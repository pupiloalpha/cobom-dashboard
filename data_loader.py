"""
Leitura e processamento inicial dos arquivos do dashboard COBOM-BH.

Este módulo concentra:
    - Detecção de formato (CSV vs. XLSX), encoding e separador.
    - Normalização de schema (por nome, por mojibake revertido ou por posição).
    - Pipeline de enriquecimento (`process_dataframe`) que cria os campos
      derivados usados por filtros, métricas e gráficos.
    - Caching em duas camadas: `@st.cache_data` e chave hashable de filtros.

Dependências internas:
    - `utils.helpers`: constantes de mapeamento, parsers, extratores.

Uso típico (a partir do `app.py`):
    >>> from data_loader import load_uploaded_data, apply_filters
    >>> df = load_uploaded_data(uploaded_file)
    >>> filtrado = apply_filters(df, {"Chamada_atendimentos.local_municipio_nome": ["BETIM"]})
"""

from __future__ import annotations

import io
from typing import Any

import chardet
import numpy as np
import pandas as pd
import streamlit as st
from openpyxl import load_workbook

from utils.helpers import (
    COLUMN_MAPPING,
    NATUREZA_GRUPOS,
    SITUACOES_TERMINAIS,
    normalize_column_names,
    parse_coordinate,
    parse_datetime_series,
)


# ---------------------------------------------------------------------------
# ESQUEMAS FIXOS DE COLUNAS
# ---------------------------------------------------------------------------
# Usados como fallback quando o cabeçalho do arquivo está ilegível (mojibake
# não revertido, cabeçalhos vazios, etc.). O export do CAD mantém a ordem
# das colunas estável, então o mapeamento posicional é seguro.
# ---------------------------------------------------------------------------
XLSX_COLUMNS: list[str] = [
    "chamada_numero",
    "reds",
    "data_hora_criacao",
    "hora_criacao",
    "Chamada_atendimentos.local_do_fato",
    "Chamada_atendimentos.local_latitude",
    "Chamada_atendimentos.local_longitude",
    "Chamada_atendimentos.natureza_codigo",
    "Chamada_atendimentos.natureza_descricao",
    "Chamada_atendimentos.unidade_servico_codigo",
    "Chamada_atendimentos.unidade_servico_nome",
    "Empenhos.recurso_codigo_prefixo",
    "Chamada_atendimentos.chamada_classificacao_descricao",
    "data_classificacao",
    "hora_classificacao",
    "estado_chamada",
    "Chamada_atendimentos.local_municipio_id",
    "Chamada_atendimentos.local_municipio_nome",
]

CSV_COLUMNS: list[str] = [
    "chamada_numero",
    "reds",
    "data_hora_criacao",
    "Chamada_atendimentos.local_do_fato",
    "Chamada_atendimentos.local_latitude",
    "Chamada_atendimentos.local_longitude",
    "Chamada_atendimentos.natureza_descricao",
    "Chamada_atendimentos.unidade_servico_nome",
    "Empenhos.recurso_codigo_prefixo",
    "alerta",
    "destaque",
    "envolve_autoridade",
    "Chamada_atendimentos.chamada_classificacao_descricao",
    "situacao",
    "data_hora_situacao_atual",
    "evento_associado",
]

# Conjunto de nomes canônicos que indicam que o mapeamento por NOME funcionou.
_CSV_KNOWN_COLUMNS: set[str] = set(CSV_COLUMNS) | {
    "chamada_data_inclusao",
    "chamada_hora_inclusao",
    "data_classificacao",
    "hora_classificacao",
    "tipo_arquivo",
    "arquivo",
    "situacao_norm",
    "situacao_terminal",
}


# >>> CORREÇÃO -----------------------------------------------------------------
# Aliases adicionais aplicados localmente em data_loader, independentes de
# helpers.COLUMN_MAPPING. Cobrem o arquivo "Mensal COBOM" do CAD, cujo cabeçalho
# expõe "ESTADO_CHAMADA" em vez de "Situação". Sem isso, `situacao` nunca é
# criada no fluxo XLSX e a lógica de terminalidade/ativas (abas 5 e 6) quebra.
# ------------------------------------------------------------------------------
_LOCAL_COLUMN_ALIASES: dict[str, str] = {
    "ESTADO_CHAMADA": "situacao",
    "Estado_chamada": "situacao",
    "estado_chamada": "situacao",
    "Estado Chamada": "situacao",
    "Estado da Chamada": "situacao",
    "ESTADO DA CHAMADA": "situacao",
    "situaçăo": "situacao",
    "Situaçăo": "situacao",
    "situacao_chamada": "situacao",
}


