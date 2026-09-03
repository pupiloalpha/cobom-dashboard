import io

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.linear_model import LinearRegression
from streamlit_folium import st_folium

from data_loader import apply_filters, load_uploaded_data, process_dataframe
from utils.demo_data import generate_demo_cobom_data
from utils.helpers import coluna_ou_none, extrair_bbm, extrair_fracao, extrair_recursos
from visualizations import (
    create_occurrence_map,
    plot_bar,
    plot_histogram,
    plot_hourly_weekday_heatmap,
    plot_line,
    plot_resource_concentration,
)

st.set_page_config(page_title="Dashboard COBOM-BH", layout="wide", page_icon="🚒")
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { font-size: 1.2rem !important; font-weight: 600 !important; }
    .stMetric { font-size: 0.9rem !important; }
    .stMetric label { font-size: 0.9rem !important; }
    .stMetric .stMetricValue { font-size: 1.4rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("🚒 Dashboard Interativo - COBOM-BH")
st.markdown("Análise operacional de chamadas do Corpo de Bombeiros Militar de Minas Gerais recebidas no COBOM-BH")


def counts(dataframe, column, name="contagem"):
    if column not in dataframe.columns:
        return pd.DataFrame(columns=[column, name])
    return dataframe[column].dropna().value_counts().rename_axis(column).reset_index(name=name)


if "use_demo_data" not in st.session_state:
    st.session_state["use_demo_data"] = False

if "cached_dataframes" not in st.session_state:
    st.session_state["cached_dataframes"] = {}

with st.sidebar:
    st.header("📂 Carregar Dados")
    uploaded_files = st.file_uploader(
        "Selecione um ou mais arquivos .xlsx ou .csv",
        type=["xlsx", "xlsm", "xslx", "csv"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.session_state["use_demo_data"] = False
    elif not st.session_state["use_demo_data"]:
        st.session_state["cached_dataframes"] = {}

    if not uploaded_files:
        if st.session_state["use_demo_data"]:
            if st.button("🔄 Sair dos dados de demonstração", use_container_width=True):
                st.session_state["use_demo_data"] = False
                st.session_state["cached_dataframes"] = {}
                st.rerun()
            st.info("ℹ️ Exibindo conjunto de **Dados de Demonstração (Demo CBMMG)**.")
        else:
            if st.button("🚀 Carregar Dados de Demonstração (Demo)", use_container_width=True):
                st.session_state["use_demo_data"] = True
                with st.spinner("Gerando dados sintéticos realistas do COBOM..."):
                    demo_df = generate_demo_cobom_data(1800)
                    processed_demo = process_dataframe(demo_df)
                    st.session_state["cached_dataframes"]["dados_demonstracao_cobom.csv"] = processed_demo
                st.rerun()
            st.info("👈 Faça upload de um ou mais arquivos ou utilize os dados de demonstração.")

if not uploaded_files and not st.session_state["use_demo_data"]:
    st.info("👈 **Para iniciar a análise, faça o upload do arquivo CSV/XLSX na barra lateral ou clique no botão de demonstração.**")

    c_demo, _ = st.columns([1, 2])
    with c_demo:
        if st.button("🚀 Explorar com Dados de Demonstração do COBOM", key="main_demo_btn", use_container_width=True):
            st.session_state["use_demo_data"] = True
            with st.spinner("Gerando dados sintéticos realistas do COBOM..."):
                demo_df = generate_demo_cobom_data(1800)
                processed_demo = process_dataframe(demo_df)
                st.session_state["cached_dataframes"]["dados_demonstracao_cobom.csv"] = processed_demo
            st.rerun()

    st.subheader("📋 Passo a Passo para Obter os Dados no Sistema CAD")

    steps_html = """
    <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 10px; margin-bottom: 25px;">
        <div style="display: flex; align-items: flex-start; background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 5px solid #d62728; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="background: #d62728; color: #ffffff; border-radius: 50%; min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 14px; margin-top: 2px;">1</div>
            <div>
                <strong style="font-size: 1.05rem; color: var(--text-color);">Acesso ao Módulo de Chamadas</strong>
                <p style="margin: 4px 0 0 0; color: var(--text-color); opacity: 0.85;">Entre no <strong>Sistema CAD</strong>, acesse o menu <strong>"Chamadas"</strong> e selecione a opção <strong>"Pesquisa de chamadas"</strong>.</p>
            </div>
        </div>
        <div style="display: flex; align-items: flex-start; background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 5px solid #d62728; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="background: #d62728; color: #ffffff; border-radius: 50%; min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 14px; margin-top: 2px;">2</div>
            <div>
                <strong style="font-size: 1.05rem; color: var(--text-color);">Definição de Critérios de Pesquisa</strong>
                <p style="margin: 4px 0 0 0; color: var(--text-color); opacity: 0.85;">Defina os critérios de sua pesquisa selecionando <strong>"Data/Hora de criação"</strong>, <strong>"Filtro de chamada"</strong> e <strong>"Pesquisar por"</strong>.</p>
            </div>
        </div>
        <div style="display: flex; align-items: flex-start; background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 5px solid #d62728; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="background: #d62728; color: #ffffff; border-radius: 50%; min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 14px; margin-top: 2px;">3</div>
            <div>
                <strong style="font-size: 1.05rem; color: var(--text-color);">Execução da Pesquisa</strong>
                <p style="margin: 4px 0 0 0; color: var(--text-color); opacity: 0.85;">Clique em <strong>"Pesquisar"</strong> para confirmar se existem chamadas para os critérios definidos.</p>
            </div>
        </div>
        <div style="display: flex; align-items: flex-start; background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 5px solid #d62728; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="background: #d62728; color: #ffffff; border-radius: 50%; min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 14px; margin-top: 2px;">4</div>
            <div>
                <strong style="font-size: 1.05rem; color: var(--text-color);">Exportação dos Dados</strong>
                <p style="margin: 4px 0 0 0; color: var(--text-color); opacity: 0.85;">Clique em <strong>"Exportar CSV"</strong> para gerar o arquivo com os dados das chamadas.</p>
            </div>
        </div>
        <div style="display: flex; align-items: flex-start; background: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); border-left: 5px solid #d62728; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
            <div style="background: #d62728; color: #ffffff; border-radius: 50%; min-width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 14px; margin-top: 2px;">5</div>
            <div>
                <strong style="font-size: 1.05rem; color: var(--text-color);">Upload no Portal</strong>
                <p style="margin: 4px 0 0 0; color: var(--text-color); opacity: 0.85;">Salve o arquivo CSV em uma pasta de fácil acesso e faça o <strong>upload na barra lateral à esquerda</strong>.</p>
            </div>
        </div>
    </div>
    """
    st.markdown(steps_html, unsafe_allow_html=True)

    with st.expander("ℹ️ Informações sobre compatibilidade e múltiplos arquivos"):
        st.markdown("""
        - **Múltiplos Arquivos**: Você pode carregar mais de um arquivo CSV ou Excel simultaneamente. O painel unificará todos os registros em um único conjunto de dados.
        - **Padronização Automática**: Datas, horários, coordenadas, municípios e viaturas empenhadas são automaticamente processados e normalizados pelo sistema.
        """)
    st.stop()

with st.sidebar:
    if uploaded_files:
        current_files_map = {f.name: f for f in uploaded_files}
        # Remover arquivos que o usuário desmarcou
        removed_keys = [k for k in st.session_state["cached_dataframes"] if k not in current_files_map]
        for k in removed_keys:
            del st.session_state["cached_dataframes"][k]

        # Processar apenas arquivos que ainda não estão em cache na sessão
        new_files = [f for f in uploaded_files if f.name not in st.session_state["cached_dataframes"]]
        if new_files:
            with st.spinner(f"Carregando e processando {len(new_files)} arquivo(s)..."):
                for uploaded_file in new_files:
                    try:
                        dataframe = load_uploaded_data(uploaded_file)
                        if not dataframe.empty:
                            st.session_state["cached_dataframes"][uploaded_file.name] = dataframe
                        else:
                            st.warning(f"⚠️ O arquivo {uploaded_file.name} não contém dados válidos.")
                    except Exception as error:
                        st.error(f"Erro ao carregar {uploaded_file.name}: {error}")

    dataframes = st.session_state.get("cached_dataframes", {})
    if not dataframes:
        st.error("Nenhum arquivo pôde ser carregado.")
        st.stop()
        combined = pd.DataFrame()
    else:
        combined = pd.concat(
            [dataframe.assign(arquivo=name) for name, dataframe in dataframes.items()],
            ignore_index=True,
        )
        if not st.session_state.get("use_demo_data"):
            st.success(f"✅ {len(dataframes)} arquivo(s) carregado(s) com sucesso!")

    if combined.empty:
        st.stop()

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

    with st.expander("Filtros adicionais (em cascata)", expanded=True):
        # 1. Município
        all_municipalities = sorted(source[municipality_column].dropna().unique()) if municipality_column in source else []
        municipality_filter = st.multiselect("Município", all_municipalities)

        # Base para filtros em cascata dependentes da seleção de município
        cascade_scope = source
        if municipality_filter and municipality_column in cascade_scope:
            cascade_scope = cascade_scope[cascade_scope[municipality_column].isin(municipality_filter)]

        # 2. Natureza
        available_natures = sorted(cascade_scope[nature_column].dropna().unique()) if nature_column in cascade_scope else []
        nature_filter = st.multiselect("Natureza", available_natures)

        # 3. Classificação
        available_classes = sorted(cascade_scope[class_column].dropna().unique()) if class_column else []
        class_filter = st.multiselect("Classificação da Chamada", available_classes)

        # 4. Unidade
        available_units = sorted(cascade_scope[unit_column].dropna().unique()) if unit_column in cascade_scope else []
        unit_filter = st.multiselect("Unidade", available_units)

        # 5. Recursos
        available_resources = extrair_recursos(cascade_scope)
        resource_filter = st.multiselect("Recursos Empenhados", available_resources)

    filter_dict = {
        municipality_column: municipality_filter,
        nature_column: nature_filter,
        unit_column: unit_filter,
        "Empenhos.recurso_codigo_prefixo": resource_filter,
    }
    if class_column:
        filter_dict[class_column] = class_filter

    df_filtered = apply_filters(source, filter_dict)
    st.download_button(
        "⬇️ Baixar dados filtrados (CSV)",
        data=df_filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name="cobom_dados_filtrados.csv",
        mime="text/csv",
    )

df_filtered = df_filtered.copy()

# Cards de métricas
number_calls = len(df_filtered)
mean_daily = number_calls / max(1, df_filtered["chamada_data_inclusao"].dt.date.nunique()) if not df_filtered.empty else 0
number_municipalities = df_filtered["Chamada_atendimentos.local_municipio_nome"].nunique() if "Chamada_atendimentos.local_municipio_nome" in df_filtered else 0
bbm_series = df_filtered["Chamada_atendimentos.unidade_servico_nome"].map(extrair_bbm) if "Chamada_atendimentos.unidade_servico_nome" in df_filtered else pd.Series(dtype=str)
unit_top = bbm_series.mode().iloc[0] if not bbm_series.mode().empty else "N/D"
nature_top = df_filtered["Chamada_atendimentos.natureza_descricao"].mode().iloc[0] if "Chamada_atendimentos.natureza_descricao" in df_filtered and not df_filtered["Chamada_atendimentos.natureza_descricao"].mode().empty else "N/D"
class_top = df_filtered[class_column].mode().iloc[0] if class_column and not df_filtered[class_column].mode().empty else "N/D"

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
df_filtered = df_filtered[
    df_filtered["tempo_minutos"].isna() | df_filtered["tempo_minutos"].ge(0)
].copy()
df_filtered["tempo_horas"] = df_filtered["tempo_minutos"] / 60

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Rankings de Dados",
    "📈 Evolução e Projeção Temporal",
    "📊 Distribuição e Comparação",
    "🗺️ Mapa de Ocorrências",
    "⏱️ Tempo de Atendimento",
])

with tab1:
    st.header("📊 Rankings de Dados")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(plot_bar(counts(df_filtered, nature_column), nature_column, "contagem", "Top 15 Naturezas de Ocorrência", 15), width="stretch")
        if "Chamada_atendimentos.local_do_fato" in df_filtered:
            locations = df_filtered["Chamada_atendimentos.local_do_fato"].dropna()
            locations = locations[
                locations.str.strip().ne("")
                & locations.str.strip().str.upper().ne("N/A")
                & locations.str.strip().str.upper().ne("N/D")
            ]
            st.plotly_chart(plot_bar(counts(locations.to_frame(), "Chamada_atendimentos.local_do_fato"), "Chamada_atendimentos.local_do_fato", "contagem", "Top 15 Logradouros / Vias", 15), width="stretch")
    with right:
        st.plotly_chart(plot_bar(counts(df_filtered, municipality_column), municipality_column, "contagem", "Top 15 Municípios", 15), width="stretch")
        if unit_column in df_filtered:
            unit_counts = counts(df_filtered.assign(bbm=df_filtered[unit_column].map(extrair_bbm)), "bbm")
            unit_counts = unit_counts[unit_counts.bbm.ne("Outros")]
            st.plotly_chart(plot_bar(unit_counts, "bbm", "contagem", "Top 15 Batalhões / Companhias Independentes", 15), width="stretch")
            fraction_counts = counts(df_filtered.assign(fracao=df_filtered[unit_column].map(extrair_fracao)), "fracao")
            fraction_counts = fraction_counts[fraction_counts.fracao.ne("Outros")]
            fig = plot_bar(fraction_counts, "fracao", "contagem", "Top 15 Frações e Unidades Operacionais", 15)
            fig.update_layout(width=1400, height=700, xaxis={"categoryorder": "total descending"}, margin={"l": 40, "r": 20, "t": 60, "b": 180})
            st.plotly_chart(fig, width="stretch")
    left, right = st.columns(2)
    with left:
        if "Empenhos.recurso_codigo_prefixo" in df_filtered:
            resources = df_filtered["Empenhos.recurso_codigo_prefixo"].fillna("").astype(str).str.replace(" / ", ",", regex=False).str.split(",").explode().str.strip()
            st.plotly_chart(plot_bar(counts(resources.to_frame(name="prefixo"), "prefixo"), "prefixo", "contagem", "Top 15 Viaturas Mais Empenhadas", 15), width="stretch")
    with right:
        if class_column:
            st.plotly_chart(plot_bar(counts(df_filtered, class_column), class_column, "contagem", "Top 10 Classificações de Chamadas", 10), width="stretch")
    resource_concentration = plot_resource_concentration(df_filtered)
    if resource_concentration is not None:
        st.plotly_chart(resource_concentration, width="stretch")
        st.caption("As barras mostram a quantidade de viaturas em cada chamada ordenada. A linha indica quanto do total de viaturas está concentrado nas chamadas do ranking.")

with tab2:
    st.header("📈 Evolução e Projeção Temporal")
    monthly = df_filtered.groupby(["ano", "mes"]).size().reset_index(name="chamadas")
    if len(monthly.ano.unique()) >= 2:
        st.plotly_chart(plot_line(monthly, "mes", "chamadas", "ano", "Comparação Mensal de Chamadas por Ano"), width="stretch")
    else:
        st.info("ℹ️ Selecione um período que contenha pelo menos dois anos distintos para a comparação mensal.")
    if len(monthly) >= 2:
        all_months = pd.date_range(df_filtered["chamada_data_inclusao"].min(), df_filtered["chamada_data_inclusao"].max(), freq="MS").to_period("M")
        full = pd.DataFrame({"ano": all_months.year, "mes": all_months.month}).merge(monthly, how="left").fillna(0)
        full["periodo"] = pd.to_datetime(full.ano.astype(int).astype(str) + "-" + full.mes.astype(int).astype(str).str.zfill(2))
        full = full.sort_values("periodo").reset_index(drop=True)
        full["indice"] = np.arange(len(full))
        
        # Regressão linear base
        model = LinearRegression().fit(full[["indice"]], full["chamadas"])
        future_indices = pd.DataFrame({"indice": np.arange(full.indice.max() + 1, full.indice.max() + 7)})
        base_predictions = model.predict(future_indices)

        # Componente sazonal mensal
        if len(full) >= 6:
            full["tendencia"] = model.predict(full[["indice"]]).clip(min=1)
            full["fator_sazonal"] = full["chamadas"] / full["tendencia"]
            seasonal_map = full.groupby("mes")["fator_sazonal"].mean().to_dict()
        else:
            seasonal_map = {}

        future_dates = pd.date_range(start=full.periodo.iloc[-1], periods=7, freq="ME")[1:]
        seasonal_preds = []
        for i, dt in enumerate(future_dates):
            pred = base_predictions[i]
            if dt.month in seasonal_map:
                pred = pred * seasonal_map[dt.month]
            seasonal_preds.append(max(0, float(pred)))

        deviation = float(np.std(full["chamadas"] - model.predict(full[["indice"]])))
        history = pd.DataFrame({"periodo_str": full.periodo.dt.strftime("%Y-%m"), "chamadas": full.chamadas, "tipo": "Histórico"})
        future = pd.DataFrame({"periodo_str": future_dates.strftime("%Y-%m"), "chamadas": seasonal_preds, "tipo": "Projeção Sazonal"})
        upper = future.assign(chamadas=future.chamadas + deviation, tipo="Limite Superior")
        lower = future.assign(chamadas=(future.chamadas - deviation).clip(lower=0), tipo="Limite Inferior")
        projection = pd.concat([history, future, upper, lower], ignore_index=True)
        fig = plot_line(projection, "periodo_str", "chamadas", "tipo", "Projeção Operacional de Chamadas com Sazonalidade e Margem de Desvio")
        st.plotly_chart(fig, width="stretch")
        st.caption("A projeção combina a tendência linear histórica com fatores multiplicativos de sazonalidade mensal (ex.: estiagem/queimadas e chuvas de verão).")
    else:
        st.info("ℹ️ Dados insuficientes para realizar a projeção (mínimo 2 meses com ocorrências).")
    daily = df_filtered.groupby(df_filtered.chamada_data_inclusao.dt.date).size().rename("chamadas").reset_index(name="chamadas").rename(columns={"chamada_data_inclusao": "data"})
    st.plotly_chart(plot_line(daily, "data", "chamadas", None, "Volume Diário de Chamadas"), width="stretch")

with tab3:
    st.header("📊 Distribuição e Comparação de Dados")

    st.subheader("🔥 Matriz de Calor de Plantão Operacional")
    heatmap_matrix = plot_hourly_weekday_heatmap(df_filtered)
    if heatmap_matrix is not None:
        st.plotly_chart(heatmap_matrix, width="stretch")
        st.caption("A matriz cruza os 7 dias da semana com as 24 horas do dia para identificar horários de pico e orientar escalas de prontidão.")

    st.divider()
    left, right = st.columns(2)
    with left:
        st.plotly_chart(plot_bar(df_filtered["hora"].value_counts().sort_index().rename_axis("hora").reset_index(name="chamadas"), "hora", "chamadas", "Distribuição de Chamadas por Hora do Dia"), width="stretch")
    with right:
        days = {0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira", 3: "Quinta-feira", 4: "Sexta-feira", 5: "Sábado", 6: "Domingo"}
        week = df_filtered.dia_semana.map(days).value_counts().reindex(list(days.values())).rename_axis("dia").reset_index(name="chamadas")
        st.plotly_chart(plot_bar(week, "dia", "chamadas", "Distribuição de Chamadas por Dia da Semana"), width="stretch")
    left, right = st.columns(2)
    with left:
        if class_column:
            pie_fig = px.pie(
                counts(df_filtered, class_column),
                names=class_column,
                values="contagem",
                title="Distribuição por Classificação da Chamada",
                labels={class_column: "Classificação", "contagem": "Nº de Chamadas"},
            )
            pie_fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(pie_fig, width="stretch")
    with right:
        if unit_column in df_filtered:
            bbm_counts = counts(df_filtered.assign(bbm=df_filtered[unit_column].map(extrair_bbm)), "bbm", "chamadas")
            bbm_counts = bbm_counts[bbm_counts.bbm.ne("Outros")]
            st.plotly_chart(plot_bar(bbm_counts, "bbm", "chamadas", "Chamadas por Batalhão / Companhia Independente"), width="stretch")
            fractions = counts(df_filtered.assign(fracao=df_filtered[unit_column].map(extrair_fracao)), "fracao", "chamadas")
            fractions = fractions[fractions.fracao.ne("Outros")]
            st.plotly_chart(plot_bar(fractions, "fracao", "chamadas", "Detalhamento por Frações e Unidades Operacionais", 15), width="stretch")

with tab4:
    st.header("🗺️ Mapa de Ocorrências")
    latitude = "Chamada_atendimentos.local_latitude"
    longitude = "Chamada_atendimentos.local_longitude"
    if latitude in df_filtered and longitude in df_filtered:
        map_data = df_filtered.dropna(subset=[latitude, longitude])
        if not map_data.empty:
            col_cfg1, col_cfg2 = st.columns([1, 1])
            with col_cfg1:
                sample_size = st.slider("Tamanho da amostra", min_value=100, max_value=max(100, min(20000, len(map_data))), value=min(5000, len(map_data)), step=100)
            with col_cfg2:
                map_mode = st.radio(
                    "Camada de Visualização",
                    options=["cluster", "heatmap", "grouped"],
                    format_func=lambda opt: {
                        "cluster": "📍 Marcadores Agrupados (Clusters)",
                        "heatmap": "🔥 Mancha de Calor (Densidade Espacial)",
                        "grouped": "⭕ Círculos por Município",
                    }[opt],
                    horizontal=True,
                )
            map_view, shown = create_occurrence_map(map_data, sample_size, mode_or_group=map_mode)
            st_folium(map_view, width=1200, height=600)
            st.caption(f"📊 Mostrando {shown:,} de {len(map_data):,} ocorrências com coordenadas válidas.")
        else:
            st.info("ℹ️ Nenhum dado com coordenadas disponíveis para exibir no mapa.")
    else:
        st.info("ℹ️ Colunas de latitude/longitude não encontradas nos dados.")

with tab5:
    st.header("⏱️ Tempo de Atendimento")
    time_data = df_filtered.dropna(subset=["data_hora_fim"]).copy()
    if time_data.empty:
        st.info("ℹ️ Nenhum registro com data/hora de encerramento disponível para análise de tempo.")
    else:
        max_time = st.slider("Filtrar tempo máximo (horas) para análise", 1.0, 720.0, 168.0, 1.0, help="Remover ocorrências com tempo acima deste limite para melhor visualização.")
        time_data = time_data[time_data.tempo_horas <= max_time].copy()
        average, median, maximum = time_data.tempo_horas.mean(), time_data.tempo_horas.median(), time_data.tempo_horas.max()
        over_day = (time_data.tempo_horas > 24).sum()
        metrics = st.columns(5)
        metrics[0].metric("📊 Média", f"{average:.2f} h")
        metrics[1].metric("📊 Mediana", f"{median:.2f} h")
        metrics[2].metric("📈 Máximo", f"{maximum:.2f} h")
        metrics[3].metric("📋 Total de Registros", f"{len(time_data):,}")
        metrics[4].metric("⏰ Duração > 24h", f"{over_day:,} ({over_day / len(time_data) * 100:.1f}%)")
        st.divider()
        st.subheader("Distribuição do Tempo de Atendimento (em horas)")
        time_data["categoria"] = np.where(time_data.tempo_horas <= 24, "Até 24h", "Acima de 24h")
        fig = plot_histogram(
            time_data,
            "tempo_horas",
            "Histograma do Tempo de Atendimento",
            color="categoria",
            nbins=50,
            labels={"tempo_horas": "Tempo de Atendimento (horas)", "contagem": "Nº de Chamadas", "categoria": "Faixa de Duração"},
            barmode="stack",
        )
        fig.update_layout(legend_title_text="Faixa de Duração")
        st.plotly_chart(fig, width="stretch")

        over_data = time_data[time_data.tempo_horas > 24].assign(dias=lambda data: np.ceil(data.tempo_horas / 24).astype(int))
        if not over_data.empty:
            st.plotly_chart(
                plot_histogram(
                    over_data,
                    "dias",
                    "Distribuição dos Atendimentos com Duração Superior a 24 horas (em dias)",
                    nbins=20,
                    labels={"dias": "Duração (dias)", "contagem": "Nº de Chamadas"},
                ),
                width="stretch",
            )
        else:
            st.info("Nenhuma ocorrência com tempo superior a 24 horas.")
        st.subheader("📋 Resumo por Classificação da Chamada")
        if class_column:
            summary = time_data.groupby(class_column).agg(
                media_horas=("tempo_horas", "mean"),
                mediana_horas=("tempo_horas", "median"),
                desvio_horas=("tempo_horas", "std"),
                contagem=("tempo_horas", "count"),
                maximo_horas=("tempo_horas", "max"),
            ).reset_index()
            summary["acima_24h"] = time_data[class_column].where(time_data.tempo_horas > 24).value_counts().reindex(summary[class_column]).fillna(0).to_numpy().astype(int)
            summary["perc_acima_24h"] = (summary.acima_24h / summary.contagem * 100).round(1)
        else:
            summary = pd.DataFrame(columns=["Classificação da Chamada", "contagem"])
        minimum = st.number_input("Mínimo de registros por classificação para exibição", 1, 100, 5, 1, key="min_reg_class")
        summary = summary[summary.contagem >= minimum].sort_values("media_horas", ascending=False) if "contagem" in summary else summary
        if summary.empty:
            st.info(f"Nenhuma classificação com pelo menos {minimum} registros.")
        else:
            for column in ["media_horas", "mediana_horas", "maximo_horas"]:
                summary[column] = summary[column].map(lambda value: f"{value:.2f}")
            summary["desvio_horas"] = summary.desvio_horas.map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
            summary["perc_acima_24h"] = summary.perc_acima_24h.map(lambda value: f"{value:.1f}%")
            st.dataframe(
                summary.rename(columns={
                    class_column: "Classificação da Chamada",
                    "media_horas": "Média (h)",
                    "mediana_horas": "Mediana (h)",
                    "desvio_horas": "Desvio Padrão (h)",
                    "contagem": "Nº de Chamadas",
                    "maximo_horas": "Máximo (h)",
                    "acima_24h": "Qtd > 24h",
                    "perc_acima_24h": "% > 24h",
                }),
                width="stretch",
                hide_index=True,
            )

st.markdown("---")
st.caption("Dashboard desenvolvido com Streamlit | Corpo de Bombeiros Militar de Minas Gerais - COBOM-BH")