"""Leitura e processamento inicial dos arquivos do dashboard."""

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

XLSX_COLUMNS = [
    "chamada_numero", "reds", "data_hora_criacao", "hora_criacao",
    "Chamada_atendimentos.local_do_fato", "Chamada_atendimentos.local_latitude",
    "Chamada_atendimentos.local_longitude", "Chamada_atendimentos.natureza_codigo",
    "Chamada_atendimentos.natureza_descricao", "Chamada_atendimentos.unidade_servico_codigo",
    "Chamada_atendimentos.unidade_servico_nome", "Empenhos.recurso_codigo_prefixo",
    "Chamada_atendimentos.chamada_classificacao_descricao", "data_classificacao",
    "hora_classificacao", "estado_chamada", "Chamada_atendimentos.local_municipio_id",
    "Chamada_atendimentos.local_municipio_nome",
]

CSV_COLUMNS = [
    "chamada_numero", "reds", "data_hora_criacao", "Chamada_atendimentos.local_do_fato",
    "Chamada_atendimentos.local_latitude", "Chamada_atendimentos.local_longitude",
    "Chamada_atendimentos.natureza_descricao", "Chamada_atendimentos.unidade_servico_nome",
    "Empenhos.recurso_codigo_prefixo", "alerta", "destaque", "envolve_autoridade",
    "Chamada_atendimentos.chamada_classificacao_descricao", "situacao",
    "data_hora_situacao_atual", "evento_associado",
]


def read_raw_data(raw: bytes, filename: str) -> pd.DataFrame:
    """Le CSV ou XLSX de forma de alta performance a partir de bytes brutos."""
    filename_clean = filename.lower().strip()
    is_excel = filename_clean.endswith((".xlsx", ".xlsm", ".xslx")) or raw[:4] == b"PK\x03\x04"
    if is_excel:
        return _normalize_excel_schema(_read_excel_with_openpyxl(raw))

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
                    return normalize_column_names(df)
            except Exception:
                continue

    detected = chardet.detect(raw[:20_000]).get("encoding") or "utf-8"
    attempts = list(dict.fromkeys([detected, "utf-8-sig", "utf-8", "cp1252", "latin-1"]))
    last_error = None
    for encoding in attempts:
        try:
            df = pd.read_csv(
                io.BytesIO(raw), sep=None, engine="python", encoding=encoding,
                dtype=str, on_bad_lines="skip",
            )
            return normalize_column_names(df)
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as error:
            last_error = error
    raise ValueError(f"CSV nao pode ser lido: {last_error}")


def read_uploaded_file(uploaded_file: Any) -> pd.DataFrame:
    """Le CSV ou XLSX usando o conteudo do upload."""
    return read_raw_data(uploaded_file.getvalue(), uploaded_file.name)


def _read_excel_with_openpyxl(raw: bytes) -> pd.DataFrame:
    """Le a aba COBOM e identifica o cabecalho nos primeiros registros de forma rapida."""
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

        known_headers = set(COLUMN_MAPPING) | set(XLSX_COLUMNS) | {
            "Reds.reds_numero",
            "chamada_data_inclusao",
            "chamada_hora_inclusao",
        }
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
        width = max((len(row) for row in rows), default=0)
        rows = [row + [None] * (width - len(row)) for row in rows]

        if header_score:
            header = [
                str(value).strip() if value is not None and str(value).strip()
                else f"coluna_{index + 1}"
                for index, value in enumerate(rows[header_index])
            ]
            return pd.DataFrame(rows[header_index + 1:], columns=header)

        return pd.DataFrame(rows[1:], columns=rows[0])
    except Exception as error:
        raise ValueError(f"Excel nao pode ser lido: {error}") from error


