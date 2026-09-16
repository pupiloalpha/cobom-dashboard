"""
Gráficos e mapas padronizados do dashboard COBOM-BH.

Este módulo encapsula TODAS as visualizações Plotly e Folium usadas no
``app.py``. Cada função recebe DataFrames já enriquecidos (saída de
``data_loader.process_dataframe``) e retorna objetos de figura prontos
para ``st.plotly_chart`` / ``st_folium``.

Convenções:
    - Fundo transparente em todos os gráficos (``_apply_theme_layout``),
      para integração automática com modo claro/escuro do Streamlit.
    - Rótulos em português brasileiro via ``DEFAULT_PT_LABELS``.
    - Funções retornam ``None`` quando não há dados suficientes — o
      chamador deve tratar exibindo mensagem informativa.
"""

from __future__ import annotations

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from folium.plugins import HeatMap, MarkerCluster
from plotly.subplots import make_subplots

from utils.helpers import safe_map_text


# ---------------------------------------------------------------------------
# RÓTULOS PADRÃO (PT-BR)
# ---------------------------------------------------------------------------
# Mapeia nomes técnicos de colunas → rótulos amigáveis exibidos nos eixos,
# legendas e tooltips. Sobrescrevível por chamada via argumento ``labels``.
# ---------------------------------------------------------------------------
DEFAULT_PT_LABELS: dict[str, str] = {
    "count": "Nº de Chamadas",
    "contagem": "Nº de Chamadas",
    "chamadas": "Nº de Chamadas",
    "recursos": "Quantidade de Recursos",
    "hora": "Hora do Dia",
    "dia": "Dia da Semana",
    "mes": "Mês",
    "ano": "Ano",
    "data": "Data",
    "periodo_str": "Período (Ano-Mês)",
    "tipo": "Tipo de Registro",
    "categoria": "Faixa de Duração",
    "tempo_horas": "Tempo de Atendimento (horas)",
    "dias": "Duração (dias)",
    "prefixo": "Prefixo da Viatura",
    "bbm": "Batalhão / Companhia",
    "fracao": "Fração / Unidade",
    "Chamada_atendimentos.local_municipio_nome": "Município",
    "Chamada_atendimentos.natureza_descricao": "Natureza da Ocorrência",
    "Chamada_atendimentos.local_do_fato": "Logradouro / Endereço",
    "Chamada_atendimentos.chamada_classificacao_descricao": "Classificação",
}


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================
def _apply_theme_layout(fig):
    """Aplica fundo transparente e margens consistentes a uma figura Plotly.

    Args:
        fig: Figura Plotly (Express ou Graph Objects).

    Returns:
        A mesma figura com layout ajustado.
    """
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=30, t=50, b=40),
    )
    return fig


# ===========================================================================
# GRÁFICOS GENÉRICOS (barras, linhas, histogramas)
# ===========================================================================
def plot_bar(df, x, y, title, top_n=None, labels=None):
    """Gráfico de barras verticais com suporte a Top-N.

    Args:
        df: DataFrame com os dados.
        x: Coluna para o eixo X (categorias).
        y: Coluna para o eixo Y (valores).
        title: Título do gráfico.
        top_n: Limita ao Top-N registros (aplicado antes do plot).
        labels: Sobrescreve rótulos em ``DEFAULT_PT_LABELS``.

    Returns:
        Figura Plotly Express.
    """
    data = df.head(top_n) if top_n else df
    combined_labels = {**DEFAULT_PT_LABELS, **(labels or {}), x: "", y: "Nº de Chamadas"}
    fig = px.bar(data, x=x, y=y, title=title, labels=combined_labels)
    fig.update_layout(xaxis_title="", yaxis_title="Nº de Chamadas")
    return _apply_theme_layout(fig)


def plot_line(df, x, y, color, title, labels=None):
    """Gráfico de linhas com coloração opcional por coluna.

    Args:
        df: DataFrame com os dados.
        x: Coluna do eixo X (temporal ou ordinal).
        y: Coluna do eixo Y (valores).
        color: Coluna de agrupamento/coloração (``None`` para linha única).
        title: Título.
        labels: Sobrescreve rótulos.

    Returns:
        Figura Plotly Express.
    """
    combined_labels = {**DEFAULT_PT_LABELS, **(labels or {})}
    fig = px.line(df, x=x, y=y, color=color, title=title, labels=combined_labels)
    return _apply_theme_layout(fig)