def _apply_local_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica aliases locais de colunas sem depender de `helpers.COLUMN_MAPPING`.

    Não sobrescreve colunas já existentes com o nome canônico — só renomeia
    se o alias estiver presente e o destino ainda não tiver sido criado.
    """
    rename_map: dict[str, str] = {}
    existing = set(df.columns)
    for source, target in _LOCAL_COLUMN_ALIASES.items():
        if source in existing and target not in existing and source != target:
            rename_map[source] = target
    return df.rename(columns=rename_map) if rename_map else df


# >>> CORREÇÃO -----------------------------------------------------------------
# Wrapper seguro de parse_datetime_series: garante que a saída é SEMPRE
# datetime64[ns] nativo do numpy (NaT em vez de pd.NA nullable). Evita que
# resíduos de pd.NA se propaguem pelas etapas seguintes do pipeline e
# estourem em chamadas como `.astype("float64")` ou `pd.to_timedelta`.
# ------------------------------------------------------------------------------
def _safe_datetime(series: pd.Series) -> pd.Series:
    parsed = parse_datetime_series(series)
    # Força numpy datetime64[ns] independente de dtype nullable de entrada.
    try:
        arr = parsed.to_numpy(dtype="datetime64[ns]", na_value=np.datetime64("NaT"))
    except (TypeError, ValueError):
        # Fallback: coage objeto por objeto.
        arr = np.array(
            [np.datetime64("NaT") if pd.isna(v) else np.datetime64(v) for v in parsed],
            dtype="datetime64[ns]",
        )
    return pd.Series(arr, index=series.index)


# >>> CORREÇÃO -----------------------------------------------------------------
# Wrapper seguro de pd.to_timedelta para colunas hora (string vazia, pd.NA,
# "HH:MM:SS", "NaT", etc.). Sem isso, o `pd.to_timedelta` reclama em alguns
# pandas quando o array intermediário contém pd.NA.
# ------------------------------------------------------------------------------
def _safe_timedelta(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    # Normaliza vazios e nulos para NaN antes de converter.
    s = s.where(s.ne("") & s.notna(), other=pd.NA)
    td = pd.to_timedelta(s, errors="coerce")
    try:
        arr = td.to_numpy(dtype="timedelta64[ns]", na_value=np.timedelta64("NaT"))
    except (TypeError, ValueError):
        arr = np.array(
            [np.timedelta64("NaT") if pd.isna(v) else np.timedelta64(v) for v in td],
            dtype="timedelta64[ns]",
        )
    return pd.Series(arr, index=series.index)


# ===========================================================================
# LEITURA CRUA (bytes → DataFrame com schema normalizado)
# ===========================================================================
def read_raw_data(raw: bytes, filename: str) -> pd.DataFrame:
    """Lê CSV ou XLSX a partir de bytes brutos, com detecção automática.

    Estratégia:
        1. Se o nome/extensão indicar Excel OU os primeiros bytes forem o
           magic number ``PK\\x03\\x04`` (ZIP), usa ``openpyxl``.
        2. Caso contrário, tenta CSV com heurística de separador e encoding.

    Args:
        raw: Conteúdo binário do arquivo.
        filename: Nome original (usado para desambiguar Excel vs. CSV).

    Returns:
        DataFrame já com schema normalizado (nomes canônicos).

    Raises:
        ValueError: Se o arquivo não puder ser lido por nenhuma estratégia.
    """
    filename_clean = filename.lower().strip()

    # Detecção de Excel por extensão OU magic number ZIP.
    is_excel = (
        filename_clean.endswith((".xlsx", ".xlsm", ".xslx"))
        or raw[:4] == b"PK\x03\x04"
    )
    if is_excel:
        return _normalize_excel_schema(_read_excel_with_openpyxl(raw))

    # Heurística de separador a partir dos primeiros 4 KB.
    sample = raw[:4096]
    semicolon_count = sample.count(b";")
    comma_count = sample.count(b",")
    tab_count = sample.count(b"\t")

    if semicolon_count >= comma_count and semicolon_count >= tab_count:
        fast_seps = [";", ",", "\t"]
    elif tab_count > comma_count:
        fast_seps = ["\t", ";", ","]
    else:
        fast_seps = [",", ";", "\t"]

    fast_encodings = ["utf-8-sig", "latin-1", "utf-8", "cp1252"]

    # Tentativa rápida: combinação de separador × encoding com engine "c".
    for sep in fast_seps:
        for encoding in fast_encodings:
            try:
                df = pd.read_csv(
                    io.BytesIO(raw),
                    sep=sep,
                    encoding=encoding,
                    dtype=str,
                    on_bad_lines="skip",
                    engine="c",
                )
                if df.shape[1] > 1:
                    return _normalize_csv_schema(df)
            except Exception:
                continue

    # Fallback: detecção automática de encoding + separador pelo parser Python.
    detected = chardet.detect(raw[:20_000]).get("encoding") or "utf-8"
    attempts = list(dict.fromkeys([detected, "utf-8-sig", "utf-8", "cp1252", "latin-1"]))
    last_error: Exception | None = None

    for encoding in attempts:
        try:
            df = pd.read_csv(
                io.BytesIO(raw),
                sep=None,
                engine="python",
                encoding=encoding,
                dtype=str,
                on_bad_lines="skip",
            )
            return _normalize_csv_schema(df)
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as error:
            last_error = error

    raise ValueError(f"CSV nao pode ser lido: {last_error}")


def read_uploaded_file(uploaded_file: Any) -> pd.DataFrame:
    """Wrapper de conveniência para ``read_raw_data`` a partir de um upload.

    Args:
        uploaded_file: Objeto ``UploadedFile`` do Streamlit.

    Returns:
        DataFrame normalizado.
    """
    return read_raw_data(uploaded_file.getvalue(), uploaded_file.name)


# ===========================================================================
# NORMALIZAÇÃO DE SCHEMA (por nome, mojibake e posição)
# ===========================================================================
def _normalize_csv_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Mapeia por nome quando possível; senão usa a posição fixa do CSV.

    Exportações do CAD têm ordem de colunas estável. Quando o cabeçalho
    está corrompido (ex.: ``Nş chamada``, ``Situaçăo``), o mapeamento por
    nome falha, mas a ordem ainda é confiável — por isso o fallback
    posicional baseado em ``CSV_COLUMNS``.

    Args:
        df: DataFrame cru do CSV.

    Returns:
        DataFrame normalizado.
    """
    normalized = _apply_local_aliases(normalize_column_names(df))

    # Se pelo menos uma coluna canônica apareceu, considera o mapeamento OK.
    if any(col in normalized.columns for col in _CSV_KNOWN_COLUMNS):
        return normalized

    # Fallback posicional.
    raw = df.copy()
    raw.columns = raw.columns.astype(str).str.strip()
    return _normalize_fixed_schema(raw, CSV_COLUMNS)


