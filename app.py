import hashlib

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.linear_model import LinearRegression
from streamlit_folium import st_folium

from data_loader import apply_filters, load_uploaded_data, process_dataframe
from utils.demo_data import generate_demo_cobom_data
from utils.helpers import (
    coluna_ou_none,
    detect_file_type,
    extrair_bbm,
    extrair_fracao,
    extrair_recursos,
)
from visualizations import (
    _apply_theme_layout,
    create_occurrence_map,
    plot_bar,
    plot_flags_overview,
    plot_flags_temporal,
    plot_histogram,
    plot_hourly_weekday_heatmap,
    plot_line,
    plot_natureza_grupos,
    plot_prioridade,
    plot_reds_origem,
    plot_resource_concentration,
    plot_situacao_operacional,
    plot_tempo_por_situacao,
)

st.set_page_config(page_title="Dashboard COBOM-BH", layout="wide", page_icon="🚒")
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { font-size: 1.1rem !important; font-weight: 600 !important; }
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
if "cached_file_signatures" not in st.session_state:
    st.session_state["cached_file_signatures"] = {}

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
        st.session_state["cached_file_signatures"] = {}

    if not uploaded_files:
        if st.session_state["use_demo_data"]:
            if st.button("🔄 Sair dos dados de demonstração", use_container_width=True):
                st.session_state["use_demo_data"] = False
                st.session_state["cached_dataframes"] = {}
                st.session_state["cached_file_signatures"] = {}
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
        - **Tipos de arquivo detectados**: `chamadas_classificadas` (base fechada) e `chamadas_ativas` (base operacional viva). O sistema identifica automaticamente e permite filtrar por tipo.
        - **Situação terminal**: apenas o valor `Classificada` remove a chamada da tela do despachante. Todos os demais valores (Terminada, Atribuída ao órgão, Em controle, No local, etc.) mantêm a chamada ativa — o tempo de atendimento é medido em relação a **agora**.
        """)
    st.stop()

with st.sidebar:
    if uploaded_files:
        current_files_map = {f.name: f for f in uploaded_files}
        current_file_signatures = {
            name: hashlib.sha256(uploaded_file.getvalue()).hexdigest()
            for name, uploaded_file in current_files_map.items()
        }
        removed_keys = [k for k in st.session_state["cached_dataframes"] if k not in current_files_map]
        for k in removed_keys:
            del st.session_state["cached_dataframes"][k]
            st.session_state["cached_file_signatures"].pop(k, None)

        new_files = [
            f for f in uploaded_files
            if st.session_state["cached_file_signatures"].get(f.name) != current_file_signatures[f.name]
        ]
        if new_files:
            with st.spinner(f"Carregando e processando {len(new_files)} arquivo(s)..."):
                for uploaded_file in new_files:
                    try:
                        dataframe = load_uploaded_data(uploaded_file)
                        if not dataframe.empty:
                            st.session_state["cached_dataframes"][uploaded_file.name] = dataframe
                            st.session_state["cached_file_signatures"][uploaded_file.name] = current_file_signatures[uploaded_file.name]
                        else:
                            st.warning(f"⚠️ O arquivo {uploaded_file.name} não contém dados válidos.")
                    except Exception as error:
                        st.error(f"Erro ao carregar {uploaded_file.name}: {error}")

    dataframes = st.session_state.get("cached_dataframes", {})
    if not dataframes:
        st.error("Nenhum arquivo pôde ser carregado.")
        st.stop()

    combined = pd.concat(
        [
            dataframe.assign(
                arquivo=name,
                tipo_arquivo=detect_file_type(dataframe, name),
            )
            for name, dataframe in dataframes.items()
        ],
        ignore_index=True,
    )

    if not st.session_state.get("use_demo_data"):
        st.success(f"✅ {len(dataframes)} arquivo(s) carregado(s) com sucesso!")

    if combined.empty:
        st.stop()

    st.header("🔍 Filtros")

    tipos_disponiveis = sorted(combined["tipo_arquivo"].dropna().unique().tolist())
    rotulos_tipo = {
        "classificadas": "✅ Classificadas",
        "ativas": "🚨 Ativas",
        "generico": "📄 Genérico",
    }
    tipos_selecionados = st.multiselect(
        "Tipo de arquivo",
        options=tipos_disponiveis,
        default=tipos_disponiveis,
        format_func=lambda v: rotulos_tipo.get(v, v),
        help="Restrinja a análise aos exports classificados, ativos, ou ambos.",
    )
    if not tipos_selecionados:
        tipos_selecionados = tipos_disponiveis

    st.subheader("📅 Período")
    available_dates = sorted(combined["chamada_data_inclusao"].dt.date.unique())
    data_inicio = st.date_input("Data inicial", value=min(available_dates), min_value=min(available_dates), max_value=max(available_dates))
    data_fim = st.date_input("Data final", value=max(available_dates), min_value=min(available_dates), max_value=max(available_dates))
    if data_inicio > data_fim:
        st.warning("⚠️ Data inicial não pode ser maior que a data final.")
        data_inicio, data_fim = data_fim, data_inicio

    selected_file = st.selectbox("Selecione um arquivo para análise detalhada (ou 'Todos')", ["Todos", *dataframes])

    if selected_file == "Todos":
        source = combined.copy()
    else:
        source = dataframes[selected_file].copy()
        if "tipo_arquivo" not in source.columns:
            source["tipo_arquivo"] = detect_file_type(source, selected_file)

    if tipos_selecionados and "tipo_arquivo" in source.columns:
        source = source[source["tipo_arquivo"].isin(tipos_selecionados)]
        if source.empty:
            st.warning("⚠️ Nenhum dado disponível para os tipos de arquivo selecionados.")
            st.stop()

    source = source[source["chamada_data_inclusao"].dt.date.between(data_inicio, data_fim)]

    municipality_column = "Chamada_atendimentos.local_municipio_nome"
    nature_column = "Chamada_atendimentos.natureza_descricao"
    unit_column = "Chamada_atendimentos.unidade_servico_nome"
    class_column = coluna_ou_none(
        source,
        "Chamada_atendimentos.chamada_classificacao_descricao",
        "chamada_classificacao_descricao",
        "Classificacao",
        "classificacao",
    )

    with st.expander("Filtros adicionais (em cascata)", expanded=True):
        all_municipalities = sorted(source[municipality_column].dropna().unique()) if municipality_column in source else []
        municipality_filter = st.multiselect("Município", all_municipalities)

        cascade_scope = source
        if municipality_filter and municipality_column in cascade_scope:
            cascade_scope = cascade_scope[cascade_scope[municipality_column].isin(municipality_filter)]

        available_natures = sorted(cascade_scope[nature_column].dropna().unique()) if nature_column in cascade_scope else []
        nature_filter = st.multiselect("Natureza", available_natures)

        available_classes = sorted(cascade_scope[class_column].dropna().unique()) if class_column else []
        class_filter = st.multiselect("Classificação da Chamada", available_classes)

        available_units = sorted(cascade_scope[unit_column].dropna().unique()) if unit_column in cascade_scope else []
        unit_filter = st.multiselect("Unidade", available_units)

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

# Campos de tempo (tab5 e tab6)
if "data_hora_fim" not in df_filtered:
    df_filtered["data_hora_fim"] = pd.NaT
df_filtered["tempo_minutos"] = (df_filtered["data_hora_fim"] - df_filtered["data_hora"]).dt.total_seconds() / 60
df_filtered = df_filtered[
    df_filtered["tempo_minutos"].isna() | df_filtered["tempo_minutos"].ge(0)
].copy()
df_filtered["tempo_horas"] = df_filtered["tempo_minutos"] / 60

if "situacao_terminal" not in df_filtered.columns:
    df_filtered["situacao_terminal"] = True

# Cards de métricas gerais
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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Rankings de Dados",
    "📈 Evolução e Projeção Temporal",
    "📊 Distribuição e Comparação",
    "🗺️ Mapa de Ocorrências",
    "⏱️ Tempo de Atendimento",
    "🚨 Operacional (Ativas)",
    "🏷️ Flags, Agências e Natureza",
])

# ===========================================================================
# TAB 1 — Rankings de Dados
# ===========================================================================
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

    # ---------------------------------------------------------------------
    # Classificações e Situações em gráficos SEPARADOS
    # ---------------------------------------------------------------------
    left, right = st.columns(2)
    with left:
        if "Empenhos.recurso_codigo_prefixo" in df_filtered:
            resources = df_filtered["Empenhos.recurso_codigo_prefixo"].fillna("").astype(str).str.replace(" / ", ",", regex=False).str.split(",").explode().str.strip()
            st.plotly_chart(plot_bar(counts(resources.to_frame(name="prefixo"), "prefixo"), "prefixo", "contagem", "Top 15 Viaturas Mais Empenhadas", 15), width="stretch")
    with right:
        # Gráfico exclusivo das CLASSIFICAÇÕES (Tipo de classificação)
        if class_column:
            class_series = (
                df_filtered[class_column].astype("string").str.strip()
            )
            class_series = class_series[class_series.notna() & class_series.ne("")]
            class_counts = (
                class_series.value_counts().rename_axis("classificacao").reset_index(name="contagem")
            )
            if not class_counts.empty:
                st.plotly_chart(
                    plot_bar(class_counts, "classificacao", "contagem", "Top 10 Classificações de Chamadas", 10),
                    width="stretch",
                )
            else:
                st.info("Sem classificações preenchidas no recorte atual.")
        else:
            st.info("Coluna de classificação indisponível neste recorte.")

    # Gráfico exclusivo das SITUAÇÕES OPERACIONAIS
    # Excluímos "Classificada" porque essa é a classificação final (terminal);
    # aqui queremos mostrar os estados ativos (Terminada, Atribuída ao órgão,
    # Em controle, No local, À caminho, Despachada, Em retorno, Suspensa, etc.)
    if "situacao_norm" in df_filtered.columns:
        sit_series = df_filtered["situacao_norm"].astype("string").str.strip()
        sit_series = sit_series[
            sit_series.notna()
            & sit_series.ne("")
            & ~sit_series.str.casefold().eq("classificada")
        ]
        sit_counts = (
            sit_series.value_counts().rename_axis("situacao").reset_index(name="contagem")
        )
        if not sit_counts.empty:
            st.plotly_chart(
                plot_bar(
                    sit_counts,
                    "situacao",
                    "contagem",
                    "Top 10 Situações Operacionais (Chamadas Ativas)",
                    10,
                ),
                width="stretch",
            )
            st.caption(
                "Estas são as situações operacionais distintas de **Classificada** — "
                "chamadas ainda ativas no sistema (o tempo é medido em relação a agora)."
            )
        else:
            st.info("Sem situações operacionais distintas de *Classificada* no recorte.")

    resource_concentration = plot_resource_concentration(df_filtered)
    if resource_concentration is not None:
        st.plotly_chart(resource_concentration, width="stretch")
        st.caption("As barras mostram a quantidade de viaturas em cada chamada ordenada. A linha indica quanto do total de viaturas está concentrado nas chamadas do ranking.")

# ===========================================================================
# TAB 2 — Evolução e Projeção Temporal
# ===========================================================================
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

        model = LinearRegression().fit(full[["indice"]], full["chamadas"])
        future_indices = pd.DataFrame({"indice": np.arange(full.indice.max() + 1, full.indice.max() + 7)})
        base_predictions = model.predict(future_indices)

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
        st.caption("A projeção combina a tendência linear histórica com fatores multiplicativos de sazonalidade mensal.")
    else:
        st.info("ℹ️ Dados insuficientes para realizar a projeção (mínimo 2 meses com ocorrências).")
    daily = df_filtered.groupby(df_filtered.chamada_data_inclusao.dt.date).size().rename("chamadas").reset_index(name="chamadas").rename(columns={"chamada_data_inclusao": "data"})
    st.plotly_chart(plot_line(daily, "data", "chamadas", None, "Volume Diário de Chamadas"), width="stretch")

# ===========================================================================
# TAB 3 — Distribuição e Comparação
# ===========================================================================
with tab3:
    st.header("📊 Distribuição e Comparação de Dados")

    st.subheader("🔥 Matriz de Calor de Plantão Operacional")
    heatmap_matrix = plot_hourly_weekday_heatmap(df_filtered)
    if heatmap_matrix is not None:
        st.plotly_chart(heatmap_matrix, width="stretch")
        st.caption("A matriz cruza os 7 dias da semana com as 24 horas do dia para identificar horários de pico.")

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
        # Pie exclusivo das CLASSIFICAÇÕES (não mistura com situações).
        if class_column:
            pie_series = df_filtered[class_column].astype("string").str.strip()
            pie_series = pie_series[pie_series.notna() & pie_series.ne("")]
            pie_data = (
                pie_series.value_counts()
                .rename_axis("classificacao").reset_index(name="contagem")
            )
            if not pie_data.empty:
                pie_fig = px.pie(
                    pie_data,
                    names="classificacao",
                    values="contagem",
                    title="Distribuição por Classificação da Chamada",
                )
                pie_fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(pie_fig, width="stretch")
            else:
                st.info("Sem classificações preenchidas no recorte.")
    with right:
        if unit_column in df_filtered:
            bbm_counts = counts(df_filtered.assign(bbm=df_filtered[unit_column].map(extrair_bbm)), "bbm", "chamadas")
            bbm_counts = bbm_counts[bbm_counts.bbm.ne("Outros")]
            st.plotly_chart(plot_bar(bbm_counts, "bbm", "chamadas", "Chamadas por Batalhão / Companhia Independente"), width="stretch")
            fractions = counts(df_filtered.assign(fracao=df_filtered[unit_column].map(extrair_fracao)), "fracao", "chamadas")
            fractions = fractions[fractions.fracao.ne("Outros")]
            st.plotly_chart(plot_bar(fractions, "fracao", "chamadas", "Detalhamento por Frações e Unidades Operacionais", 15), width="stretch")

# ===========================================================================
# TAB 4 — Mapa de Ocorrências
# ===========================================================================
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

# ===========================================================================
# TAB 5 — Tempo de Atendimento
# ===========================================================================
with tab5:
    st.header("⏱️ Tempo de Atendimento")
    terminal_mask = df_filtered["situacao_terminal"].fillna(True).astype(bool)

    metr_cols = st.columns(4)
    metr_cols[0].metric("📞 Total", f"{len(df_filtered):,}")
    metr_cols[1].metric("✅ Classificadas (encerradas)", f"{int(terminal_mask.sum()):,}")
    metr_cols[2].metric("🟡 Ativas (em andamento)", f"{int((~terminal_mask).sum()):,}")
    delta_dias = (df_filtered["chamada_data_inclusao"].max() - df_filtered["chamada_data_inclusao"].min()).days + 1
    metr_cols[3].metric("📅 Dias no recorte", f"{delta_dias}")

    st.caption(
        "Apenas chamadas com situação **Classificada** estão encerradas. Todas as outras "
        "(Terminada, Atribuída ao órgão, Em controle, Em direção, À caminho, No local, "
        "Despachada, Em retorno, Suspensa, etc.) continuam **ativas** — o tempo exibido é "
        "**decorrido desde a criação até agora**."
    )

    modo = st.radio(
        "Analisar:",
        ["Classificadas (tempo real)", "Ativas (tempo decorrido)", "Todas"],
        horizontal=True,
        key="tempo_modo",
    )
    if modo.startswith("Classificadas"):
        time_data = df_filtered[terminal_mask].dropna(subset=["data_hora_fim"]).copy()
    elif modo.startswith("Ativas"):
        time_data = df_filtered[~terminal_mask].dropna(subset=["data_hora_fim"]).copy()
    else:
        time_data = df_filtered.dropna(subset=["data_hora_fim"]).copy()

    if time_data.empty:
        st.info("ℹ️ Nenhum registro disponível para o modo selecionado.")
    else:
        max_time_limit = max(720.0, float(np.ceil(time_data.tempo_horas.max())))
        max_time = st.slider("Filtrar tempo máximo (horas) para análise", 1.0, max_time_limit, max_time_limit, 1.0)
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

        st.subheader("Distribuição do Tempo (em horas)")
        time_data["categoria"] = np.where(time_data.tempo_horas <= 24, "Até 24h", "Acima de 24h")
        fig = plot_histogram(
            time_data, "tempo_horas", "Histograma do Tempo",
            color="categoria", nbins=50,
            labels={"tempo_horas": "Tempo (horas)", "contagem": "Nº de Chamadas", "categoria": "Faixa"},
            barmode="stack",
        )
        fig.update_layout(legend_title_text="Faixa de Duração")
        st.plotly_chart(fig, width="stretch")

        over_data = time_data[time_data.tempo_horas > 24].assign(dias=lambda data: np.ceil(data.tempo_horas / 24).astype(int))
        if not over_data.empty:
            st.plotly_chart(
                plot_histogram(
                    over_data, "dias", "Distribuição dos Atendimentos com Duração > 24h (em dias)",
                    nbins=20, labels={"dias": "Duração (dias)", "contagem": "Nº de Chamadas"},
                ),
                width="stretch",
            )

        st.subheader("📋 Resumo por Classificação / Situação da Chamada")
        summary_data = time_data.copy()
        if class_column:
            summary_data["classificacao_exibicao"] = summary_data[class_column].astype("string").str.strip()
        else:
            summary_data["classificacao_exibicao"] = pd.Series(pd.NA, index=summary_data.index, dtype="string")
        if "situacao" in summary_data.columns:
            status_labels = summary_data["situacao"].astype("string").str.strip()
            summary_data["classificacao_exibicao"] = summary_data["classificacao_exibicao"].mask(
                summary_data["classificacao_exibicao"].isna() | summary_data["classificacao_exibicao"].eq(""),
                status_labels,
            )
        summary_data = summary_data[summary_data["classificacao_exibicao"].notna() & summary_data["classificacao_exibicao"].ne("")]
        if summary_data.empty:
            summary = pd.DataFrame(columns=["classificacao_exibicao", "contagem"])
        else:
            summary = summary_data.groupby("classificacao_exibicao").agg(
                media_horas=("tempo_horas", "mean"),
                mediana_horas=("tempo_horas", "median"),
                desvio_horas=("tempo_horas", "std"),
                contagem=("tempo_horas", "count"),
                maximo_horas=("tempo_horas", "max"),
            ).reset_index()
            summary["acima_24h"] = summary_data["classificacao_exibicao"].where(summary_data.tempo_horas > 24).value_counts().reindex(summary["classificacao_exibicao"]).fillna(0).to_numpy().astype(int)
            summary["perc_acima_24h"] = (summary.acima_24h / summary.contagem * 100).round(1)

        minimum = st.number_input("Mínimo de registros por classificação", 1, 100, 5, 1, key="min_reg_class")
        summary = summary[summary.contagem >= minimum].sort_values("media_horas", ascending=False) if "contagem" in summary and not summary.empty else summary
        if summary.empty:
            st.info(f"Nenhuma classificação com pelo menos {minimum} registros.")
        else:
            for column in ["media_horas", "mediana_horas", "maximo_horas"]:
                summary[column] = summary[column].map(lambda value: f"{value:.2f}")
            summary["desvio_horas"] = summary.desvio_horas.map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
            summary["perc_acima_24h"] = summary.perc_acima_24h.map(lambda value: f"{value:.1f}%")
            st.dataframe(
                summary.rename(columns={
                    "classificacao_exibicao": "Classificação / Situação",
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

        st.divider()
        st.subheader("⏱️ Tempo por Situação Operacional")
        fig = plot_tempo_por_situacao(df_filtered if modo == "Todas" else time_data, min_registros=3)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Poucas situações distintas para gerar o boxplot.")

# ===========================================================================
# TAB 6 — Operacional (Ativas)
# ---------------------------------------------------------------------------
# Foco desta aba: chamadas AINDA EM ANDAMENTO.
# Gráficos/tabelas duplicados de outras abas foram removidos:
#   - Boxplot "Tempo por Situação Operacional" -> já em tab5
#   - Mapa das chamadas ativas -> já coberto pela tab4 (mesma df_filtered)
# Permanecem: métricas, distribuição por situação operacional, SLA e tabela.
# ===========================================================================
with tab6:
    st.header("🚨 Painel Operacional — Chamadas em Andamento")
    if "situacao_terminal" not in df_filtered.columns:
        st.info("Estrutura de situação não disponível neste recorte.")
    else:
        ativas = df_filtered[~df_filtered["situacao_terminal"].fillna(True).astype(bool)].copy()
        if ativas.empty:
            st.info("✅ Nenhuma chamada em andamento no recorte atual.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🚨 Em andamento", f"{len(ativas):,}")
            tmed = ativas["tempo_no_estado_horas"].mean() if "tempo_no_estado_horas" in ativas else np.nan
            c2.metric("⏱️ Tempo médio decorrido", f"{tmed:.2f} h" if pd.notna(tmed) else "N/D")
            mode_nat = ativas["Chamada_atendimentos.natureza_descricao"].mode() if "Chamada_atendimentos.natureza_descricao" in ativas else pd.Series(dtype=str)
            c3.metric("🔥 Natureza dominante", (str(mode_nat.iloc[0])[:38] + "…") if not mode_nat.empty else "N/D")
            c4.metric("📍 Municípios ativos", ativas["Chamada_atendimentos.local_municipio_nome"].nunique() if "Chamada_atendimentos.local_municipio_nome" in ativas else 0)

            st.divider()
            st.subheader("📊 Distribuição por Situação Operacional")
            fig = plot_situacao_operacional(ativas)
            if fig is not None:
                st.plotly_chart(fig, width="stretch")
                st.caption(
                    "Cada fatia representa uma situação operacional distinta de **Classificada** — "
                    "chamadas ainda pendentes na tela do despachante."
                )
            else:
                st.info("Sem situações operacionais para exibir.")

            st.subheader("⏱️ SLA de Chamadas em Aberto")
            if "tempo_no_estado_horas" in ativas:
                faixas = pd.cut(
                    ativas["tempo_no_estado_horas"],
                    bins=[-0.01, 1, 3, 6, 12, 24, np.inf],
                    labels=["<1h", "1-3h", "3-6h", "6-12h", "12-24h", ">24h"],
                )
                dist = (
                    faixas.value_counts()
                    .reindex(["<1h", "1-3h", "3-6h", "6-12h", "12-24h", ">24h"])
                    .rename_axis("faixa").reset_index(name="chamadas")
                )
                fig_sla = px.bar(
                    dist, x="faixa", y="chamadas",
                    title="Distribuição do Tempo Decorrido (SLA)",
                    color="chamadas", color_continuous_scale="OrRd",
                )
                fig_sla.update_layout(
                    xaxis_title="Faixa de tempo", yaxis_title="Nº de Chamadas",
                    coloraxis_showscale=False,
                )
                st.plotly_chart(_apply_theme_layout(fig_sla), width="stretch")

            st.subheader("📋 Chamadas em Andamento")
            colunas_visiveis = [
                "chamada_numero",
                "Chamada_atendimentos.local_municipio_nome",
                "Chamada_atendimentos.natureza_descricao",
                "situacao_norm",
                "tempo_no_estado_horas",
                "Chamada_atendimentos.unidade_servico_nome",
                "reds_origem",
            ]
            colunas_visiveis = [c for c in colunas_visiveis if c in ativas.columns]
            tabela = ativas[colunas_visiveis].copy()
            if "tempo_no_estado_horas" in tabela.columns:
                tabela = tabela.sort_values("tempo_no_estado_horas", ascending=False)
            st.dataframe(tabela, width="stretch", hide_index=True)

# ===========================================================================
# TAB 7 — Flags, Agências e Natureza
# ===========================================================================
with tab7:
    st.header("🏷️ Flags Operacionais, Agências e Categorias de Natureza")

    st.subheader("🚩 Sinalizações Operacionais")
    fig = plot_flags_overview(df_filtered)
    if fig is not None:
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Nenhuma das flags (Alerta, Destaque, Envolve autoridade) está disponível.")

    left, right = st.columns(2)
    with left:
        meses_distintos = df_filtered["chamada_data_inclusao"].dt.to_period("M").nunique() if "chamada_data_inclusao" in df_filtered else 0
        freq = "MS" if meses_distintos > 2 else "D"
        fig = plot_flags_temporal(df_filtered, freq=freq)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")
    with right:
        if "alerta_flag" in df_filtered.columns and "Chamada_atendimentos.local_municipio_nome" in df_filtered.columns:
            top_alerta = (
                df_filtered[df_filtered["alerta_flag"].fillna(False)]
                ["Chamada_atendimentos.local_municipio_nome"]
                .value_counts().head(10).rename_axis("municipio").reset_index(name="chamadas")
            )
            if not top_alerta.empty:
                st.plotly_chart(plot_bar(top_alerta, "municipio", "chamadas", "Top 10 Municípios com Alerta"), width="stretch")
            else:
                st.info("Nenhuma chamada marcada com Alerta no recorte.")

    st.divider()
    st.subheader("🏢 Origem do REDS / Agências Solicitantes")
    left, right = st.columns(2)
    with left:
        fig = plot_reds_origem(df_filtered)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")
    with right:
        if "reds_multiagencia" in df_filtered.columns:
            multi = df_filtered["reds_multiagencia"].fillna(False).astype(bool)
            c1, c2 = st.columns(2)
            c1.metric("🤝 Multiagência (PM+BM)", int(multi.sum()))
            c2.metric("% do total", f"{multi.mean()*100:.1f}%")
            if "natureza_grupo" in df_filtered.columns and multi.any():
                cross = (
                    df_filtered[multi]
                    .groupby("natureza_grupo").size()
                    .sort_values(ascending=False).head(8)
                    .rename_axis("grupo").reset_index(name="chamadas")
                )
                if not cross.empty:
                    st.plotly_chart(plot_bar(cross, "grupo", "chamadas", "Grupos com Mais Chamadas Multiagência"), width="stretch")

    st.divider()
    st.subheader("🧭 Natureza por Grupo Temático e Prioridade")
    left, right = st.columns(2)
    with left:
        fig = plot_natureza_grupos(df_filtered)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")
    with right:
        fig = plot_prioridade(df_filtered)
        if fig is not None:
            st.plotly_chart(fig, width="stretch")

    if {"natureza_grupo", "natureza_prioridade"}.issubset(df_filtered.columns):
        pivot = pd.pivot_table(
            df_filtered,
            index="natureza_grupo",
            columns="natureza_prioridade",
            values="chamada_numero",
            aggfunc="count",
            fill_value=0,
        ).rename(columns={1: "Alta", 2: "Média", 3: "Baixa"})
        st.subheader("📊 Natureza × Prioridade (contagem de chamadas)")
        st.dataframe(pivot, width="stretch")

st.markdown("---")
st.caption("Dashboard desenvolvido com Streamlit | Corpo de Bombeiros Militar de Minas Gerais - COBOM-BH")
