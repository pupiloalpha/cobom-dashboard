"""
Funções puras de normalização, parsing e enriquecimento dos dados do COBOM-BH.

Este módulo NÃO depende de Streamlit, Plotly ou qualquer biblioteca de I/O.
É importado por `data_loader.py`, `visualizations.py` e `app.py` para garantir
que a lógica de domínio permaneça testável e reutilizável fora do contexto web.

Responsabilidades:
    - Mapear cabeçalhos do CAD para nomes canônicos (COLUMN_MAPPING).
    - Reverter mojibake (encoding CP1252 ↔ UTF-8) em cabeçalhos e valores.
    - Fazer parsing robusto de datas e coordenadas em formatos brasileiros.
    - Extrair BBM, fração, recursos empenhados e origem do REDS.
    - Detectar o tipo de arquivo (classificadas / ativas / genérico).
    - Fornecer utilitários de segurança para popups de mapa.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# MAPEAMENTO DE COLUNAS DO CAD
# ---------------------------------------------------------------------------
# Rótulos exibidos no export do CAD (alguns com variantes de acentuação e/ou
# caracteres corrompidos por encoding) → nome canônico usado internamente.
#
# Sempre que um novo export introduzir um rótulo diferente, adicione aqui.
# `normalize_column_names` também tenta a versão corrigida por `fix_mojibake`
# caso o mapeamento direto falhe.
# ---------------------------------------------------------------------------
COLUMN_MAPPING: dict[str, str] = {
    "Nº chamada": "chamada_numero",
    "Nş chamada": "chamada_numero",
    "Nº REDS": "reds",
    "Nş REDS": "reds",
    "Data/hora de criação": "data_hora_criacao",
    "Data/hora de criaçăo": "data_hora_criacao",
    "Data/hora de criacao": "data_hora_criacao",
    "Local do fato": "Chamada_atendimentos.local_do_fato",
    "Latitude  do local": "Chamada_atendimentos.local_latitude",
    "Latitude do local": "Chamada_atendimentos.local_latitude",
    "Longitude do local": "Chamada_atendimentos.local_longitude",
    "Natureza": "Chamada_atendimentos.natureza_descricao",
    "Unidade Responsável": "Chamada_atendimentos.unidade_servico_nome",
    "Unidade Responsavel": "Chamada_atendimentos.unidade_servico_nome",
    "Recursos empenhados": "Empenhos.recurso_codigo_prefixo",
    "Alerta": "alerta",
    "Destaque": "destaque",
    "Envolve autoridade": "envolve_autoridade",
    "Tipo de classificação": "Chamada_atendimentos.chamada_classificacao_descricao",
    "Tipo de classificaçăo": "Chamada_atendimentos.chamada_classificacao_descricao",
    "Tipo de classificacao": "Chamada_atendimentos.chamada_classificacao_descricao",
    "Situação": "situacao",
    "Situaçăo": "situacao",
    "Situacao": "situacao",
    "Data/hora da situação atual": "data_hora_situacao_atual",
    "Data/hora da situaçăo atual": "data_hora_situacao_atual",
    "Data/hora da situacao atual": "data_hora_situacao_atual",
    "Evento associado": "evento_associado",
}


# ---------------------------------------------------------------------------
# CORREÇÃO DE MOJIBAKE
# ---------------------------------------------------------------------------
# O export do CAD pode ser gerado em CP1252 e lido como UTF-8 (ou vice-versa),
# o que transforma acentos e o símbolo "º" em sequências estranhas.
# Este mapa reverte os casos conhecidos.
# ---------------------------------------------------------------------------
_MOJIBAKE_MAP = str.maketrans({
    "ş": "º",
    "Ş": "º",
    "ă": "ã",
    "Ă": "Ã",
    "Ŕ": "À",
    "ŕ": "à",
    "Ę": "Ê",
    "ę": "ê",
    "Ţ": "Ç",
    "ţ": "ç",
    "´": "Ó",
    "ł": "õ",
})


def fix_mojibake(text: Any) -> str:
    """Reverte caracteres corrompidos por encoding mismatch em exports do CAD.

    Args:
        text: Valor de entrada (str, None, NaN, etc.).

    Returns:
        String com os caracteres corrigidos. Retorna ``""`` para ``None``.
    """
    if text is None:
        return ""
    return str(text).translate(_MOJIBAKE_MAP)


# ---------------------------------------------------------------------------
# GRUPOS TEMÁTICOS DE NATUREZA
# ---------------------------------------------------------------------------
# O código da natureza segue o padrão `<LETRA><5 dígitos>` (ex.: V12345).
# A letra inicial identifica o grupo temático. Prioridade vem anexada à
# descrição no formato "Prioridade: N".
# ---------------------------------------------------------------------------
NATUREZA_GRUPOS: dict[str, str] = {
    "V": "🚑 APH / Vítimas",
    "O": "🔥 Incêndios / Queimadas",
    "S": "🆘 Salvamentos",
    "W": "🛡️ Apoio / Preventivas",
    "P": "⚠️ Perigos / Vistorias",
    "X": "📋 Empenho Administrativo",
    "Y": "🚁 Aéreas / Apoio a Órgãos",
    "Q": "🎓 Treinamento / Palestras",
    "R": "🤝 Ações Comunitárias / Risco",
    "A": "💔 Autoextermínio",
    "B": "🏗️ Brigada / Apoio Especial",
}


# ---------------------------------------------------------------------------
# REGRA DE NEGÓCIO: SITUAÇÕES TERMINAIS
# ---------------------------------------------------------------------------
# No CAD, APENAS "Classificada" retira a chamada da tela do despachante.
# Todos os demais estados (Terminada, Em controle, No local, À caminho,
# Suspensa, Nada constatado, Teste, RAT, Duplicada, Dispensada pelo
# solicitante, etc.) mantêm a chamada ATIVA — o tempo decorrido é medido
# em relação a `now()`.
#
# Este conjunto é usado por `data_loader._enrich_situacao` e por toda a
# lógica de SLA/ativas nas abas 5 e 6 do dashboard.
# ---------------------------------------------------------------------------
SITUACOES_TERMINAIS: set[str] = {"classificada"}


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os nomes de colunas; tolerante a cabeçalhos com mojibake.

    Estratégia por coluna:
        1. Tenta mapeamento direto em ``COLUMN_MAPPING``.
        2. Se não casar, aplica ``fix_mojibake`` e tenta novamente.
        3. Se ainda não casar, mantém o nome (apenas com mojibake revertido).

    Colunas duplicadas após o mapeamento são removidas (primeira ocorrência
    vence), evitando conflito em operações vetoriais posteriores.

    Args:
        df: DataFrame original.

    Returns:
        Novo DataFrame com colunas renomeadas.
    """
    result = df.copy()
    original = result.columns.astype(str).str.strip()

    mapped: list[str] = []
    for col in original:
        target = COLUMN_MAPPING.get(col)
        if target is None:
            fixed = fix_mojibake(col).strip()
            target = COLUMN_MAPPING.get(fixed, fixed)
        mapped.append(target)

    result.columns = pd.Index(mapped)

    # Remove duplicatas (mantém a primeira ocorrência).
    if result.columns.duplicated().any():
        result = result.loc[:, ~result.columns.duplicated()]

    return result


