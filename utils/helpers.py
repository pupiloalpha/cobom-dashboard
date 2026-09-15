"""Funcoes puras para normalizacao e enriquecimento dos dados do COBOM."""

import re
from typing import Any

import numpy as np
import pandas as pd


COLUMN_MAPPING = {
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

# Mapa de mojibake -> caracteres originais.
# Ocorre quando o export e gerado em CP1252 e lido como UTF-8 (ou vice-versa),
# transformando 'º'->'ş', 'ã'->'ă', 'Ã'->'Ă', 'Ç'->'Ţ', 'É'->'Ę', etc.
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
    """Reverte caracteres corrompidos por encoding mismatch em exports do CAD."""
    if text is None:
        return ""
    return str(text).translate(_MOJIBAKE_MAP)


NATUREZA_GRUPOS = {
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


# Situacoes que ENCERRAM o ciclo operacional.
#
# IMPORTANTE: no CAD, APENAS "Classificada" retira a chamada da tela do
# despachante. Todos os demais valores (Terminada, Atribuída ao órgão,
# Em controle, Em direção, À caminho, No local, Despachada, Em retorno,
# Suspensa, Nada constatado, Teste, RAT, Duplicada, Dispensada pelo
# solicitante, Solicitante não encontrado, Não atendida: falta de viatura/
# efetivo, Atendida pelo SAMU, Repassada a outros órgãos, Ocorrências
# típicas de bombeiros atendida por outros órgãos, Orientação, Orientação
# da regulação médica) mantêm a chamada ATIVA no sistema.
#
# Portanto: chamadas com qualquer situação diferente de "Classificada"
# recebem now() como data_hora_fim e o tempo decorrido é exibido como
# tempo de atendimento em andamento.
SITUACOES_TERMINAIS = {"classificada"}


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza nomes de colunas; tolerante a cabecalhos com mojibake.

    Estrategia por coluna:
    1. Tenta mapeamento direto em COLUMN_MAPPING.
    2. Se nao casar, aplica fix_mojibake e tenta novamente.
    3. Se ainda nao casar, mantem o nome (apenas com mojibake revertido).
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
    if result.columns.duplicated().any():
        result = result.loc[:, ~result.columns.duplicated()]
    return result


def parse_coordinate(value: Any, max_abs: float) -> float:
    """Converte coordenadas em formatos decimais brasileiros e exportados."""
    if pd.isna(value):
        return np.nan
    value_str = str(value).strip().replace(" ", "")
    if not value_str or value_str.lower() == "nan":
        return np.nan
    try:
        if value_str.count(".") > 1 and "," not in value_str:
            sign = "-" if value_str.startswith("-") else ""
            unsigned_value = value_str.lstrip("+-")
            groups = unsigned_value.split(".")
            decimal_position = min(len(groups[0]), 2)
            digits = "".join(groups)
            parsed = float(f"{sign}{digits[:decimal_position]}.{digits[decimal_position:]}")
        else:
            parsed = float(
                value_str.replace(".", "").replace(",", ".")
                if "," in value_str
                else value_str
            )
    except (TypeError, ValueError):
        return np.nan
    return parsed if abs(parsed) <= max_abs else np.nan


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """Tenta os formatos conhecidos e depois o parser flexivel do pandas."""
    return pd.to_datetime(
        series,
        format="mixed",
        errors="coerce",
        dayfirst=True,
        utc=True,
    ).dt.tz_localize(None)


def extract_municipio(local: Any) -> Any:
    if pd.isna(local):
        return np.nan
    parts = str(local).split(" - ")
    return parts[-1].strip() if len(parts) >= 2 else np.nan


def extrair_bbm(unidade: Any) -> str:
    if pd.isna(unidade):
        return "Outros"
    for part in str(unidade).split("/"):
        part = part.strip()
        if "BBM" in part or "CIA IND" in part:
            return part.split("(")[0].strip()
    return "Outros"


def extrair_fracao(unidade: Any) -> str:
    if pd.isna(unidade):
        return "Outros"
    text = re.sub(r"\s*\([^)]*\)", "", str(unidade).strip())
    parts = [part.strip() for part in text.split("/") if part.strip()]
    return " / ".join(parts) if parts else "Outros"


def extrair_recursos(df: pd.DataFrame) -> list[str]:
    column = "Empenhos.recurso_codigo_prefixo"
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.replace(" / ", ",", regex=False)
    resources = values.str.split(",").explode().str.strip()
    return sorted(resources[resources.ne("")].unique().tolist())


def coluna_ou_none(df: pd.DataFrame, *names: str) -> str | None:
    return next((name for name in names if name in df.columns), None)


def safe_map_text(value: Any, default: str = "N/A", max_len: int | None = None) -> str:
    text = default if pd.isna(value) else str(value)
    return text[:max_len] if max_len is not None else text


def detect_file_type(df: pd.DataFrame, filename: str = "") -> str:
    """Identifica se o DataFrame veio de um export 'classificadas', 'ativas' ou outro.

    Prioridade:
    1) Nome do arquivo (contem 'ativ' ou 'classific').
    2) Conteudo da coluna `situacao`: um unico valor == 'classificada' ->
       'classificadas'; multiplos valores -> 'ativas'.
    3) Fallback: 'generico'.
    """
    name = (filename or "").lower()
    if "ativ" in name:
        return "ativas"
    if "classific" in name:
        return "classificadas"

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