def _normalize_excel_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Preserva cabecalhos XLSX conhecidos e usa posicoes somente no fallback."""
    normalized = normalize_column_names(df)
    known_columns = set(XLSX_COLUMNS) | {
        "chamada_data_inclusao",
        "chamada_hora_inclusao",
        "Chamada_atendimentos.chamada_classificacao_data",
        "Chamada_atendimentos.chamada_classificacao_hora",
    }
    if any(column in normalized.columns for column in known_columns):
        return _normalize_fixed_schema_by_name(normalized)
    return _normalize_fixed_schema(normalized, XLSX_COLUMNS)


def _normalize_fixed_schema_by_name(df: pd.DataFrame) -> pd.DataFrame:
    """Converte aliases do Excel sem descartar colunas reconhecidas pelo cabecalho."""
    aliases = {
        "Reds.reds_numero": "reds",
        "Chamada_atendimentos.chamada_classificacao_data": "data_classificacao",
        "Chamada_atendimentos.chamada_classificacao_hora": "hora_classificacao",
    }
    result = df.rename(columns={source: target for source, target in aliases.items()})
    if "chamada_data_inclusao" in result.columns:
        result = result.rename(columns={
            "chamada_data_inclusao": "data_hora_criacao",
            "chamada_hora_inclusao": "hora_criacao",
        })
    if "data_hora_criacao" not in result.columns and "chamada_data_inclusao" in df.columns:
        result["data_hora_criacao"] = df["chamada_data_inclusao"]
    if {"data_hora_criacao", "hora_criacao"}.issubset(result.columns):
        result["data_hora_criacao"] = parse_datetime_series(result["data_hora_criacao"])
        result["data_hora_criacao"] = result["data_hora_criacao"] + pd.to_timedelta(
            result["hora_criacao"].astype("string").str.strip(), errors="coerce"
        )
    if "data_hora_situacao_atual" not in result.columns and {
        "data_classificacao", "hora_classificacao"
    }.issubset(result.columns):
        result["data_hora_situacao_atual"] = parse_datetime_series(result["data_classificacao"])
        result["data_hora_situacao_atual"] = result["data_hora_situacao_atual"] + pd.to_timedelta(
            result["hora_classificacao"].astype("string").str.strip(), errors="coerce"
        )
    return result


def _normalize_fixed_schema(df: pd.DataFrame, fixed_columns: list[str]) -> pd.DataFrame:
    """Converte os campos especificos dos esquemas XLSX e CSV para o modelo comum."""
    result = df.iloc[:, :len(fixed_columns)].copy()
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
    }
    result = result.rename(columns={source: target for source, target in aliases.items() if source in result})

    if "data_hora_criacao" in result.columns and "hora_criacao" in result.columns:
        result["data_hora_criacao"] = (
            result["data_hora_criacao"].astype("string").str.strip()
            + " "
            + result["hora_criacao"].astype("string").str.strip()
        )
    if "data_classificacao" in result.columns and "hora_classificacao" in result.columns:
        result["data_hora_situacao_atual"] = (
            result["data_classificacao"].astype("string").str.strip()
            + " "
            + result["hora_classificacao"].astype("string").str.strip()
        )

    return result


def _numeric_coordinates(series: pd.Series, max_abs: float) -> pd.Series:
    text = series.astype("string").str.strip()
    numeric = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce").astype("float64")

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

    fallback = numeric.isna() & series.notna()
    if fallback.any():
        numeric.loc[fallback] = series.loc[fallback].map(
            lambda value: parse_coordinate(value, max_abs)
        )
    return numeric.where(numeric.abs().le(max_abs))


def _enrich_situacao(result: pd.DataFrame) -> pd.DataFrame:
    """Normaliza situacao, marca terminalidade e calcula tempo no estado."""
    if "situacao" not in result.columns:
        result["situacao_norm"] = pd.Series(pd.NA, index=result.index, dtype="string")
        result["situacao_terminal"] = True
        return result

    sit = result["situacao"].astype("string").str.strip()
    result["situacao_norm"] = sit
    result["situacao_terminal"] = sit.str.casefold().isin(SITUACOES_TERMINAIS).fillna(True)

    if "data_hora_fim" in result.columns and "data_hora" in result.columns:
        delta = (result["data_hora_fim"] - result["data_hora"]).dt.total_seconds() / 3600
        result["tempo_no_estado_horas"] = delta.clip(lower=0)
    return result


def _enrich_natureza(result: pd.DataFrame) -> pd.DataFrame:
    """Extrai codigo, grupo tematico e prioridade da natureza."""
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
    """Converte Alerta / Destaque / Envolve autoridade em booleano."""
    for col in ("alerta", "destaque", "envolve_autoridade"):
        flag_col = f"{col}_flag"
        if col in result.columns:
            result[flag_col] = (
                result[col].astype("string").str.strip().str.casefold().eq("sim")
            )
        else:
            result[flag_col] = False
    return result


def _enrich_reds(result: pd.DataFrame) -> pd.DataFrame:
    """Decompoe Nº REDS: origem PM/BM, quantidade, multiagencia."""
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


def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Cria campos derivados usados por filtros, metricas e graficos."""
    result = df.copy()
    if "data_hora_criacao" in result.columns:
        created = parse_datetime_series(result["data_hora_criacao"])
        result["chamada_data_inclusao"] = created.dt.normalize()
        result["chamada_hora_inclusao"] = pd.to_timedelta(created.dt.time.astype(str), errors="coerce")
        result["data_hora"] = created

    for column, max_abs in (
        ("Chamada_atendimentos.local_latitude", 90),
        ("Chamada_atendimentos.local_longitude", 180),
    ):
        if column in result.columns:
            result[column] = _numeric_coordinates(result[column], max_abs)

    local_column = "Chamada_atendimentos.local_do_fato"
    if local_column in result.columns:
        result["Chamada_atendimentos.local_municipio_nome"] = result[local_column].map(
            lambda value: value if pd.isna(value) else str(value).split(" - ")[-1].strip()
        )

    if "chamada_data_inclusao" in result.columns:
        result = result.dropna(subset=["chamada_data_inclusao"])
        result["ano"] = result["chamada_data_inclusao"].dt.year
        result["mes"] = result["chamada_data_inclusao"].dt.month
        result["mes_ano"] = result["chamada_data_inclusao"].dt.to_period("M").astype(str)
        result["hora"] = (result["chamada_hora_inclusao"].dt.total_seconds() // 3600).astype("Int64")
        result["dia_semana"] = result["chamada_data_inclusao"].dt.dayofweek

    end_times = (
        parse_datetime_series(result["data_hora_situacao_atual"])
        if "data_hora_situacao_atual" in result.columns
        else pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns]")
    )
    if "situacao" in result.columns:
        situacao_norm = result["situacao"].astype("string").str.strip().str.casefold()
        is_terminal = situacao_norm.isin(SITUACOES_TERMINAIS)
        # Chamadas em andamento (nao-terminais) usam now() como referencia do decorrido.
        end_times = end_times.where(is_terminal, pd.Timestamp.now().floor("s"))
    result["data_hora_fim"] = end_times

    # Enriquecimentos derivados
    result = _enrich_situacao(result)
    result = _enrich_natureza(result)
    result = _enrich_flags(result)
    result = _enrich_reds(result)
    return result


