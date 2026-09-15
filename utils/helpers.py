"""Funcoes puras para normalizacao e enriquecimento dos dados do COBOM."""

import re
from typing import Any

import numpy as np
import pandas as pd


# Mapeamento de cabecalhos do CAD para nomes internos.
# Inclui aliases para o cabecalho com mojibake (encoding corrompido)
# que aparece em alguns exports (ex.: "Nş chamada", "Situaçăo").
COLUMN_MAPPING = {
    "Nº chamada": "chamada_numero",
    "Nş chamada": "chamada_numero",
    "Nº REDS": "reds",
    "Nş REDS": "reds",
    "Data/hora de criação": "data_hora_criacao",
    "Data/hora de criaçăo": "data_hora_criacao",
    "Local do fato": "Chamada_atendimentos.local_do_fato",
    "Latitude  do local": "Chamada_atendimentos.local_latitude",
    "Longitude do local": "Chamada_atendimentos.local_longitude",
    "Natureza": "Chamada_atendimentos.natureza_descricao",
    "Unidade Responsável": "Chamada_atendimentos.unidade_servico_nome",
    "Recursos empenhados": "Empenhos.recurso_codigo_prefixo",
    "Alerta": "alerta",
    "Destaque": "destaque",
    "Envolve autoridade": "envolve_autoridade",
    "Tipo de classificação": "Chamada_atendimentos.chamada_classificacao_descricao",
    "Tipo de classificaçăo": "Chamada_atendimentos.chamada_classificacao_descricao",
    "Situação": "situacao",
    "Situaçăo": "situacao",
    "Data/hora da situação atual": "data_hora_situacao_atual",
    "Data/hora da situaçăo atual": "data_hora_situacao_atual",
    "Evento associado": "evento_associado",
}


# Grupos tematicos derivados do primeiro caractere do codigo da natureza.
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


# Situacoes que representam encerramento do ciclo operacional.
# Chamadas fora desta lista sao tratadas como "em andamento" e usam now()
# como referencia para o tempo decorrido.
SITUACOES_TERMINAIS = {
    "classificada",
    "terminada",
    "suspensa",
    "nada constatado",
    "cancelada pelo coordenador do cobom",
    "cancelada por ordem do orgao de coordenacao e controle",
    "atribuída ao órgão",
    "atribuida ao orgao",
    "duplicada",
    "dispensada pelo solicitante",
    "solicitante não encontrado",
    "solicitante nao encontrado",
    "nao atendida: falta de viatura",
    "nao atendida: falta de efetivo",
    "não atendida: falta de viatura",
    "não atendida: falta de efetivo",
    "atendida pelo samu",
    "repassada a outros orgaos",
    "repassada a outros órgãos",
    "ocorrências típicas de bombeiros atendida por outros órgãos",
    "ocorrencias tipicas de bombeiros atendida por outros orgaos",
    "orientação",
    "orientacao",
    "orientação da regulação médica",
    "orientacao da regulacao medica",
    "teste",
    "rat",
}


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Retorna uma copia com nomes de colunas padronizados."""
    result = df.copy()
    result.columns = result.columns.astype(str).str.strip()
    result = result.rename(columns=COLUMN_MAPPING)
    # Remove colunas duplicadas geradas por aliases coincidentes
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

    Estrategia:
    1) Pelo nome do arquivo, se contiver pistas textuais.
    2) Pela cardinalidade e conteudo da coluna `situacao`.
    """
    name = (filename or "").lower()
    if "ativ" in name:
        return "ativas"
    if "classific" in name:
        return "classificadas"

    for col in ("situacao", "Situaçăo", "Situação", "Situaçăo"):
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