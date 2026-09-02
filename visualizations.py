"""Graficos e mapa padronizados do dashboard."""

import folium
import pandas as pd
import plotly.express as px
from folium.plugins import MarkerCluster

from utils.helpers import safe_map_text


def plot_bar(df, x, y, title, top_n=None):
    data = df.head(top_n) if top_n else df
    return px.bar(data, x=x, y=y, title=title, labels={x: "", y: "Chamadas"}, template="plotly_white")


def plot_line(df, x, y, color, title):
    return px.line(df, x=x, y=y, color=color, title=title, template="plotly_white")


def plot_histogram(df, x, title, **kwargs):
    return px.histogram(df, x=x, title=title, template="plotly_white", **kwargs)


def create_occurrence_map(map_df: pd.DataFrame, sample_size: int, group_by_municipality: bool):
    latitude = "Chamada_atendimentos.local_latitude"
    longitude = "Chamada_atendimentos.local_longitude"
    center = [map_df[latitude].mean(), map_df[longitude].mean()]
    selected = map_df.sample(sample_size, random_state=42) if len(map_df) > sample_size else map_df
    map_view = folium.Map(location=center, zoom_start=9, tiles="OpenStreetMap", control_scale=True)

    if group_by_municipality:
        grouped = selected.dropna(subset=["Chamada_atendimentos.local_municipio_nome"]).groupby(
            "Chamada_atendimentos.local_municipio_nome", as_index=False
        ).agg(latitude=(latitude, "mean"), longitude=(longitude, "mean"), ocorrencias=(latitude, "size"))
        for _, row in grouped.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]], radius=max(5, min(30, row["ocorrencias"] ** 0.5 * 2)),
                popup=f"<b>{row['Chamada_atendimentos.local_municipio_nome']}</b><br>Ocorrencias: {row['ocorrencias']}",
                color="#d62728", fill=True, fill_opacity=0.65,
            ).add_to(map_view)
    else:
        cluster = MarkerCluster().add_to(map_view)
        for _, row in selected.iterrows():
            municipality = safe_map_text(row.get("Chamada_atendimentos.local_municipio_nome"))
            nature = safe_map_text(row.get("Chamada_atendimentos.natureza_descricao"))
            local = safe_map_text(row.get("Chamada_atendimentos.local_do_fato"))
            popup = f"<b>📍 {municipality}</b><br><b>Natureza:</b> {nature}<br><b>Local:</b> {local}"
            folium.Marker(
                location=[row[latitude], row[longitude]], popup=folium.Popup(popup, max_width=300),
                tooltip=f"{municipality} - {safe_map_text(nature, 'N/A', 30)}...",
            ).add_to(cluster)
    return map_view, len(selected)