def parse_coordinate(value: Any, max_abs: float) -> float:
    """Converte coordenadas em formatos decimais brasileiros e exportados.

    Trata:
        - vírgula como separador decimal ("-19,9167")
        - múltiplos pontos como separador de milhar ("-19.916.700")
        - strings vazias, "nan" e valores não numéricos (retorna ``np.nan``)
        - valores fora da faixa ``[-max_abs, max_abs]`` (retorna ``np.nan``)

    Args:
        value: Valor bruto da coordenada.
        max_abs: Limite absoluto (90 para latitude, 180 para longitude).

    Returns:
        Float dentro da faixa válida, ou ``np.nan``.
    """
    if pd.isna(value):
        return np.nan

    value_str = str(value).strip().replace(" ", "")
    if not value_str or value_str.lower() == "nan":
        return np.nan

    try:
        # Caso 1: múltiplos pontos sem vírgula (ex.: "-19.916.700").
        if value_str.count(".") > 1 and "," not in value_str:
            sign = "-" if value_str.startswith("-") else ""
            unsigned_value = value_str.lstrip("+-")
            groups = unsigned_value.split(".")
            # Posiciona o decimal após os 2 primeiros dígitos (padrão lat/lon).
            decimal_position = min(len(groups[0]), 2)
            digits = "".join(groups)
            parsed = float(f"{sign}{digits[:decimal_position]}.{digits[decimal_position:]}")
        else:
            # Caso 2: vírgula como decimal.
            parsed = float(
                value_str.replace(".", "").replace(",", ".")
                if "," in value_str
                else value_str
            )
    except (TypeError, ValueError):
        return np.nan

    return parsed if abs(parsed) <= max_abs else np.nan


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """Converte uma série textual em ``datetime64``, tolerando formatos mistos.

    Usa ``format="mixed"`` (Pandas ≥ 2.0) e ``dayfirst=True`` para acomodar
    os formatos brasileiros (DD/MM/YYYY). Timestamps em UTC são convertidos
    para naive (sem timezone) para consistência interna.

    Args:
        series: Série de strings/objetos representando datas.

    Returns:
        Série de ``datetime64[ns]`` sem timezone; valores inválidos → ``NaT``.
    """
    return pd.to_datetime(
        series,
        format="mixed",
        errors="coerce",
        dayfirst=True,
        utc=True,
    ).dt.tz_localize(None)