def plot_histogram(df, x, title, labels=None, **kwargs):
    """Histograma com kwargs repassados ao Plotly Express.

    Args:
        df: DataFrame com os dados.
        x: Coluna a histogramar.
        title: Título.
        labels: Sobrescreve rótulos.
        **kwargs: Repassados a ``px.histogram`` (ex.: ``nbins``, ``color``,
            ``barmode``).

    Returns:
        Figura Plotly Express.
    """
    combined_labels = {**DEFAULT_PT_LABELS, **(labels or {})}
    fig = px.histogram(df, x=x, title=title, labels=combined_labels, **kwargs)
    fig.update_layout(yaxis_title="Nº de Chamadas")
    return _apply_theme_layout(fig)


# ===========================================================================
# GRÁFICOS ESPECÍFICOS DO DOMÍNIO
# ===========================================================================
def plot_resource_concentration(df: pd.DataFrame, top_n: int = 30):
    """Exibe os chamados com mais recursos e a concentração acumulada (Pareto).

    Combina:
        - Barras: quantidade de recursos por chamada (ordenadas desc).
        - Linha (eixo secundário): percentual acumulado de recursos.

    Args:
        df: DataFrame enriquecido.
        top_n: Número de chamadas a exibir (Top-N).

    Returns:
        Figura Plotly ou ``None`` se colunas essenciais faltarem.
    """
    call_column = "chamada_numero"
    resource_column = "Empenhos.recurso_codigo_prefixo"
    if call_column not in df.columns or resource_column not in df.columns:
        return None

    # Universo de chamadas (deduplicado).
    calls = df[[call_column]].copy()
    calls[call_column] = calls[call_column].astype("string").str.strip()
    calls = calls[calls[call_column].notna() & calls[call_column].ne("")].drop_duplicates()

    # Explode recursos multi-valor em linhas individuais.
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

    # Barras + linha em eixos duplos.
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=visible["ordem"],
            y=visible["recursos"],
            customdata=visible[[call_column]],
            hovertemplate="Chamada nº %{customdata[0]}<br>Viaturas/Recursos: <b>%{y}</b><extra></extra>",
            name="Recursos por Chamada",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=visible["ordem"],
            y=visible["concentracao_acumulada"],
            mode="lines+markers",
            name="Concentração Acumulada (%)",
            hovertemplate="Posição no Ranking: %{x}º<br>Concentração Acumulada: <b>%{y:.1f}%</b><extra></extra>",
            line={"color": "#d62728", "width": 2},
        ),
        secondary_y=True,
    )
    figure.update_layout(
        title=f"Concentração de Recursos por Chamada (Top {min(top_n, len(counts))})",
        hovermode="x unified",
        margin={"l": 50, "r": 50, "t": 70, "b": 50},
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    figure.update_xaxes(title_text="Posição da Chamada no Ranking de Recursos")
    figure.update_yaxes(title_text="Quantidade de Recursos Empenhados", secondary_y=False)
    figure.update_yaxes(title_text="Recursos Acumulados (%)", range=[0, 100], secondary_y=True)
    return _apply_theme_layout(figure)


def plot_hourly_weekday_heatmap(df: pd.DataFrame):
    """Gera matriz de calor 2D (24h × 7 dias) para planejamento operacional.

    Args:
        df: DataFrame enriquecido (deve conter ``hora`` e ``dia_semana``).

    Returns:
        Figura Plotly com heatmap, ou ``None`` se dados insuficientes.
    """
    if "hora" not in df.columns or "dia_semana" not in df.columns:
        return None

    valid = df.dropna(subset=["hora", "dia_semana"]).copy()
    if valid.empty:
        return None

    valid["hora"] = valid["hora"].astype(int)
    valid["dia_semana"] = valid["dia_semana"].astype(int)

    day_names = [
        "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
        "Sexta-feira", "Sábado", "Domingo",
    ]
    hours = list(range(24))

    # Pivot: linhas = dias, colunas = horas.
    pivot = (
        valid.groupby(["dia_semana", "hora"])
        .size()
        .unstack(level="hora", fill_value=0)
        .reindex(index=range(7), columns=hours, fill_value=0)
    )

    total_calls = pivot.values.sum()
    pct_matrix = (
        (pivot.values / total_calls * 100) if total_calls > 0 else np.zeros_like(pivot.values)
    )

    # Texto customizado de hover com contagem absoluta + percentual.
    hover_text = [
        [
            f"<b>{day_names[d]} às {h:02d}:00</b><br>"
            f"Chamadas: <b>{pivot.values[d, h]:,}</b><br>"
            f"Percentual do total: <b>{pct_matrix[d, h]:.2f}%</b>"
            for h in hours
        ]
        for d in range(7)
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{h:02d}h" for h in hours],
            y=day_names,
            hoverongaps=False,
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
            colorscale="YlOrRd",
            colorbar=dict(title="Nº Chamadas"),
        )
    )

    fig.update_layout(
        title="🔥 Matriz Operacional de Plantão: Volume de Chamadas (Hora do Dia × Dia da Semana)",
        xaxis=dict(title="Hora do Dia (00h às 23h)", tickmode="linear"),
        yaxis=dict(title="Dia da Semana", categoryorder="array", categoryarray=day_names[::-1]),
        height=420,
        margin={"l": 80, "r": 40, "t": 60, "b": 50},
    )
    return _apply_theme_layout(fig)