def _read_excel_with_openpyxl(raw: bytes) -> pd.DataFrame:
    """Lê a aba ``bd_cobom`` (ou a mais populosa) e detecta a linha de cabeçalho.

    Estratégia:
        1. Abre o workbook em modo ``read_only`` (economia de memória).
        2. Prefere a aba chamada ``bd_cobom``; caso não exista, escolhe a
           primeira aba com conteúdo.
        3. Escaneia as primeiras 25 linhas buscando aquela com maior número
           de correspondências em ``COLUMN_MAPPING ∪ XLSX_COLUMNS`` —
           essa linha é o cabeçalho.
        4. Constrói o DataFrame a partir das linhas abaixo do cabeçalho.

    Args:
        raw: Bytes do arquivo Excel.

    Returns:
        DataFrame cru (ainda não normalizado por nome canônico).

    Raises:
        ValueError: Se o arquivo não puder ser lido.
    """
    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        worksheet = next(
            (sheet for sheet in workbook.worksheets if sheet.title.strip().lower() == "bd_cobom"),
            None,
        )
        if worksheet is None:
            worksheet = next(
                (sheet for sheet in workbook.worksheets if sheet.max_row and sheet.max_column),
                None,
            )
        if worksheet is None:
            return pd.DataFrame()

        rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
        if not rows:
            return pd.DataFrame()

        # >>> CORREÇÃO: incluir aliases locais no conjunto de cabeçalhos conhecidos
        # para que "ESTADO_CHAMADA" seja reconhecida na pontuação do cabeçalho.
        known_headers = (
            set(COLUMN_MAPPING)
            | set(XLSX_COLUMNS)
            | set(_LOCAL_COLUMN_ALIASES)
            | {
                "Reds.reds_numero",
                "chamada_data_inclusao",
                "chamada_hora_inclusao",
            }
        )

        # Pontua cada linha pelo número de cabeçalhos conhecidos.
        sample_range = range(min(25, len(rows)))
        header_index = max(
            sample_range,
            key=lambda index: sum(
                str(value).strip() in known_headers
                for value in rows[index]
                if value is not None
            ),
            default=0,
        )
        header_score = sum(
            str(value).strip() in known_headers
            for value in rows[header_index]
            if value is not None
        )

        # Padroniza largura das linhas para evitar erros de comprimento.
        width = max((len(row) for row in rows), default=0)
        rows = [row + [None] * (width - len(row)) for row in rows]

        if header_score:
            header = [
                str(value).strip() if value is not None and str(value).strip()
                else f"coluna_{index + 1}"
                for index, value in enumerate(rows[header_index])
            ]
            return pd.DataFrame(rows[header_index + 1:], columns=header)

        # Fallback: assume que a primeira linha é o cabeçalho.
        return pd.DataFrame(rows[1:], columns=rows[0])

    except Exception as error:
        raise ValueError(f"Excel nao pode ser lido: {error}") from error


