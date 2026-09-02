import io

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.linear_model import LinearRegression
from streamlit_folium import st_folium

from data_loader import apply_filters, load_uploaded_data
from utils.helpers import coluna_ou_none, extrair_bbm, extrair_fracao, extrair_recursos
from visualizations import create_occurrence_map, plot_bar, plot_histogram, plot_line

st.set_page_config(page_title="Dashboard COBOM-BH", layout="wide")
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { font-size: 1.2rem !important; font-weight: 600 !important; }
    .stMetric { font-size: 0.9rem !important; }
    .stMetric label { font-size: 0.9rem !important; }
    .stMetric .stMetricValue { font-size: 1.4rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("🚒 Dashboard Interativo - COBOM-BH")
st.markdown("Análise de chamadas do Corpo de Bombeiros Militar de Minas Gerais recebidas no COBOM-BH")


def counts(dataframe, column, name="count"):
    if column not in dataframe.columns:
        return pd.DataFrame(columns=[column, name])
    return dataframe[column].dropna().value_counts().rename_axis(column).reset_index(name=name)


with st.sidebar:
    st.header("📂 Carregar Dados")
    uploaded_files = st.file_uploader("Selecione um ou mais arquivos .xlsx ou .csv", type=["xlsx", "csv"], accept_multiple_files=True)
    if not uploaded_files:
        st.info("👈 Faça upload de um ou mais arquivos .xlsx ou .csv para começar a análise.")
        st.stop()

    dataframes = {}
    with st.spinner("Carregando e processando arquivos..."):
        for uploaded_file in uploaded_files:
            try:
                dataframe = load_uploaded_data(uploaded_file)
                if not dataframe.empty:
                    dataframes[uploaded_file.name] = dataframe
                else:
                    st.warning(f"⚠️ O arquivo {uploaded_file.name} não contém dados válidos.")
            except Exception as error:
                st.error(f"Erro ao carregar {uploaded_file.name}: {error}")
    if not dataframes:
        st.error("Nenhum arquivo pôde ser carregado.")
        st.stop()

    combined = pd.concat([dataframe.assign(arquivo=name) for name, dataframe in dataframes.items()], ignore_index=True)
    st.success(f"✅ {len(dataframes)} arquivo(s) carregado(s) com sucesso!")
    st.header("🔍 Filtros")
    st.subheader("📅 Período")
    available_dates = sorted(combined["chamada_data_inclusao"].dt.date.unique())
    data_inicio = st.date_input("Data inicial", value=min(available_dates), min_value=min(available_dates), max_value=max(available_dates))
    data_fim = st.date_input("Data final", value=max(available_dates), min_value=min(available_dates), max_value=max(available_dates))
    if data_inicio > data_fim:
        st.warning("⚠️ Data inicial não pode ser maior que a data final.")
        data_inicio, data_fim = data_fim, data_inicio

    selected_file = st.selectbox("Selecione um arquivo para análise detalhada (ou 'Todos')", ["Todos", *dataframes])
    source = combined if selected_file == "Todos" else dataframes[selected_file]
    source = source[source["chamada_data_inclusao"].dt.date.between(data_inicio, data_fim)]

    municipality_column = "Chamada_atendimentos.local_municipio_nome"
    nature_column = "Chamada_atendimentos.natureza_descricao"
    unit_column = "Chamada_atendimentos.unidade_servico_nome"
    class_column = coluna_ou_none(source, "Chamada_atendimentos.chamada_classificacao_descricao", "chamada_classificacao_descricao", "Classificacao", "classificacao")
    with st.expander("Filtros adicionais", expanded=True):
        municipality_filter = st.multiselect("Município", sorted(source[municipality_column].dropna().unique()) if municipality_column in source else [])
        nature_filter = st.multiselect("Natureza", sorted(source[nature_column].dropna().unique()) if nature_column in source else [])
        class_filter = st.multiselect("Classificação da Chamada", sorted(source[class_column].dropna().unique()) if class_column else [])
        unit_filter = st.multiselect("Unidade", sorted(source[unit_column].dropna().unique()) if unit_column in source else [])
        resource_filter = st.multiselect("Recursos Empenhados", extrair_recursos(source))
    filter_dict = {municipality_column: municipality_filter, nature_column: nature_filter, unit_column: unit_filter, "Empenhos.recurso_codigo_prefixo": resource_filter}
    if class_column:
        filter_dict[class_column] = class_filter
    df_filtered = apply_filters(source, filter_dict)
    st.session_state["df_filtered"] = df_filtered
    st.download_button("⬇️ Baixar dados filtrados (CSV)", data=df_filtered.to_csv(index=False).encode("utf-8-sig"), file_name="cobom_dados_filtrados.csv", mime="text/csv")

if "df_filtered" not in st.session_state:
    st.stop()
df_filtered = st.session_state["df_filtered"].copy()

# Cards de métricas
number_calls = len(df_filtered)
mean_daily = number_calls / max(1, df_filtered["chamada_data_inclusao"].dt.date.nunique())
number_municipalities = df_filtered["Chamada_atendimentos.local_municipio_nome"].nunique()
bbm_series = df_filtered["Chamada_atendimentos.unidade_servico_nome"].map(extrair_bbm) if "Chamada_atendimentos.unidade_servico_nome" in df_filtered else pd.Series(dtype=str)
unit_top = bbm_series.mode().iloc[0] if not bbm_series.empty else "N/A"
nature_top = df_filtered["Chamada_atendimentos.natureza_descricao"].mode().iloc[0] if not df_filtered.empty and "Chamada_atendimentos.natureza_descricao" in df_filtered else "N/A"
class_top = df_filtered[class_column].mode().iloc[0] if class_column and not df_filtered.empty and not df_filtered[class_column].mode().empty else "N/A"
metric_row = st.columns(3)
metric_row[0].metric("📞 Total de Chamadas", f"{number_calls:,}")
metric_row[1].metric("📊 Média Diária", f"{mean_daily:.1f}")
metric_row[2].metric("📍 Municípios Atendidos", number_municipalities)
metric_row = st.columns(3)
metric_row[0].metric("🚒 Unidade Mais Acionada", unit_top)
metric_row[1].metric("🔥 Natureza Mais Comum", nature_top)
metric_row[2].metric("📋 Classificação Mais Frequente", class_top)
st.divider()

if "data_hora_fim" not in df_filtered:
    df_filtered["data_hora_fim"] = pd.NaT
df_filtered["tempo_minutos"] = (df_filtered["data_hora_fim"] - df_filtered["data_hora"]).dt.total_seconds() / 60
df_filtered = df_filtered[df_filtered["tempo_minutos"] >= 0].copy()
df_filtered["tempo_horas"] = df_filtered["tempo_minutos"] / 60

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Rankings de Dados", "📈 Evolução e Projeção Temporal", "📊 Distribuição e Comparação", "🗺️ Mapa de Ocorrências", "⏱️ Tempo de Atendimento"])

with tab1:
    st.header("📊 Rankings de Dados")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(plot_bar(counts(df_filtered, nature_column), nature_column, "count", "Top 15 Naturezas", 15), width="stretch")
        if "Chamada_atendimentos.local_do_fato" in df_filtered:
            locations = df_filtered["Chamada_atendimentos.local_do_fato"].dropna()
            locations = locations[locations.str.strip().ne("") & locations.str.strip().str.upper().ne("N/A")]
            st.plotly_chart(plot_bar(counts(locations.to_frame(), "Chamada_atendimentos.local_do_fato"), "Chamada_atendimentos.local_do_fato", "count", "Top 15 Logradouros", 15), width="stretch")
    with right:
        st.plotly_chart(plot_bar(counts(df_filtered, municipality_column), municipality_column, "count", "Top 15 Municípios", 15), width="stretch")
        if unit_column in df_filtered:
            unit_counts = counts(df_filtered.assign(bbm=df_filtered[unit_column].map(extrair_bbm)), "bbm")
            unit_counts = unit_counts[unit_counts.bbm.ne("Outros")]
            st.plotly_chart(plot_bar(unit_counts, "bbm", "count", "Top 15 Unidades", 15), width="stretch")
            fraction_counts = counts(df_filtered.assign(fracao=df_filtered[unit_column].map(extrair_fracao)), "fracao")
            fraction_counts = fraction_counts[fraction_counts.fracao.ne("Outros")]
            fig = plot_bar(fraction_counts, "fracao", "count", "Top 15 Frações / Unidades", 15)
            fig.update_layout(width=1400, height=700, xaxis={"categoryorder": "total descending"}, margin={"l": 40, "r": 20, "t": 60, "b": 180})
            st.plotly_chart(fig, use_container_width=True)
    left, right = st.columns(2)
    with left:
        if "Empenhos.recurso_codigo_prefixo" in df_filtered:
            resources = df_filtered["Empenhos.recurso_codigo_prefixo"].fillna("").astype(str).str.replace(" / ", ",", regex=False).str.split(",").explode().str.strip()
            st.plotly_chart(plot_bar(counts(resources.to_frame(name="prefixo"), "prefixo"), "prefixo", "count", "Top 15 Viaturas Mais Empenhadas", 15), width="stretch")
    with right:
        if class_column:
            st.plotly_chart(plot_bar(counts(df_filtered, class_column), class_column, "count", "Top 10 Classificações", 10), width="stretch")

with tab2:
    st.header("📈 Evolução e Projeção Temporal")
    monthly = df_filtered.groupby(["ano", "mes"]).size().reset_index(name="chamadas")
    if len(monthly.ano.unique()) >= 2:
        st.plotly_chart(plot_line(monthly, "mes", "chamadas", "ano", "Comparação Mensal por Ano (dados filtrados)"), width="stretch")
    else:
        st.info("ℹ️ Selecione um período que contenha pelo menos dois anos distintos para a comparação mensal.")
    if len(monthly) >= 2:
        all_months = pd.date_range(df_filtered["chamada_data_inclusao"].min(), df_filtered["chamada_data_inclusao"].max(), freq="MS").to_period("M")
        full = pd.DataFrame({"ano": all_months.year, "mes": all_months.month}).merge(monthly, how="left").fillna(0)
        full["periodo"] = pd.to_datetime(full.ano.astype(int).astype(str) + "-" + full.mes.astype(int).astype(str).str.zfill(2))
        full = full.sort_values("periodo").reset_index(drop=True)
        full["indice"] = np.arange(len(full))
        model = LinearRegression().fit(full[["indice"]], full["chamadas"])
        future_indices = np.arange(full.indice.max() + 1, full.indice.max() + 7).reshape(-1, 1)
        predictions = model.predict(future_indices)
        deviation = np.std(full["chamadas"] - model.predict(full[["indice"]]))
        future_dates = pd.date_range(start=full.periodo.iloc[-1], periods=7, freq="M")[1:]
        history = pd.DataFrame({"periodo_str": full.periodo.dt.strftime("%Y-%m"), "chamadas": full.chamadas, "tipo": "Histórico"})
        future = pd.DataFrame({"periodo_str": future_dates.strftime("%Y-%m"), "chamadas": predictions, "tipo": "Projeção"})
        upper = future.assign(chamadas=future.chamadas + deviation, tipo="Limite Superior")
        lower = future.assign(chamadas=(future.chamadas - deviation).clip(lower=0), tipo="Limite Inferior")
        projection = pd.concat([history, future, upper, lower], ignore_index=True)
        fig = plot_line(projection, "periodo_str", "chamadas", "tipo", "Projeção de Chamadas (próximos 6 meses) com Desvio Padrão")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("ℹ️ Dados insuficientes para realizar a projeção (mínimo 2 meses com ocorrências).")
    daily = df_filtered.groupby(df_filtered.chamada_data_inclusao.dt.date).size().rename("chamadas").reset_index(name="chamadas").rename(columns={"chamada_data_inclusao": "data"})
    st.plotly_chart(plot_line(daily, "data", "chamadas", None, "Chamadas por Dia"), width="stretch")

with tab3:
    st.header("📊 Distribuição e Comparação de Dados")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(plot_bar(df_filtered["hora"].value_counts().sort_index().rename_axis("hora").reset_index(name="chamadas"), "hora", "chamadas", "Chamadas por Hora do Dia"), width="stretch")
    with right:
        days = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
        week = df_filtered.dia_semana.map(days).value_counts().reindex(list(days.values())).rename_axis("dia").reset_index(name="chamadas")
        st.plotly_chart(plot_bar(week, "dia", "chamadas", "Chamadas por Dia da Semana"), width="stretch")
    left, right = st.columns(2)
    with left:
        if class_column:
            st.plotly_chart(px.pie(counts(df_filtered, class_column), names=class_column, values="count", title="Distribuição por Classificação", template="plotly_white"), width="stretch")
    with right:
        if unit_column in df_filtered:
            bbm_counts = counts(df_filtered.assign(bbm=df_filtered[unit_column].map(extrair_bbm)), "bbm", "chamadas")
            bbm_counts = bbm_counts[bbm_counts.bbm.ne("Outros")]
            st.plotly_chart(plot_bar(bbm_counts, "bbm", "chamadas", "Chamadas por BBM / CIA IND"), width="stretch")
            fractions = counts(df_filtered.assign(fracao=df_filtered[unit_column].map(extrair_fracao)), "fracao", "chamadas")
            fractions = fractions[fractions.fracao.ne("Outros")]
            st.plotly_chart(plot_bar(fractions, "fracao", "chamadas", "Detalhamento por Frações / Unidades", 15), width="stretch")

with tab4:
    st.header("🗺️ Mapa de Ocorrências")
    latitude = "Chamada_atendimentos.local_latitude"
    longitude = "Chamada_atendimentos.local_longitude"
    if latitude in df_filtered and longitude in df_filtered:
        map_data = df_filtered.dropna(subset=[latitude, longitude])
        if not map_data.empty:
            sample_size = st.slider("Tamanho da amostra", min_value=100, max_value=max(100, min(20000, len(map_data))), value=min(5000, len(map_data)), step=100)
            grouped_map = st.checkbox("Agrupar por município", value=False)
            map_view, shown = create_occurrence_map(map_data, sample_size, grouped_map)
            st_folium(map_view, width=1200, height=600)
            st.caption(f"📊 Mostrando {shown} de {len(map_data)} ocorrências com coordenadas válidas.")
        else:
            st.info("ℹ️ Nenhum dado com coordenadas disponíveis para exibir no mapa.")
    else:
        st.info("ℹ️ Colunas de latitude/longitude não encontradas nos dados.")

with tab5:
    st.header("⏱️ Tempo de Atendimento")
    time_data = df_filtered.dropna(subset=["data_hora_fim"]).copy()
    if time_data.empty:
        st.info("ℹ️ Nenhum registro com data/hora de classificação (fim) disponível para análise de tempo.")
    else:
        max_time = st.slider("Filtrar tempo máximo (horas) para análise", 1.0, 720.0, 168.0, 1.0, help="Remover ocorrências com tempo acima deste limite para melhor visualização.")
        time_data = time_data[time_data.tempo_horas <= max_time].copy()
        average, median, maximum = time_data.tempo_horas.mean(), time_data.tempo_horas.median(), time_data.tempo_horas.max()
        over_day = (time_data.tempo_horas > 24).sum()
        metrics = st.columns(5)
        metrics[0].metric("📊 Média (h)", f"{average:.2f}"); metrics[1].metric("📊 Mediana (h)", f"{median:.2f}"); metrics[2].metric("📈 Máximo (h)", f"{maximum:.2f}"); metrics[3].metric("📋 Total de Registros", f"{len(time_data):,}"); metrics[4].metric("⏰ > 24h", f"{over_day} ({over_day / len(time_data) * 100:.1f}%)")
        st.divider(); st.subheader("Distribuição do Tempo de Atendimento (em horas)")
        time_data["categoria"] = np.where(time_data.tempo_horas <= 24, "Até 24h", "Acima de 24h")
        fig = plot_histogram(time_data, "tempo_horas", "Histograma do Tempo de Atendimento", color="categoria", nbins=50, labels={"tempo_horas": "Horas", "count": "Número de Chamadas"}, barmode="stack")
        fig.update_layout(legend_title_text=""); st.plotly_chart(fig, width="stretch")
        over_data = time_data[time_data.tempo_horas > 24].assign(dias=lambda data: np.ceil(data.tempo_horas / 24).astype(int))
        if not over_data.empty:
            st.plotly_chart(plot_histogram(over_data, "dias", "Distribuição dos Atendimentos com Duração > 24 horas (em dias)", nbins=20, labels={"dias": "Dias", "count": "Número de Chamadas"}), width="stretch")
        else:
            st.info("Nenhuma ocorrência com tempo superior a 24 horas.")
        st.subheader("📋 Resumo por Classificação da Chamada")
        if class_column:
            summary = time_data.groupby(class_column).agg(media_horas=("tempo_horas", "mean"), mediana_horas=("tempo_horas", "median"), desvio_horas=("tempo_horas", "std"), contagem=("tempo_horas", "count"), maximo_horas=("tempo_horas", "max")).reset_index()
            summary["acima_24h"] = time_data[class_column].where(time_data.tempo_horas > 24).value_counts().reindex(summary[class_column]).fillna(0).to_numpy().astype(int)
            summary["perc_acima_24h"] = (summary.acima_24h / summary.contagem * 100).round(1)
        else:
            summary = pd.DataFrame(columns=["Classificação", "contagem"])
        minimum = st.number_input("Mínimo de registros por classificação para exibição", 1, 100, 5, 1, key="min_reg_class")
        summary = summary[summary.contagem >= minimum].sort_values("media_horas", ascending=False) if "contagem" in summary else summary
        if summary.empty:
            st.info(f"Nenhuma classificação com pelo menos {minimum} registros.")
        else:
            for column in ["media_horas", "mediana_horas", "maximo_horas"]: summary[column] = summary[column].map(lambda value: f"{value:.2f}")
            summary["desvio_horas"] = summary.desvio_horas.map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
            summary["perc_acima_24h"] = summary.perc_acima_24h.map(lambda value: f"{value:.1f}%")
            st.dataframe(summary.rename(columns={class_column: "Classificação", "media_horas": "Média (h)", "mediana_horas": "Mediana (h)", "desvio_horas": "Desvio (h)", "contagem": "Nº Chamadas", "maximo_horas": "Máximo (h)", "acima_24h": "> 24h", "perc_acima_24h": "% > 24h"}), use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("Dashboard desenvolvido com Streamlit | Dados do COBOM-BH")