def extract_municipio(local: Any) -> Any:
    """Extrai o município a partir do campo ``local_do_fato``.

    Assume o formato ``"LOGRADOURO - MUNICÍPIO"``. Retorna ``np.nan`` se o
    separador não estiver presente.

    Args:
        local: Valor de ``local_do_fato``.

    Returns:
        Nome do município ou ``np.nan``.
    """
    if pd.isna(local):
        return np.nan
    parts = str(local).split(" - ")
    return parts[-1].strip() if len(parts) >= 2 else np.nan


def extrair_bbm(unidade: Any) -> str:
    """Extrai o Batalhão / Companhia Independente a partir do nome da unidade.

    Formato esperado: ``"1º BBM / 1ª CIA (BAIRRO)"``. Retorna o segmento que
    contém ``"BBM"`` ou ``"CIA IND"`` sem o sufixo entre parênteses.

    Args:
        unidade: Nome completo da unidade.

    Returns:
        Nome do BBM/CIA IND, ou ``"Outros"`` se nada for reconhecido.
    """
    if pd.isna(unidade):
        return "Outros"
    for part in str(unidade).split("/"):
        part = part.strip()
        if "BBM" in part or "CIA IND" in part:
            return part.split("(")[0].strip()
    return "Outros"


def extrair_fracao(unidade: Any) -> str:
    """Remove o bairro entre parênteses e normaliza as partes da unidade.

    Exemplo: ``"1º BBM / 1ª CIA (SAVASSI - BH)"`` → ``"1º BBM / 1ª CIA"``.

    Args:
        unidade: Nome completo da unidade.

    Returns:
        Fração/Unidade normalizada, ou ``"Outros"`` se vazio.
    """
    if pd.isna(unidade):
        return "Outros"
    text = re.sub(r"\s*\([^)]*\)", "", str(unidade).strip())
    parts = [part.strip() for part in text.split("/") if part.strip()]
    return " / ".join(parts) if parts else "Outros"


def extrair_recursos(df: pd.DataFrame) -> list[str]:
    """Lista os prefixos de viaturas/recursos únicos presentes no DataFrame.

    O campo ``Empenhos.recurso_codigo_prefixo`` pode conter múltiplos recursos
    separados por ``" / "``. Esta função explodde esses valores e retorna
    a lista ordenada e sem duplicatas.

    Args:
        df: DataFrame que pode ou não conter a coluna de recursos.

    Returns:
        Lista ordenada de prefixos; ``[]`` se a coluna não existir.
    """
    column = "Empenhos.recurso_codigo_prefixo"
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.replace(" / ", ",", regex=False)
    resources = values.str.split(",").explode().str.strip()
    return sorted(resources[resources.ne("")].unique().tolist())


def coluna_ou_none(df: pd.DataFrame, *names: str) -> str | None:
    """Retorna o primeiro nome de coluna existente em ``df``; senão ``None``.

    Útil quando o schema varia entre versões do export do CAD e queremos
    tratar múltiplas variantes sem quebrar.

    Args:
        df: DataFrame a inspecionar.
        *names: Nomes candidatos em ordem de preferência.

    Returns:
        Nome da coluna encontrada, ou ``None``.
    """
    return next((name for name in names if name in df.columns), None)


def safe_map_text(value: Any, default: str = "N/A", max_len: int | None = None) -> str:
    """Retorna texto seguro para popups de mapa (evita ``None``/``NaN``).

    Args:
        value: Valor bruto (pode ser ``NaN``, ``None``, número, etc.).
        default: Texto a usar se o valor for nulo.
        max_len: Se definido, trunca o texto ao número de caracteres.

    Returns:
        String segura para exibição em HTML.
    """
    text = default if pd.isna(value) else str(value)
    return text[:max_len] if max_len is not None else text


def detect_file_type(df: pd.DataFrame, filename: str = "") -> str:
    """Classifica o DataFrame em ``"classificadas"``, ``"ativas"`` ou ``"generico"``.

    Ordem de prioridade:
        1. Nome do arquivo contém ``"ativ"`` → ``"ativas"``.
        2. Nome do arquivo contém ``"classific"`` → ``"classificadas"``.
        3. Conteúdo de ``situacao``: valor único ``"classificada"`` →
           ``"classificadas"``; múltiplos valores → ``"ativas"``.
        4. Fallback → ``"generico"``.

    Args:
        df: DataFrame já normalizado.
        filename: Nome original do arquivo (usado como dica).

    Returns:
        Um dos três rótulos canônicos.
    """
    name = (filename or "").lower()
    if "ativ" in name:
        return "ativas"
    if "classific" in name:
        return "classificadas"

    # Inspeciona variantes do nome da coluna de situação.
    for col in ("situacao", "Situaçăo", "Situação", "Situacao", "situaçăo"):
        if col in df.columns:
            valores = (
                df[col].dropna().astype(str).str.strip().str.casefold().unique()
            )
            if len(valores) == 0:
                continue
            if len(valores) == 1 and valores[0] == "classificada":
                return "classificadas"
            if len(valores) > 1:
                return "ativas"
    return "generico"