def _normalize_excel_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza schema de Excel: por nome se possível, senão por posição fixa.

    Args:
        df: DataFrame cru vindo de ``_read_excel_with_openpyxl``.

    Returns:
        DataFrame com nomes canônicos e aliases resolvidos.
    """
    normalized = _apply_local_aliases(normalize_column_names(df))
    known_columns = set(XLSX_COLUMNS) | {
        "chamada_data_inclusao",
        "chamada_hora_inclusao",
        "Chamada_atendimentos.chamada_classificacao_data",
        "Chamada_atendimentos.chamada_classificacao_hora",
        "situacao",  # >>> CORREÇÃO: reconhece alias "ESTADO_CHAMADA"
    }
    if any(column in normalized.columns for column in known_columns):
        return _normalize_fixed_schema_by_name(normalized)
    return _normalize_fixed_schema(normalized, XLSX_COLUMNS)


def _normalize_fixed_schema_by_name(df: pd.DataFrame) -> pd.DataFrame:
    """Resolve aliases de colunas do Excel sem descartar as já reconhecidas.

    Converte ``Reds.reds_numero`` → ``reds``, junta data+hora de criação
    em um único ``data_hora_criacao`` e a data/hora da situação atual em
    ``data_hora_situacao_atual``.

    Args:
        df: DataFrame com cabeçalhos já reconhecidos.

    Returns:
        DataFrame com aliases resolvidos e colunas combinadas.
    """
    aliases = {
        "Reds.reds_numero": "reds",
        "Chamada_atendimentos.chamada_classificacao_data": "data_classificacao",
        "Chamada_atendimentos.chamada_classificacao_hora": "hora_classificacao",
    }
    result = df.rename(columns={source: target for source, target in aliases.items()})

    # Combina data + hora de criação, se ainda separadas.
    if "chamada_data_inclusao" in result.columns:
        result = result.rename(columns={
            "chamada_data_inclusao": "data_hora_criacao",
            "chamada_hora_inclusao": "hora_criacao",
        })
    if "data_hora_criacao" not in result.columns and "chamada_data_inclusao" in df.columns:
        result["data_hora_criacao"] = df["chamada_data_inclusao"]

    # >>> CORREÇÃO: usa wrappers seguros para data/hora
    if {"data_hora_criacao", "hora_criacao"}.issubset(result.columns):
        result["data_hora_criacao"] = _safe_datetime(result["data_hora_criacao"])
        result["data_hora_criacao"] = result["data_hora_criacao"] + _safe_timedelta(
            result["hora_criacao"]
        )

    # Combina data + hora da situação atual.
    if "data_hora_situacao_atual" not in result.columns and {
        "data_classificacao", "hora_classificacao"
    }.issubset(result.columns):
        result["data_hora_situacao_atual"] = _safe_datetime(result["data_classificacao"])
        result["data_hora_situacao_atual"] = result["data_hora_situacao_atual"] + _safe_timedelta(
            result["hora_classificacao"]
        )

    # >>> CORREÇÃO: normaliza data_hora_criacao que ficou sem combinar (caso
    # o arquivo tenha vindo com data/hora já num único campo, formato string).
    if "data_hora_criacao" in result.columns:
        result["data_hora_criacao"] = _safe_datetime(result["data_hora_criacao"])

    return result


def _normalize_fixed_schema(df: pd.DataFrame, fixed_columns: list[str]) -> pd.DataFrame:
    """Converte colunas por posição para o modelo canônico do dashboard.

    Se o DataFrame tiver menos colunas que o esquema, preenche as faltantes
    com ``pd.NA``. Combina campos de data/hora separados em timestamps únicos.

    Args:
        df: DataFrame cru (sem cabeçalho confiável).
        fixed_columns: Lista ordenada de nomes canônicos esperados.

    Returns:
        DataFrame com o esquema canônico aplicado.
    """
    result = df.iloc[:, :len(fixed_columns)].copy()

    # Preenche colunas faltantes para manter a forma do esquema.
    if result.shape[1] < len(fixed_columns):
        for index in range(result.shape[1], len(fixed_columns)):
            result[index] = pd.NA
    result.columns = fixed_columns

    aliases = {
        "Reds.reds_numero": "reds",
        "chamada_data_inclusao": "data_hora_criacao",
        "chamada_hora_inclusao": "hora_criacao",
        "Chamada_atendimentos.chamada_classificacao_data": "data_classificacao",
        "Chamada_atendimentos.chamada_classificacao_hora": "hora_classificacao",
        "estado_chamada": "situacao",  # >>> CORREÇÃO
        "ESTADO_CHAMADA": "situacao",  # >>> CORREÇÃO
    }
    result = result.rename(
        columns={s: t for s, t in aliases.items() if s in result}
    )

    # Combina data + hora de criação (com wrapper seguro).
    if "data_hora_criacao" in result.columns and "hora_criacao" in result.columns:
        result["data_hora_criacao"] = (
            result["data_hora_criacao"].astype("string").str.strip()
            + " "
            + result["hora_criacao"].astype("string").str.strip()
        )

    # Combina data + hora da situação atual.
    if "data_classificacao" in result.columns and "hora_classificacao" in result.columns:
        result["data_hora_situacao_atual"] = (
            result["data_classificacao"].astype("string").str.strip()
            + " "
            + result["hora_classificacao"].astype("string").str.strip()
        )

    return result


# ===========================================================================
# ENRIQUECIMENTO (campos derivados)
# ===========================================================================
def _numeric_coordinates(series: pd.Series, max_abs: float) -> pd.Series:
    """Normaliza coordenadas, corrigindo valores sem separador decimal.

    Valores como ``-19916700`` (sem ponto/vírgula) podem representar
    ``-19.9167``. A função divide por potências de 10 até que o valor
    caiba em ``[-max_abs, max_abs]``.

    Args:
        series: Série textual de coordenadas.
        max_abs: Limite absoluto (90 lat / 180 lon).

    Returns:
        Série de floats dentro da faixa (ou ``NaN``).
    """
    text = series.astype("string").str.strip()
    raw = pd.to_numeric(
        text.str.replace(",", ".", regex=False), errors="coerce"
    )

    # >>> CORREÇÃO -----------------------------------------------------------------
    # Alguns pandas devolvem dtype "object" contendo pd.NA quando a coluna de
    # entrada tem dtype "string" (nullable) e há valores nulos. Nesse caso,
    # `raw.astype("float64")` chama `float(pd.NA)` internamente e estoura:
    #   "float() argument must be a string or a real number, not 'NAType'"
    # Aqui forçamos a conversão via numpy float64 nativo, mapeando pd.NA → NaN.
    # ------------------------------------------------------------------------------
    try:
        numeric = raw.astype("float64")
    except (TypeError, ValueError):
        numeric = pd.Series(
            np.where(pd.isna(raw), np.nan, raw).astype("float64"),
            index=series.index,
        )

    # Garantia extra: se ainda veio como nullable Float64, converte para numpy.
    if str(numeric.dtype) not in ("float64", "float32"):
        try:
            numeric = numeric.astype("float64")
        except (TypeError, ValueError):
            numeric = pd.Series(
                numeric.to_numpy(dtype="float64", na_value=np.nan),
                index=series.index,
            )
    else:
        # Já é numpy float64: garante que é um Series numpy-backed (não extension).
        if not isinstance(numeric.dtype, np.dtype):
            numeric = pd.Series(
                numeric.to_numpy(dtype="float64", na_value=np.nan),
                index=series.index,
            )

    # Detecta inteiros fora da faixa sem separador decimal → provável erro de escala.
    integer_like = numeric.notna() & numeric.mod(1).eq(0)
    unformatted = numeric.abs().gt(max_abs) & (
        ~text.str.contains(r"[.,]", regex=True, na=False) | integer_like
    )
    for index in numeric.index[unformatted]:
        value = numeric.at[index]
        for scale in range(1, 10):
            candidate = value / 10 ** scale
            if abs(candidate) <= max_abs:
                numeric.at[index] = candidate
                break

    # Fallback para o parser robusto de coordenadas.
    fallback = numeric.isna() & series.notna()
    if fallback.any():
        numeric.loc[fallback] = series.loc[fallback].map(
            lambda value: parse_coordinate(value, max_abs)
        )
    return numeric.where(numeric.abs().le(max_abs))


def _enrich_situacao(result: pd.DataFrame) -> pd.DataFrame:
    """Normaliza situação, marca terminalidade e calcula tempo no estado.

    Adiciona as colunas:
        - ``situacao_norm``: string normalizada (strip).
        - ``situacao_terminal``: ``True`` se situação ∈ ``SITUACOES_TERMINAIS``.
        - ``tempo_no_estado_horas``: horas decorridas entre criação e
          ``data_hora_fim`` (quando disponível), com clip em ``[0, +∞)``.

    Args:
        result: DataFrame em processamento.

    Returns:
        Mesmo DataFrame, com as três colunas adicionadas.
    """
    if "situacao" not in result.columns:
        result["situacao_norm"] = pd.Series(pd.NA, index=result.index, dtype="string")
        result["situacao_terminal"] = True
        result["tempo_no_estado_horas"] = pd.Series(pd.NA, index=result.index, dtype="float64")
        return result

    sit = result["situacao"].astype("string").str.strip()
    result["situacao_norm"] = sit
    result["situacao_terminal"] = sit.str.casefold().isin(SITUACOES_TERMINAIS).fillna(False)

    if "data_hora_fim" in result.columns and "data_hora" in result.columns:
        delta = (result["data_hora_fim"] - result["data_hora"]).dt.total_seconds() / 3600
        result["tempo_no_estado_horas"] = delta.clip(lower=0)
    else:
        result["tempo_no_estado_horas"] = pd.Series(pd.NA, index=result.index, dtype="float64")
    return result


def _enrich_natureza(result: pd.DataFrame) -> pd.DataFrame:
    """Extrai código, grupo temático e prioridade da natureza.

    Formato esperado da descrição: ``"V12345 NOME DA NATUREZA Prioridade: 2"``.

    Adiciona:
        - ``natureza_codigo``: código ``[A-Z]\\d{5}``.
        - ``natureza_grupo_letra``: primeira letra do código.
        - ``natureza_grupo``: rótulo do grupo (via ``NATUREZA_GRUPOS``).
        - ``natureza_prioridade``: inteiro 1, 2 ou 3.

    Args:
        result: DataFrame em processamento.

    Returns:
        Mesmo DataFrame, com as quatro colunas adicionadas.
    """
    col = "Chamada_atendimentos.natureza_descricao"
    if col not in result.columns:
        result["natureza_codigo"] = pd.Series(pd.NA, index=result.index, dtype="string")
        result["natureza_grupo_letra"] = pd.Series(pd.NA, index=result.index, dtype="string")
        result["natureza_grupo"] = "📌 Outros"
        result["natureza_prioridade"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        return result

    nat = result[col].astype("string")
    result["natureza_codigo"] = nat.str.extract(r"^([A-Z]\d{5})", expand=False)
    result["natureza_grupo_letra"] = result["natureza_codigo"].str[0]
    result["natureza_grupo"] = (
        result["natureza_grupo_letra"].map(NATUREZA_GRUPOS).fillna("📌 Outros")
    )
    result["natureza_prioridade"] = pd.to_numeric(
        nat.str.extract(r"Prioridade:\s*(\d)", expand=False),
        errors="coerce",
    ).astype("Int64")
    return result


def _enrich_flags(result: pd.DataFrame) -> pd.DataFrame:
    """Converte Alerta / Destaque / Envolve autoridade em booleanos.

    Colunas de entrada (``alerta``, ``destaque``, ``envolve_autoridade``)
    contêm ``"Sim"`` / ``"Não"``; o resultado são colunas ``*_flag`` do
    tipo ``bool``, com ``False`` quando a coluna original não existe.

    Args:
        result: DataFrame em processamento.

    Returns:
        Mesmo DataFrame, com ``alerta_flag``, ``destaque_flag`` e
        ``envolve_autoridade_flag``.
    """
    for col in ("alerta", "destaque", "envolve_autoridade"):
        flag_col = f"{col}_flag"
        if col in result.columns:
            result[flag_col] = (
                result[col].astype("string").str.strip().str.casefold().eq("sim")
            ).fillna(False)
        else:
            result[flag_col] = False
    return result


def _enrich_reds(result: pd.DataFrame) -> pd.DataFrame:
    """Decompõe o campo ``reds`` em origem, quantidade e multiagência.

    O campo ``reds`` contém identificadores separados por espaço no formato
    ``"NNN (PM) NNN (BM)"``. Extrai:
        - ``reds_qtd``: número de ocorrências REDS.
        - ``reds_pm`` / ``reds_bm``: presença de cada agência.
        - ``reds_multiagencia``: mais de um REDS.
        - ``reds_origem``: rótulo legível (Somente PM / Somente BM /
          PM + BM (multiagência) / Sem REDS).

    Args:
        result: DataFrame em processamento.

    Returns:
        Mesmo DataFrame, com as cinco colunas adicionadas.
    """
    if "reds" not in result.columns:
        result["reds_qtd"] = pd.Series(0, index=result.index, dtype="Int64")
        result["reds_pm"] = False
        result["reds_bm"] = False
        result["reds_multiagencia"] = False
        result["reds_origem"] = "Sem REDS"
        return result

    reds = result["reds"].fillna("").astype("string")
    result["reds_qtd"] = reds.str.count(r"\([PB]M\)").fillna(0).astype("Int64")
    result["reds_pm"] = reds.str.contains(r"\(PM\)", regex=True, na=False)
    result["reds_bm"] = reds.str.contains(r"\(BM\)", regex=True, na=False)
    result["reds_multiagencia"] = result["reds_qtd"] > 1
    result["reds_origem"] = np.select(
        [
            result["reds_pm"] & ~result["reds_bm"],
            ~result["reds_pm"] & result["reds_bm"],
            result["reds_pm"] & result["reds_bm"],
        ],
        ["Somente PM", "Somente BM", "PM + BM (multiagência)"],
        default="Sem REDS",
    )
    return result


# ===========================================================================
# PIPELINE PRINCIPAL
# ===========================================================================
def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Cria os campos derivados usados por filtros, métricas e gráficos.

    Ordem das etapas:
        1. Parse de ``data_hora_criacao`` e derivação de data/hora/ano/mês.
        2. Normalização de coordenadas (lat/lon).
        3. Extração do município a partir de ``local_do_fato``.
        4. Cálculo de ``data_hora_fim``:
              - se situação terminal → usa ``data_hora_situacao_atual``;
              - caso contrário → usa ``now()`` (chamada ativa).
        5. Enriquecimentos: situação, natureza, flags, REDS.

    Args:
        df: DataFrame já normalizado por ``read_raw_data``.

    Returns:
        DataFrame enriquecido, pronto para filtros e gráficos.
    """
    result = df.copy()

    # >>> CORREÇÃO: aplica aliases locais (ex.: ESTADO_CHAMADA → situacao) ANTES
    # de qualquer etapa do pipeline. Cobre arquivos XLSX que não passaram pelo
    # normalize_column_names por já terem colunas canônicas parciais.
    result = _apply_local_aliases(result)

    # -- Etapa 1: data/hora de criação e derivações temporais ----------------
    if "data_hora_criacao" in result.columns:
        created = _safe_datetime(result["data_hora_criacao"])
        result["chamada_data_inclusao"] = created.dt.normalize()
        result["chamada_hora_inclusao"] = pd.to_timedelta(
            created.dt.time.astype(str), errors="coerce"
        )
        result["data_hora"] = created

    # -- Etapa 2: coordenadas ------------------------------------------------
    for column, max_abs in (
        ("Chamada_atendimentos.local_latitude", 90),
        ("Chamada_atendimentos.local_longitude", 180),
    ):
        if column in result.columns:
            result[column] = _numeric_coordinates(result[column], max_abs)

    # -- Etapa 3: município --------------------------------------------------
    local_column = "Chamada_atendimentos.local_do_fato"
    if local_column in result.columns:
        result["Chamada_atendimentos.local_municipio_nome"] = result[local_column].map(
            lambda value: value if pd.isna(value) else str(value).split(" - ")[-1].strip()
        )

    # -- Etapa 4: componentes temporais adicionais ---------------------------
    if "chamada_data_inclusao" in result.columns:
        result = result.dropna(subset=["chamada_data_inclusao"])
        result["ano"] = result["chamada_data_inclusao"].dt.year
        result["mes"] = result["chamada_data_inclusao"].dt.month
        result["mes_ano"] = result["chamada_data_inclusao"].dt.to_period("M").astype(str)
        result["hora"] = (result["chamada_hora_inclusao"].dt.total_seconds() // 3600).astype("Int64")
        result["dia_semana"] = result["chamada_data_inclusao"].dt.dayofweek

    # -- Etapa 5: data_hora_fim (terminal vs. agora) -------------------------
    end_times = (
        _safe_datetime(result["data_hora_situacao_atual"])
        if "data_hora_situacao_atual" in result.columns
        else pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns]")
    )
    if "situacao" in result.columns:
        situacao_norm = result["situacao"].astype("string").str.strip().str.casefold()
        is_terminal = situacao_norm.isin(SITUACOES_TERMINAIS)
        # Chamadas ativas: substitui por now() para medir tempo decorrido.
        end_times = end_times.where(is_terminal, pd.Timestamp.now().floor("s"))
    result["data_hora_fim"] = end_times

    # -- Etapa 6: enriquecimentos -------------------------------------------
    result = _enrich_situacao(result)
    result = _enrich_natureza(result)
    result = _enrich_flags(result)
    result = _enrich_reds(result)
    return result