@st.cache_data(show_spinner=False)
def load_raw_bytes_data(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    """Carrega e processa bytes brutos com cache pelo hash dos bytes do arquivo."""
    return process_dataframe(read_raw_data(raw_bytes, filename))


def load_uploaded_data(uploaded_file: Any) -> pd.DataFrame:
    """Wrapper para carregar arquivos enviados com cacheamento dos bytes."""
    return load_raw_bytes_data(uploaded_file.getvalue(), uploaded_file.name)


def _filters_key(filters: dict[str, Any]) -> tuple:
    return tuple((key, tuple(value) if isinstance(value, list) else value) for key, value in sorted(filters.items()))


@st.cache_data(show_spinner=False)
def _apply_filters_cached(df: pd.DataFrame, filters_key: tuple) -> pd.DataFrame:
    result = df
    for column, selected in filters_key:
        if selected and column in result.columns:
            if column == "Empenhos.recurso_codigo_prefixo":
                resources = result[column].fillna("").astype(str).str.replace(" / ", ",", regex=False).str.split(",").explode()
                matching = resources.str.strip().isin(selected).groupby(level=0).any()
                result = result.loc[result.index.intersection(matching[matching].index)]
            else:
                result = result[result[column].isin(selected)]
    return result


def apply_filters(df: pd.DataFrame, filters_dict: dict[str, Any]) -> pd.DataFrame:
    """Aplica filtros hashable, mantendo o DataFrame original intacto."""
    return _apply_filters_cached(df, _filters_key(filters_dict)).copy()