def plot_situacao_operacional(df: pd.DataFrame):
    """Distribuição das situações operacionais (rosca). Útil para ativas.

    Args:
        df: DataFrame enriquecido (deve conter ``situacao_norm``).

    Returns:
        Figura Plotly ou ``None`` se dados insuficientes.
    """
    if "situacao_norm" not in df.columns:
        return None
    base = (
        df["situacao_norm"].dropna().astype(str).str.strip()
        .value_counts().rename_axis("situacao").reset_index(name="chamadas")
    )
    if base.empty:
        return None
    fig = px.pie(
        base, names="situacao", values="chamadas",
        title="Distribuição por Situação Operacional",
        hole=0.45,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return _apply_theme_layout(fig)


def plot_flags_overview(df: pd.DataFrame):
    """Comparativo das três flags operacionais (Alerta, Destaque, Autoridade).

    Args:
        df: DataFrame enriquecido com ``*_flag``.

    Returns:
        Figura Plotly ou ``None`` se nenhuma flag existir.
    """
    registros = []
    for col, rotulo in (
        ("alerta_flag", "Alerta"),
        ("destaque_flag", "Destaque"),
        ("envolve_autoridade_flag", "Envolve Autoridade"),
    ):
        if col not in df.columns:
            continue
        serie = df[col].fillna(False).astype(bool)
        registros.append({"categoria": rotulo, "tipo": "Sim", "chamadas": int(serie.sum())})
        registros.append({"categoria": rotulo, "tipo": "Não", "chamadas": int((~serie).sum())})
    if not registros:
        return None
    fig = px.bar(
        pd.DataFrame(registros), x="categoria", y="chamadas", color="tipo",
        barmode="group",
        title="Sinalizações Operacionais (Alerta, Destaque, Autoridade)",
        color_discrete_map={"Sim": "#d62728", "Não": "#9aa0a6"},
    )
    fig.update_layout(xaxis_title="", yaxis_title="Nº de Chamadas")
    return _apply_theme_layout(fig)


def plot_flags_temporal(df: pd.DataFrame, freq: str = "MS"):
    """Evolução temporal das flags ativas (resample mensal ou diário).

    Args:
        df: DataFrame enriquecido.
        freq: Frequência do ``resample`` Pandas (``"MS"`` mensal, ``"D"`` diário).

    Returns:
        Figura Plotly ou ``None`` se dados insuficientes.
    """
    if "chamada_data_inclusao" not in df.columns:
        return None
    flags = [c for c in ("alerta_flag", "destaque_flag", "envolve_autoridade_flag") if c in df.columns]
    if not flags:
        return None
    base = df.set_index("chamada_data_inclusao")[flags].resample(freq).sum().reset_index()
    melted = base.melt(id_vars="chamada_data_inclusao", var_name="flag", value_name="chamadas")
    rotulos = {
        "alerta_flag": "Alerta",
        "destaque_flag": "Destaque",
        "envolve_autoridade_flag": "Envolve Autoridade",
    }
    melted["flag"] = melted["flag"].map(rotulos)
    fig = px.line(
        melted, x="chamada_data_inclusao", y="chamadas", color="flag",
        title="Evolução Temporal das Sinalizações Operacionais", markers=True,
    )
    fig.update_layout(xaxis_title="Período", yaxis_title="Nº de Chamadas")
    return _apply_theme_layout(fig)


def plot_natureza_grupos(df: pd.DataFrame):
    """Ranking por grupo temático da natureza (APH, incêndio, salvamento...).

    Args:
        df: DataFrame enriquecido com ``natureza_grupo``.

    Returns:
        Figura Plotly ou ``None`` se dados insuficientes.
    """
    if "natureza_grupo" not in df.columns:
        return None
    base = (
        df["natureza_grupo"].dropna()
        .value_counts().rename_axis("grupo").reset_index(name="chamadas")
    )
    if base.empty:
        return None
    fig = px.bar(
        base, x="chamadas", y="grupo", orientation="h",
        title="Chamadas por Grupo Temático de Natureza",
        color="chamadas", color_continuous_scale="Reds",
    )
    fig.update_layout(
        yaxis_title="", xaxis_title="Nº de Chamadas",
        coloraxis_showscale=False,
    )
    fig.update_yaxes(categoryorder="total ascending")
    return _apply_theme_layout(fig)


def plot_prioridade(df: pd.DataFrame):
    """Distribuição por prioridade da natureza (1, 2, 3).

    Args:
        df: DataFrame enriquecido com ``natureza_prioridade``.

    Returns:
        Figura Plotly ou ``None`` se dados insuficientes.
    """
    if "natureza_prioridade" not in df.columns:
        return None
    base = (
        df["natureza_prioridade"].dropna().astype(int)
        .value_counts().sort_index()
        .rename_axis("prioridade").reset_index(name="chamadas")
    )
    if base.empty:
        return None
    mapa = {1: "1 - Alta", 2: "2 - Média", 3: "3 - Baixa"}
    base["prioridade"] = base["prioridade"].map(mapa)
    fig = px.bar(
        base, x="prioridade", y="chamadas", color="prioridade",
        title="Distribuição por Prioridade da Ocorrência",
        color_discrete_map={
            "1 - Alta": "#d62728",
            "2 - Média": "#ff9800",
            "3 - Baixa": "#4caf50",
        },
    )
    fig.update_layout(xaxis_title="", yaxis_title="Nº de Chamadas", showlegend=False)
    return _apply_theme_layout(fig)


def plot_reds_origem(df: pd.DataFrame):
    """Distribuição por origem do REDS (PM, BM, multiagência).

    Args:
        df: DataFrame enriquecido com ``reds_origem``.

    Returns:
        Figura Plotly ou ``None`` se dados insuficientes.
    """
    if "reds_origem" not in df.columns:
        return None
    base = (
        df["reds_origem"].fillna("Sem REDS")
        .value_counts().rename_axis("origem").reset_index(name="chamadas")
    )
    if base.empty:
        return None
    fig = px.pie(
        base, names="origem", values="chamadas",
        title="Origem do REDS (Agência Solicitante)", hole=0.45,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return _apply_theme_layout(fig)


def plot_tempo_por_situacao(df: pd.DataFrame, min_registros: int = 3):
    """Boxplot do tempo decorrido por situação (SLA por estado operacional).

    Args:
        df: DataFrame enriquecido com ``situacao_norm`` e ``tempo_no_estado_horas``.
        min_registros: Mínimo de registros por situação para entrar no plot.

    Returns:
        Figura Plotly ou ``None`` se dados insuficientes.
    """
    if "situacao_norm" not in df.columns or "tempo_no_estado_horas" not in df.columns:
        return None
    validos = df.dropna(subset=["situacao_norm", "tempo_no_estado_horas"]).copy()
    if validos.empty:
        return None
    contagem = validos["situacao_norm"].value_counts()
    validos = validos[validos["situacao_norm"].isin(contagem[contagem >= min_registros].index)]
    if validos.empty:
        return None
    fig = px.box(
        validos, x="situacao_norm", y="tempo_no_estado_horas",
        title="Tempo no Estado Atual por Situação Operacional",
        points="outliers",
    )
    fig.update_layout(xaxis_title="", yaxis_title="Tempo (horas)")
    return _apply_theme_layout(fig)


# ===========================================================================
# MAPA FOLIUM
# ===========================================================================
def create_occurrence_map(
    map_df: pd.DataFrame,
    sample_size: int,
    mode_or_group: str | bool = "cluster",
):
    """Cria mapa Folium com três modos de camada.

    Modos suportados:
        - ``"cluster"``: ``MarkerCluster`` com popup por ocorrência.
        - ``"heatmap"``: mancha de calor via ``HeatMap`` (KDE espacial).
        - ``"grouped"``: ``CircleMarker`` por município, com raio proporcional
          ao número de ocorrências.

    Compatibilidade retroativa: aceitar ``bool`` (``True`` → ``"grouped"``,
    ``False`` → ``"cluster"``).

    Args:
        map_df: DataFrame com coordenadas válidas.
        sample_size: Número de pontos a exibir (amostragem aleatória).
        mode_or_group: Modo (str) ou bool legado.

    Returns:
        Tupla ``(folium.Map, n_pontos_exibidos)``.
    """
    latitude = "Chamada_atendimentos.local_latitude"
    longitude = "Chamada_atendimentos.local_longitude"

    # Centro do mapa pela média das coordenadas válidas.
    center = [float(map_df[latitude].mean()), float(map_df[longitude].mean())]

    # Amostragem determinística para estabilidade visual.
    selected = (
        map_df.sample(sample_size, random_state=42)
        if len(map_df) > sample_size
        else map_df
    )
    map_view = folium.Map(
        location=center, zoom_start=10, tiles="OpenStreetMap", control_scale=True
    )

    # Compatibilidade com assinatura antiga (bool).
    if isinstance(mode_or_group, bool):
        mode = "grouped" if mode_or_group else "cluster"
    else:
        mode = mode_or_group

    if mode == "heatmap":
        heat_data = selected[[latitude, longitude]].dropna().values.tolist()
        HeatMap(
            heat_data,
            radius=16,
            blur=20,
            min_opacity=0.35,
            max_zoom=14,
            gradient={0.2: "blue", 0.4: "cyan", 0.6: "lime", 0.8: "yellow", 1.0: "red"},
        ).add_to(map_view)

    elif mode == "grouped":
        # Agrega por município; raio ~ sqrt(ocorrências).
        grouped = (
            selected.dropna(subset=["Chamada_atendimentos.local_municipio_nome"])
            .groupby("Chamada_atendimentos.local_municipio_nome", as_index=False)
            .agg(latitude=(latitude, "mean"), longitude=(longitude, "mean"),
                 ocorrencias=(latitude, "size"))
        )
        for _, row in grouped.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=max(6, min(35, row["ocorrencias"] ** 0.5 * 2.5)),
                popup=(
                    f"<b>{row['Chamada_atendimentos.local_municipio_nome']}</b>"
                    f"<br>Ocorrências: {row['ocorrencias']:,}"
                ),
                color="#d62728",
                fill=True,
                fill_opacity=0.65,
            ).add_to(map_view)

    else:
        # Cluster padrão: um marcador por ocorrência.
        cluster = MarkerCluster().add_to(map_view)
        for _, row in selected.iterrows():
            municipality = safe_map_text(row.get("Chamada_atendimentos.local_municipio_nome"), "N/D")
            nature = safe_map_text(row.get("Chamada_atendimentos.natureza_descricao"), "N/D")
            local = safe_map_text(row.get("Chamada_atendimentos.local_do_fato"), "N/D")
            popup = (
                f"<b>📍 Município:</b> {municipality}<br>"
                f"<b>🔥 Natureza:</b> {nature}<br>"
                f"<b>🏠 Local:</b> {local}"
            )
            folium.Marker(
                location=[row[latitude], row[longitude]],
                popup=folium.Popup(popup, max_width=300),
                tooltip=f"{municipality} - {safe_map_text(nature, 'N/D', 30)}...",
            ).add_to(cluster)

    return map_view, len(selected)