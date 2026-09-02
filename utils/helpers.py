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
    """Converte coordenada decimal ou DMS, descartando valores impossiveis."""
    if pd.isna(value):
        return np.nan

    text = str(value).strip().upper()
    if not text:
        return np.nan

    direction_match = re.search(r"([NSEW])\s*$", text)
    direction = direction_match.group(1) if direction_match else ""
    if direction_match:
        text = text[: direction_match.start()].strip()

    negative = text.startswith("-") or direction in ("S", "W")
    text = text.lstrip("+-").strip().replace(",", ".")

    try:
        dms_match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*[°º]\s*"
            r"(\d+(?:\.\d+)?)?\s*[\'′m]?\s*"
            r"(\d+(?:\.\d+)?)?\s*[\"″s]?",
            text,
        )
        if dms_match and any(dms_match.groups()[1:]):
            degrees = float(dms_match.group(1))
            minutes = float(dms_match.group(2) or 0)
            seconds = float(dms_match.group(3) or 0)
            if minutes >= 60 or seconds >= 60:
                return np.nan
            parsed = degrees + minutes / 60 + seconds / 3600
        else:
            parsed = float(text)
    except (TypeError, ValueError):
        return np.nan

    parsed = -abs(parsed) if negative else parsed
    return parsed if abs(parsed) <= max_abs else np.nan


def parse_datetime_series(series: pd.Series) -> pd.Series:
    """Tenta os formatos conhecidos e depois o parser flexivel do pandas."""
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    for date_format in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        missing = result.isna()
        if missing.any():
            result.loc[missing] = pd.to_datetime(
                series.loc[missing], format=date_format, errors="coerce", dayfirst=True
            )
    missing = result.isna()
    if missing.any():
        result.loc[missing] = pd.to_datetime(
            series.loc[missing], errors="coerce", dayfirst=True
        )
    return result


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
