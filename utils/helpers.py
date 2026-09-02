"""Funcoes puras para normalizacao e enriquecimento dos dados do COBOM."""

import re
from typing import Any

import numpy as np
import pandas as pd


COLUMN_MAPPING = {
    "Nº chamada": "chamada_numero",
    "Nº REDS": "reds",
    "Data/hora de criação": "data_hora_criacao",
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
    "Situação": "situacao",
    "Data/hora da situação atual": "data_hora_situacao_atual",
    "Evento associado": "evento_associado",
}


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Retorna uma copia com nomes de colunas padronizados."""
    result = df.copy()
    result.columns = result.columns.astype(str).str.strip()
    return result.rename(columns=COLUMN_MAPPING)


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
