"""Leitura e processamento inicial dos arquivos do dashboard."""

import io
from typing import Any

import chardet
import numpy as np
import pandas as pd
import streamlit as st
from openpyxl import load_workbook

from utils.helpers import COLUMN_MAPPING, normalize_column_names, parse_coordinate, parse_datetime_series


def read_uploaded_file(uploaded_file: Any) -> pd.DataFrame:
    """Le CSV ou XLSX usando o conteudo do upload, sem cachear o objeto recebido."""
    raw = uploaded_file.getvalue()
    filename = uploaded_file.name.lower().strip()
    is_excel = filename.endswith((".xlsx", ".xlsm", ".xslx")) or raw[:4] == b"PK\x03\x04"
    if is_excel:
        return normalize_column_names(_read_excel_with_openpyxl(raw))

    detected = chardet.detect(raw[:100_000]).get("encoding") or "utf-8"
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


def _read_excel_with_openpyxl(raw: bytes) -> pd.DataFrame:
    """Le planilhas Excel mesmo quando o cabecalho ocupa uma linha irregular."""
    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        worksheet = next(
            (sheet for sheet in workbook.worksheets if sheet.max_row and sheet.max_column),
            None,
        )
        if worksheet is None:
            return pd.DataFrame()

        rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
        width = max((len(row) for row in rows), default=0)
        rows = [row + [None] * (width - len(row)) for row in rows]
        header_index = max(
            range(len(rows)),
            key=lambda index: sum(
                str(value).strip() in COLUMN_MAPPING for value in rows[index] if value is not None
            ),
            default=0,
        )
        header = [str(value).strip() if value is not None and str(value).strip() else f"coluna_{index + 1}"
                  for index, value in enumerate(rows[header_index])]
        data = rows[header_index + 1:]
        return pd.DataFrame(data, columns=header)
    except Exception as error:
        raise ValueError(f"Excel nao pode ser lido: {error}") from error


def _numeric_coordinates(series: pd.Series, max_abs: float) -> pd.Series:
    numeric = pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce")
    fallback = numeric.isna() & series.notna()
    if fallback.any():
        numeric.loc[fallback] = series.loc[fallback].map(
            lambda value: parse_coordinate(value, max_abs)
        )
    return numeric.where(numeric.abs().le(max_abs))


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

    if "data_hora_situacao_atual" in result.columns:
        result["data_hora_fim"] = parse_datetime_series(result["data_hora_situacao_atual"])
    else:
        result["data_hora_fim"] = pd.NaT
    return result


def load_uploaded_data(uploaded_file: Any) -> pd.DataFrame:
    return process_dataframe(read_uploaded_file(uploaded_file))


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
