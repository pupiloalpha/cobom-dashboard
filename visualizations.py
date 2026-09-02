"""Graficos e mapa padronizados do dashboard."""

import folium
import plotly.graph_objects as go
import pandas as pd
import plotly.express as px
from folium.plugins import MarkerCluster
from plotly.subplots import make_subplots

from utils.helpers import safe_map_text


def plot_bar(df, x, y, title, top_n=None):
    data = df.head(top_n) if top_n else df
    return px.bar(data, x=x, y=y, title=title, labels={x: "", y: "Chamadas"}, template="plotly_white")


def plot_line(df, x, y, color, title):
    return px.line(df, x=x, y=y, color=color, title=title, template="plotly_white")


def plot_histogram(df, x, title, **kwargs):
    return px.histogram(df, x=x, title=title, template="plotly_white", **kwargs)


def plot_resource_concentration(df: pd.DataFrame, top_n: int = 30):
    """Exibe os chamados com mais recursos e a concentração acumulada."""
    call_column = "chamada_numero"
    resource_column = "Empenhos.recurso_codigo_prefixo"
    if call_column not in df.columns or resource_column not in df.columns:
        return None

    calls = df[[call_column]].copy()
    calls[call_column] = calls[call_column].astype("string").str.strip()
    calls = calls[calls[call_column].notna() & calls[call_column].ne("")].drop_duplicates()
    resources = df[[call_column, resource_column]].copy()
    resources[call_column] = resources[call_column].astype("string").str.strip()
    resources[resource_column] = (
        resources[resource_column].fillna("").astype(str).str.replace(" / ", ",", regex=False)
    )
    resources = resources.assign(recurso=resources[resource_column].str.split(",")).explode("recurso")
    resources["recurso"] = resources["recurso"].astype("string").str.strip()
    resources = resources[resources["recurso"].notna() & resources["recurso"].ne("")]
    counts = resources.groupby(call_column).size().rename("recursos").reset_index()
    counts = calls.merge(counts, on=call_column, how="left").fillna({"recursos": 0})
    counts = counts.sort_values(["recursos", call_column], ascending=[False, True]).reset_index(drop=True)
    if counts.empty:
        return None

    counts["ordem"] = counts.index + 1
    total_resources = counts["recursos"].sum()
    counts["concentracao_acumulada"] = (
        counts["recursos"].cumsum().div(total_resources).mul(100) if total_resources else 0
    )
    visible = counts.head(top_n)
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=visible["ordem"], y=visible["recursos"],
            customdata=visible[[call_column]],
            hovertemplate="Chamada %{customdata[0]}<br>Recursos: %{y}<extra></extra>",
            name="Recursos por chamada",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=visible["ordem"], y=visible["concentracao_acumulada"],
            mode="lines+markers", name="Concentração acumulada (%)",
            hovertemplate="Top %{x}<br>Concentração: %{y:.1f}%<extra></extra>",
            line={"color": "#d62728", "width": 2},
        ),
        secondary_y=True,
    )
    figure.update_layout(
        title=f"Concentração de recursos por chamada (top {min(top_n, len(counts))})",
        template="plotly_white", hovermode="x unified",
        margin={"l": 50, "r": 50, "t": 70, "b": 50},
    )
    figure.update_xaxes(title_text="Posição da chamada no ranking")
    figure.update_yaxes(title_text="Quantidade de recursos", secondary_y=False)
    figure.update_yaxes(title_text="Recursos acumulados (%)", range=[0, 100], secondary_y=True)
    return figure


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