# ===========================================================================
# CACHE E CARREGAMENTO
# ===========================================================================
@st.cache_data(show_spinner=False)
def load_raw_bytes_data(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    """Carrega e processa bytes brutos com cache pelo hash do conteúdo.

    O Streamlit usa o hash dos argumentos como chave de cache; como
    ``raw_bytes`` é o conteúdo completo, qualquer mudança no arquivo
    invalida automaticamente a entrada.

    Args:
        raw_bytes: Conteúdo binário do arquivo.
        filename: Nome original (usado na detecção de tipo).

    Returns:
        DataFrame processado e enriquecido.
    """
    return process_dataframe(read_raw_data(raw_bytes, filename))


def load_uploaded_data(uploaded_file: Any) -> pd.DataFrame:
    """Wrapper sobre ``load_raw_bytes_data`` para um ``UploadedFile``.

    Args:
        uploaded_file: Arquivo enviado pelo usuário no Streamlit.

    Returns:
        DataFrame processado e enriquecido.
    """
    return load_raw_bytes_data(uploaded_file.getvalue(), uploaded_file.name)


# ===========================================================================
# FILTROS COM CACHE
# ===========================================================================
def _filters_key(filters: dict[str, Any]) -> tuple:
    """Converte um dicionário de filtros em uma chave hashable ordenada.

    Listas são convertidas em tuplas; as chaves são ordenadas para garantir
    que a mesma seleção lógica produza a mesma chave de cache.

    Args:
        filters: Dicionário ``{coluna: [valores]}``.

    Returns:
        Tupla hashable pronta para servir de chave de cache.
    """
    return tuple(
        (key, tuple(value) if isinstance(value, list) else value)
        for key, value in sorted(filters.items())
    )


@st.cache_data(show_spinner=False)
def _apply_filters_cached(df: pd.DataFrame, filters_key: tuple) -> pd.DataFrame:
    """Aplica filtros com cache; recebe a chave hashable já preparada.

    O filtro especial de ``Empenhos.recurso_codigo_prefixo`` explode o
    campo de recursos e mantém linhas cujo conjunto de recursos tenha
    interseção com a seleção.

    Args:
        df: DataFrame enriquecido.
        filters_key: Saída de ``_filters_key``.

    Returns:
        DataFrame filtrado.
    """
    result = df
    for column, selected in filters_key:
        if selected and column in result.columns:
            if column == "Empenhos.recurso_codigo_prefixo":
                # Filtro especial: recursos são multi-valor em uma só célula.
                resources = (
                    result[column]
                    .fillna("")
                    .astype(str)
                    .str.replace(" / ", ",", regex=False)
                    .str.split(",")
                    .explode()
                )
                matching = resources.str.strip().isin(selected).groupby(level=0).any()
                result = result.loc[result.index.intersection(matching[matching].index)]
            else:
                result = result[result[column].isin(selected)]
    return result


def apply_filters(df: pd.DataFrame, filters_dict: dict[str, Any]) -> pd.DataFrame:
    """Aplica filtros hashable, mantendo o DataFrame original intacto.

    Args:
        df: DataFrame enriquecido.
        filters_dict: ``{coluna: [valores selecionados]}``.

    Returns:
        Cópia filtrada do DataFrame.
    """
    return _apply_filters_cached(df, _filters_key(filters_dict)).copy()