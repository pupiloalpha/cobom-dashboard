import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import io
import re

# Configuração da página
st.set_page_config(page_title="Dashboard COBOM-BH", layout="wide")

# ==========================
# CSS PERSONALIZADO PARA AJUSTE DE FONTES
# ==========================
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
    }
    .stMetric {
        font-size: 0.9rem !important;
    }
    .stMetric label {
        font-size: 0.9rem !important;
    }
    .stMetric .stMetricValue {
        font-size: 1.4rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚒 Dashboard Interativo - COBOM-BH")
st.markdown("Análise de chamadas do Corpo de Bombeiros Militar de Minas Gerais recebidas no COBOM-BH")

# ==========================
# FUNÇÕES AUXILIARES
# ==========================

def detect_csv_header(file):
    """Retorna o índice da linha que contém o cabeçalho (início com 'chamada_numero')."""
    file.seek(0)
    lines = file.readlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(b'|')]
        if parts and parts[0] == b'chamada_numero':
            file.seek(0)
            return i
    for i, line in enumerate(lines):
        if line.count(b'|') > 10:
            file.seek(0)
            return i
    file.seek(0)
    return 0

@st.cache_data
def load_data(uploaded_file):
    file_name = uploaded_file.name.lower()
    
    # ----- TENTATIVA 1: CSV separado por ";" (novo formato) -----
    if file_name.endswith('.csv'):
        encodings = ['utf-8-sig', 'utf-8', 'latin-1']
        for encoding in encodings:
            try:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=';', encoding=encoding,
                                 dtype=str, on_bad_lines='skip')
                df.columns = df.columns.str.strip()
                
                if df.shape[1] >= 16:
                    col_map = {
                        0: 'chamada_numero',
                        1: 'reds',
                        2: 'data_hora_criacao',
                        3: 'Chamada_atendimentos.local_do_fato',
                        4: 'Chamada_atendimentos.local_latitude',
                        5: 'Chamada_atendimentos.local_longitude',
                        6: 'Chamada_atendimentos.natureza_descricao',
                        7: 'Chamada_atendimentos.unidade_servico_nome',
                        8: 'Empenhos.recurso_codigo_prefixo',
                        9: 'alerta',
                        10: 'destaque',
                        11: 'envolve_autoridade',
                        12: 'Chamada_atendimentos.chamada_classificacao_descricao',
                        13: 'situacao',
                        14: 'data_hora_situacao_atual',  # Fim do atendimento (classificação)
                        15: 'evento_associado'
                    }
                    col_names = list(df.columns)
                    for i, new_name in col_map.items():
                        if i < len(col_names):
                            col_names[i] = new_name
                    df.columns = col_names
                    df = df[list(col_map.values())]
                    
                    #st.info("📄 Formato CSV novo detectado (separador ;).")
                    
                    # Extrai município
                    def extract_municipio(local):
                        if pd.isna(local):
                            return np.nan
                        partes = local.split(' - ')
                        if len(partes) >= 2:
                            return partes[-1].strip()
                        return np.nan
                    df['Chamada_atendimentos.local_municipio_nome'] = df['Chamada_atendimentos.local_do_fato'].apply(extract_municipio)
                    
                    # Converte data/hora de início
                    dt_series = pd.to_datetime(df['data_hora_criacao'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                    df['chamada_data_inclusao'] = dt_series.dt.normalize()
                    df['chamada_hora_inclusao'] = dt_series.dt.time
                    df['chamada_hora_inclusao'] = pd.to_timedelta(df['chamada_hora_inclusao'].astype(str))
                    df['data_hora'] = df['chamada_data_inclusao'] + df['chamada_hora_inclusao']
                    df.drop(columns=['data_hora_criacao'], inplace=True)
                    
                    # Converte data/hora de fim (classificação)
                    fim_series = pd.to_datetime(df['data_hora_situacao_atual'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                    df['data_hora_fim'] = fim_series
                    df.drop(columns=['data_hora_situacao_atual'], inplace=True)
                    
                    # Converte coordenadas
                    for col in ['Chamada_atendimentos.local_latitude', 'Chamada_atendimentos.local_longitude']:
                        df[col] = df[col].apply(
                            lambda x: float(str(x).replace(',', '.')) 
                            if pd.notna(x) and str(x).strip() != '' else np.nan
                        )
                    
                    # Colunas auxiliares
                    df['ano'] = df['chamada_data_inclusao'].dt.year
                    df['mes'] = df['chamada_data_inclusao'].dt.month
                    df['mes_ano'] = df['chamada_data_inclusao'].dt.to_period('M').astype(str)
                    df['hora'] = df['chamada_hora_inclusao'].dt.total_seconds() // 3600
                    df['hora'] = df['hora'].astype(int)
                    df['dia_semana'] = df['chamada_data_inclusao'].dt.dayofweek
                    
                    df = df.dropna(subset=['chamada_data_inclusao'])
                    return df
            except Exception as e:
                continue
        
        st.warning("Não foi possível ler o arquivo com os encodings testados. Tentando formato antigo...")
        uploaded_file.seek(0)

    # ----- TENTATIVA 2: CSV separado por "|" (formato antigo) ou Excel -----
    if file_name.endswith('.csv'):
        header_line = detect_csv_header(uploaded_file)
        try:
            df = pd.read_csv(uploaded_file, sep='|', skiprows=header_line,
                             dtype=str, engine='python', encoding='latin-1')
        except Exception as e:
            st.error(f"Erro ao ler CSV antigo: {e}")
            st.stop()
        
        df.columns = df.columns.str.strip()
        if 'chamada_data_inclusao' not in df.columns:
            uploaded_file.seek(0)
            lines = uploaded_file.read().decode('latin-1').splitlines()
            header_line_content = lines[header_line].strip()
            col_names = [c.strip() for c in header_line_content.split('|')]
            data_lines = lines[header_line+1:]
            data_str = '\n'.join(data_lines)
            from io import StringIO
            df = pd.read_csv(StringIO(data_str), sep='|', names=col_names,
                             dtype=str, engine='python', encoding='latin-1')
            df = df[df[col_names[0]].notna()]
    else:
        # Excel
        df = pd.read_excel(uploaded_file, sheet_name="BD_Cobom")
    
    # ----- Processamento do formato antigo -----
    if 'chamada_data_inclusao' not in df.columns:
        st.error("❌ O arquivo não contém a coluna 'chamada_data_inclusao' e não pôde ser processado.")
        st.stop()
    
    df['chamada_data_inclusao'] = pd.to_datetime(df['chamada_data_inclusao'], format='%d/%m/%Y', errors='coerce')
    df['chamada_hora_inclusao'] = pd.to_timedelta(df['chamada_hora_inclusao'], errors='coerce')
    df['data_hora'] = df['chamada_data_inclusao'] + df['chamada_hora_inclusao']
    
    # Data/hora de fim (classificação) - colunas N e O
    if 'Chamada_atendimentos.chamada_classificacao_data' in df.columns and 'Chamada_atendimentos.chamada_classificacao_hora' in df.columns:
        df['data_hora_fim'] = pd.to_datetime(
            df['Chamada_atendimentos.chamada_classificacao_data'].astype(str) + ' ' + 
            df['Chamada_atendimentos.chamada_classificacao_hora'].astype(str),
            format='%d/%m/%Y %H:%M:%S', errors='coerce'
        )
    else:
        # Se não houver colunas de fim, criar como NaT
        df['data_hora_fim'] = pd.NaT
    
    # Converte coordenadas
    if 'Chamada_atendimentos.local_latitude' in df.columns:
        def parse_coord(x):
            if pd.isna(x):
                return np.nan
            if isinstance(x, (int, float)):
                return float(x)
            if isinstance(x, str):
                cleaned = x.strip().replace(',', '.').replace(' ', '')
                try:
                    return float(cleaned)
                except:
                    return np.nan
            return np.nan
        df['Chamada_atendimentos.local_latitude'] = df['Chamada_atendimentos.local_latitude'].apply(parse_coord)
    
    if 'Chamada_atendimentos.local_longitude' in df.columns:
        def parse_coord_long(x):
            if pd.isna(x):
                return np.nan
            if isinstance(x, (int, float)):
                return float(x)
            if isinstance(x, str):
                cleaned = x.strip().replace(',', '.').replace(' ', '')
                try:
                    return float(cleaned)
                except:
                    return np.nan
            return np.nan
        df['Chamada_atendimentos.local_longitude'] = df['Chamada_atendimentos.local_longitude'].apply(parse_coord_long)
    
    # Extrai município (se não existir)
    if 'Chamada_atendimentos.local_municipio_nome' not in df.columns:
        def extract_municipio(local):
            if pd.isna(local):
                return np.nan
            partes = local.split(' - ')
            if len(partes) >= 2:
                return partes[-1].strip()
            return np.nan
        df['Chamada_atendimentos.local_municipio_nome'] = df['Chamada_atendimentos.local_do_fato'].apply(extract_municipio)
    
    # Colunas auxiliares
    df['mes_ano'] = df['chamada_data_inclusao'].dt.to_period('M').astype(str)
    df['ano'] = df['chamada_data_inclusao'].dt.year
    df['mes'] = df['chamada_data_inclusao'].dt.month
    df['hora'] = df['chamada_hora_inclusao'].dt.total_seconds() // 3600
    df['hora'] = df['hora'].astype(int)
    df['dia_semana'] = df['chamada_data_inclusao'].dt.dayofweek
    
    df = df.dropna(subset=['chamada_data_inclusao'])
    return df

def extrair_bbm(unidade):
    if pd.isna(unidade):
        return 'Outros'
    unidade_str = str(unidade)
    if 'BBM' in unidade_str:
        for part in unidade_str.split('/'):
            part = part.strip()
            if 'BBM' in part:
                if '(' in part:
                    part = part.split('(')[0].strip()
                return part
    if 'CIA IND' in unidade_str:
        for part in unidade_str.split('/'):
            part = part.strip()
            if 'CIA IND' in part:
                if '(' in part:
                    part = part.split('(')[0].strip()
                return part
    return 'Outros'

def extrair_recursos_unicos(df):
    """Retorna lista ordenada de códigos de recursos únicos a partir da coluna 'Empenhos.recurso_codigo_prefixo'."""
    if 'Empenhos.recurso_codigo_prefixo' not in df.columns:
        return []
    recursos = set()
    for val in df['Empenhos.recurso_codigo_prefixo'].dropna():
        val_str = str(val).strip()
        if not val_str:
            continue
        if ',' in val_str:
            for item in val_str.split(','):
                item = item.strip()
                if item:
                    recursos.add(item)
        else:
            recursos.add(val_str)
    return sorted(recursos)

# ==========================
# SIDEBAR - UPLOAD E FILTROS
# ==========================

with st.sidebar:
    st.header("📂 Carregar Dados")
    uploaded_files = st.file_uploader(
        "Selecione um ou mais arquivos .xlsx ou .csv",
        type=['xlsx', 'csv'],
        accept_multiple_files=True
    )
    
    rec_filter = []  # Garante que a variável exista mesmo sem arquivos

    if uploaded_files:
        dfs = {}
        for file in uploaded_files:
            df = load_data(file)
            dfs[file.name] = df
        
        combined_df = pd.concat(
            [df.assign(arquivo=name) for name, df in dfs.items()],
            ignore_index=True
        )
        
        st.success(f"✅ {len(uploaded_files)} arquivo(s) carregado(s)!")
        
        st.header("🔍 Filtros")
        
        st.subheader("📅 Período")
        datas_disponiveis = sorted(combined_df['chamada_data_inclusao'].dt.date.unique())
        if len(datas_disponiveis) > 0:
            data_inicio = st.date_input(
                "Data inicial",
                value=min(datas_disponiveis),
                min_value=min(datas_disponiveis),
                max_value=max(datas_disponiveis)
            )
            data_fim = st.date_input(
                "Data final",
                value=max(datas_disponiveis),
                min_value=min(datas_disponiveis),
                max_value=max(datas_disponiveis)
            )
            if data_inicio > data_fim:
                st.warning("⚠️ Data inicial não pode ser maior que a data final.")
                data_inicio, data_fim = data_fim, data_inicio
        else:
            data_inicio = None
            data_fim = None
        
        arquivos_disponiveis = list(dfs.keys())
        arquivo_selecionado = st.selectbox(
            "Selecione um arquivo para análise detalhada (ou 'Todos')",
            ["Todos"] + arquivos_disponiveis
        )
        
        if arquivo_selecionado != "Todos":
            df_filtro = dfs[arquivo_selecionado]
        else:
            df_filtro = combined_df
        
        if data_inicio is not None and data_fim is not None:
            df_filtro = df_filtro[
                (df_filtro['chamada_data_inclusao'].dt.date >= data_inicio) &
                (df_filtro['chamada_data_inclusao'].dt.date <= data_fim)
            ]
        
        municipios = sorted(df_filtro['Chamada_atendimentos.local_municipio_nome'].dropna().unique())
        natureza = sorted(df_filtro['Chamada_atendimentos.natureza_descricao'].dropna().unique())
        classificacoes = sorted(df_filtro['Chamada_atendimentos.chamada_classificacao_descricao'].dropna().unique())
        unidades = sorted(df_filtro['Chamada_atendimentos.unidade_servico_nome'].dropna().unique())
        # NOVO: filtro de recursos empenhados
        recursos_unicos = extrair_recursos_unicos(df_filtro)
        
        with st.expander("Filtros adicionais", expanded=True):
            mun_filter = st.multiselect("Município", municipios, default=[])
            nat_filter = st.multiselect("Natureza", natureza, default=[])
            class_filter = st.multiselect("Classificação da Chamada", classificacoes, default=[])
            uni_filter = st.multiselect("Unidade", unidades, default=[])
            rec_filter = st.multiselect("Recursos Empenhados", recursos_unicos, default=[])
        
        df_filtered = df_filtro.copy()
        if mun_filter:
            df_filtered = df_filtered[df_filtered['Chamada_atendimentos.local_municipio_nome'].isin(mun_filter)]
        if nat_filter:
            df_filtered = df_filtered[df_filtered['Chamada_atendimentos.natureza_descricao'].isin(nat_filter)]
        if class_filter:
            df_filtered = df_filtered[df_filtered['Chamada_atendimentos.chamada_classificacao_descricao'].isin(class_filter)]
        if uni_filter:
            df_filtered = df_filtered[df_filtered['Chamada_atendimentos.unidade_servico_nome'].isin(uni_filter)]
        # Filtro por recursos empenhados
        if rec_filter:
            def has_selected_resource(val):
                if pd.isna(val):
                    return False
                resources = [r.strip() for r in str(val).split(',') if r.strip()]
                return any(r in resources for r in rec_filter)
            df_filtered = df_filtered[df_filtered['Empenhos.recurso_codigo_prefixo'].apply(has_selected_resource)]
        
        # Armazenar em session_state para uso após a sidebar
        st.session_state.df_filtered = df_filtered
    else:
        st.info("👈 Faça upload de um ou mais arquivos .xlsx ou .csv para começar a análise.")
        st.stop()

# Verificar se df_filtered está disponível
if 'df_filtered' not in st.session_state:
    st.stop()

# Recuperar df_filtered do session_state
df_filtered = st.session_state.df_filtered

# ==========================
# CARDS DE MÉTRICAS
# ==========================

total_chamadas = len(df_filtered)
media_diaria = total_chamadas / max(1, len(df_filtered['chamada_data_inclusao'].dt.date.unique()))
total_municipios = df_filtered['Chamada_atendimentos.local_municipio_nome'].nunique()

if 'Chamada_atendimentos.unidade_servico_nome' in df_filtered.columns:
    bbm_series = df_filtered['Chamada_atendimentos.unidade_servico_nome'].apply(extrair_bbm)
    unidade_top = bbm_series.mode()[0] if not bbm_series.empty else "N/A"
else:
    unidade_top = "N/A"

natureza_top = df_filtered['Chamada_atendimentos.natureza_descricao'].mode()[0] if not df_filtered.empty else "N/A"
classificacao_top = df_filtered['Chamada_atendimentos.chamada_classificacao_descricao'].mode()[0] if not df_filtered.empty else "N/A"

col1, col2, col3 = st.columns(3)
col1.metric("📞 Total de Chamadas", f"{total_chamadas:,}")
col2.metric("📊 Média Diária", f"{media_diaria:.1f}")
col3.metric("📍 Municípios Atendidos", total_municipios)

col4, col5, col6 = st.columns(3)
col4.metric("🚒 Unidade Mais Acionada", unidade_top)
col5.metric("🔥 Natureza Mais Comum", natureza_top)
col6.metric("📋 Classificação Mais Frequente", classificacao_top)

st.divider()

# ==========================
# CÁLCULO DO TEMPO DE ATENDIMENTO (preparação dos dados)
# ==========================
# Garantir que a coluna data_hora_fim exista e seja datetime
if 'data_hora_fim' not in df_filtered.columns:
    df_filtered['data_hora_fim'] = pd.NaT

# Calcular tempo em minutos
df_filtered['tempo_minutos'] = (df_filtered['data_hora_fim'] - df_filtered['data_hora']).dt.total_seconds() / 60
# Remover tempos negativos ou nulos
df_filtered = df_filtered[df_filtered['tempo_minutos'] >= 0]
df_filtered['tempo_horas'] = df_filtered['tempo_minutos'] / 60

# ==========================
# ABAS
# ==========================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Rankings de Dados",
    "📈 Evolução e Projeção Temporal",
    "📊 Distribuição e Comparação",
    "🗺️ Mapa de Ocorrências",
    "⏱️ Tempo de Atendimento"
])

# ==========================
# ABA 1 - RANKINGS
# ==========================

with tab1:
    st.header("📊 Rankings de Dados")
    col1, col2 = st.columns(2)
    
    with col1:
        nat_counts = df_filtered['Chamada_atendimentos.natureza_descricao'].value_counts().reset_index()
        nat_counts.columns = ['natureza', 'count']
        nat_counts = nat_counts.head(15)
        fig = px.bar(nat_counts, x='natureza', y='count', title='Top 15 Naturezas',
                     labels={'natureza': '', 'count': 'Chamadas'}, template='plotly_white')
        st.plotly_chart(fig, width='stretch')
        
        if 'Chamada_atendimentos.local_do_fato' in df_filtered.columns:
            locais = df_filtered['Chamada_atendimentos.local_do_fato'].dropna()
            locais = locais[locais.str.strip() != '']
            locais = locais[locais.str.strip().str.upper() != 'N/A']
            if not locais.empty:
                loc_counts = locais.value_counts().reset_index()
                loc_counts.columns = ['logradouro', 'count']
                loc_counts = loc_counts.head(15)
                fig = px.bar(loc_counts, x='logradouro', y='count', title='Top 15 Logradouros',
                             labels={'logradouro': '', 'count': 'Chamadas'}, template='plotly_white')
                st.plotly_chart(fig, width='stretch')
    
    with col2:
        mun_counts = df_filtered['Chamada_atendimentos.local_municipio_nome'].value_counts().reset_index()
        mun_counts.columns = ['municipio', 'count']
        mun_counts = mun_counts.head(15)
        fig = px.bar(mun_counts, x='municipio', y='count', title='Top 15 Municípios',
                     labels={'municipio': '', 'count': 'Chamadas'}, template='plotly_white')
        st.plotly_chart(fig, width='stretch')
        
        if 'Chamada_atendimentos.unidade_servico_nome' in df_filtered.columns:
            df_filtered['bbm_rank'] = df_filtered['Chamada_atendimentos.unidade_servico_nome'].apply(extrair_bbm)
            uni_counts = df_filtered['bbm_rank'].value_counts().reset_index()
            uni_counts.columns = ['unidade', 'count']
            uni_counts = uni_counts[uni_counts['unidade'] != 'Outros'].head(15)
            if not uni_counts.empty:
                fig = px.bar(uni_counts, x='unidade', y='count', title='Top 15 Unidades',
                             labels={'unidade': '', 'count': 'Chamadas'}, template='plotly_white')
                st.plotly_chart(fig, width='stretch')
    
    col3, col4 = st.columns(2)
    with col3:
        if 'Empenhos.recurso_codigo_prefixo' in df_filtered.columns:
            prefixos_series = df_filtered['Empenhos.recurso_codigo_prefixo'].dropna()
            prefixos_series = prefixos_series[prefixos_series.str.strip() != '']
            if not prefixos_series.empty:
                all_prefixos = []
                for item in prefixos_series:
                    if ',' in str(item):
                        partes = [p.strip() for p in str(item).split(',') if p.strip()]
                        all_prefixos.extend(partes)
                    else:
                        all_prefixos.append(str(item).strip())
                if all_prefixos:
                    prefix_counts = pd.Series(all_prefixos).value_counts().reset_index()
                    prefix_counts.columns = ['prefixo', 'count']
                    prefix_counts = prefix_counts.head(15)
                    fig = px.bar(prefix_counts, x='prefixo', y='count', title='Top 15 Viaturas Mais Empenhadas',
                                 labels={'prefixo': '', 'count': 'Empenhos'}, template='plotly_white')
                    st.plotly_chart(fig, width='stretch')
    
    with col4:
        class_counts = df_filtered['Chamada_atendimentos.chamada_classificacao_descricao'].value_counts().reset_index()
        class_counts.columns = ['classificacao', 'count']
        class_counts = class_counts.head(10)
        fig = px.bar(class_counts, x='classificacao', y='count', title='Top 10 Classificações',
                     labels={'classificacao': '', 'count': 'Chamadas'}, template='plotly_white')
        st.plotly_chart(fig, width='stretch')

# ==========================
# ABA 2 - EVOLUÇÃO
# ==========================

with tab2:
    st.header("📈 Evolução e Projeção Temporal")
    
    if not df_filtered.empty:
        monthly = df_filtered.groupby(['ano', 'mes']).size().reset_index(name='chamadas')
        anos_distintos = monthly['ano'].unique()
        if len(anos_distintos) >= 2:
            fig = px.line(monthly, x='mes', y='chamadas', color='ano',
                          title='Comparação Mensal por Ano (dados filtrados)',
                          labels={'mes': 'Mês', 'chamadas': 'Chamadas'},
                          template='plotly_white')
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("ℹ️ Selecione um período que contenha pelo menos dois anos distintos para a comparação mensal.")
    else:
        st.info("ℹ️ Nenhum dado disponível após os filtros.")
    
    if not df_filtered.empty:
        monthly = df_filtered.groupby(['ano', 'mes']).size().reset_index(name='chamadas')
        if len(monthly) >= 2:
            min_date = df_filtered['chamada_data_inclusao'].min()
            max_date = df_filtered['chamada_data_inclusao'].max()
            all_months = pd.date_range(start=min_date, end=max_date, freq='MS').to_period('M')
            full_index = pd.DataFrame({'ano': all_months.year, 'mes': all_months.month})
            monthly_full = full_index.merge(monthly, on=['ano', 'mes'], how='left').fillna(0)
            
            monthly_full['periodo'] = pd.to_datetime(monthly_full['ano'].astype(str) + '-' + monthly_full['mes'].astype(str).str.zfill(2))
            monthly_full = monthly_full.sort_values('periodo').reset_index(drop=True)
            monthly_full['indice'] = range(len(monthly_full))
            
            X = monthly_full[['indice']].values
            y = monthly_full['chamadas'].values
            model = LinearRegression()
            model.fit(X, y)
            
            ultimo_indice = monthly_full['indice'].max()
            futuro_indices = np.array(range(ultimo_indice + 1, ultimo_indice + 7)).reshape(-1, 1)
            previsoes = model.predict(futuro_indices)
            
            residuos = y - model.predict(X)
            desvio = np.std(residuos)
            
            ultima_data = monthly_full['periodo'].iloc[-1]
            future_dates = [ultima_data + pd.DateOffset(months=i) for i in range(1, 7)]
            future_periods = [d.to_period('M').strftime('%Y-%m') for d in future_dates]
            
            df_historico = monthly_full[['periodo', 'chamadas']].copy()
            df_historico['periodo_str'] = df_historico['periodo'].dt.strftime('%Y-%m')
            df_historico['tipo'] = 'Histórico'
            
            df_future = pd.DataFrame({
                'periodo': future_dates,
                'periodo_str': future_periods,
                'chamadas': previsoes,
                'tipo': 'Projeção'
            })
            
            df_upper = df_future.copy()
            df_upper['chamadas'] = df_upper['chamadas'] + desvio
            df_upper['tipo'] = 'Limite Superior'
            
            df_lower = df_future.copy()
            df_lower['chamadas'] = df_lower['chamadas'] - desvio
            df_lower['chamadas'] = df_lower['chamadas'].clip(lower=0)
            df_lower['tipo'] = 'Limite Inferior'
            
            df_completo = pd.concat([df_historico, df_future, df_upper, df_lower], ignore_index=True)
            
            fig = px.line(df_completo, x='periodo_str', y='chamadas', color='tipo',
                          title='Projeção de Chamadas (próximos 6 meses) com Desvio Padrão',
                          labels={'periodo_str': 'Mês/Ano', 'chamadas': 'Chamadas'},
                          template='plotly_white')
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("ℹ️ Dados insuficientes para realizar a projeção (mínimo 2 meses com ocorrências).")
    else:
        st.info("ℹ️ Nenhum dado disponível após os filtros aplicados.")
    
    daily = df_filtered.groupby(df_filtered['chamada_data_inclusao'].dt.date).size().reset_index(name='count')
    daily.columns = ['data', 'chamadas']
    fig = px.line(daily, x='data', y='chamadas', title='Chamadas por Dia',
                  labels={'data': 'Data', 'chamadas': 'Chamadas'}, template='plotly_white')
    st.plotly_chart(fig, width='stretch')

# ==========================
# ABA 3 - DISTRIBUIÇÃO
# ==========================

with tab3:
    st.header("📊 Distribuição e Comparação de Dados")
    
    col1, col2 = st.columns(2)
    
    with col1:
        hour_counts = df_filtered['hora'].value_counts().sort_index().reset_index()
        hour_counts.columns = ['hora', 'chamadas']
        fig = px.bar(hour_counts, x='hora', y='chamadas', title='Chamadas por Hora do Dia',
                     labels={'hora': 'Hora', 'chamadas': 'Chamadas'}, template='plotly_white')
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        dias_semana = {0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'}
        df_filtered['dia_semana_nome'] = df_filtered['dia_semana'].map(dias_semana)
        week_counts = df_filtered['dia_semana_nome'].value_counts().reindex(
            ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        ).reset_index()
        week_counts.columns = ['dia', 'chamadas']
        fig = px.bar(week_counts, x='dia', y='chamadas', title='Chamadas por Dia da Semana',
                     labels={'dia': '', 'chamadas': 'Chamadas'}, template='plotly_white')
        st.plotly_chart(fig, width='stretch')
    
    col3, col4 = st.columns(2)
    
    with col3:
        class_counts = df_filtered['Chamada_atendimentos.chamada_classificacao_descricao'].value_counts().reset_index()
        class_counts.columns = ['classificacao', 'count']
        fig = px.pie(class_counts, names='classificacao', values='count',
                     title='Distribuição por Classificação', template='plotly_white')
        st.plotly_chart(fig, width='stretch')
    
    with col4:
        if 'Chamada_atendimentos.unidade_servico_nome' in df_filtered.columns:
            df_filtered['bbm'] = df_filtered['Chamada_atendimentos.unidade_servico_nome'].apply(extrair_bbm)
            bbm_counts = df_filtered['bbm'].value_counts().reset_index()
            bbm_counts.columns = ['bbm', 'chamadas']
            bbm_counts = bbm_counts[bbm_counts['bbm'] != 'Outros']
            try:
                bbm_counts['ordem'] = bbm_counts['bbm'].str.extract(r'(\d+)').astype(float)
                bbm_counts = bbm_counts.sort_values('ordem')
            except:
                pass
            if not bbm_counts.empty:
                fig = px.bar(bbm_counts, x='bbm', y='chamadas', title='Chamadas por BBM / CIA IND',
                             labels={'bbm': '', 'chamadas': 'Chamadas'}, template='plotly_white')
                st.plotly_chart(fig, width='stretch')

# ==========================
# ABA 4 - MAPA
# ==========================

with tab4:
    st.header("🗺️ Mapa de Ocorrências")
    
    if 'Chamada_atendimentos.local_latitude' in df_filtered.columns and 'Chamada_atendimentos.local_longitude' in df_filtered.columns:
        map_df = df_filtered.dropna(subset=['Chamada_atendimentos.local_latitude', 'Chamada_atendimentos.local_longitude'])
        
        if not map_df.empty:
            try:
                import folium
                from streamlit_folium import st_folium
                from folium.plugins import MarkerCluster
                
                center_lat = map_df['Chamada_atendimentos.local_latitude'].mean()
                center_lon = map_df['Chamada_atendimentos.local_longitude'].mean()
                
                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=9,
                    tiles='OpenStreetMap',
                    control_scale=True
                )
                
                marker_cluster = MarkerCluster().add_to(m)
                
                if len(map_df) > 5000:
                    map_df_sample = map_df.sample(5000, random_state=42)
                else:
                    map_df_sample = map_df
                
                def safe_map_text(value, default='N/A', max_len=None):
                    if pd.isna(value):
                        text = default
                    else:
                        text = str(value)
                    if max_len is not None and len(text) > max_len:
                        text = text[:max_len]
                    return text

                for idx, row in map_df_sample.iterrows():
                    lat = row['Chamada_atendimentos.local_latitude']
                    lon = row['Chamada_atendimentos.local_longitude']
                    municipio = safe_map_text(row.get('Chamada_atendimentos.local_municipio_nome', 'N/A'))
                    natureza = safe_map_text(row.get('Chamada_atendimentos.natureza_descricao', 'N/A'))
                    local = safe_map_text(row.get('Chamada_atendimentos.local_do_fato', 'N/A'))
                    
                    popup_text = f"""
                    <b>📍 {municipio}</b><br>
                    <b>Natureza:</b> {natureza}<br>
                    <b>Local:</b> {local}
                    """
                    
                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(popup_text, max_width=300),
                        tooltip=f"{municipio} - {safe_map_text(natureza, 'N/A', 30)}..."
                    ).add_to(marker_cluster)
                
                st_folium(m, width=1200, height=600)
                st.caption(f"📊 Mostrando {len(map_df_sample)} de {len(map_df)} ocorrências com coordenadas válidas.")
                
            except ImportError:
                st.warning("⚠️ Bibliotecas 'folium' e 'streamlit-folium' não instaladas. Execute: pip install folium streamlit-folium")
            except Exception as e:
                st.warning(f"Não foi possível gerar o mapa: {e}")
        else:
            st.info("ℹ️ Nenhum dado com coordenadas disponíveis para exibir no mapa.")
    else:
        st.info("ℹ️ Colunas de latitude/longitude não encontradas nos dados.")

# ==========================
# ABA 5 - TEMPO DE ATENDIMENTO
# ==========================

with tab5:
    st.header("⏱️ Tempo de Atendimento")
    
    # Filtrar registros com data_hora_fim disponível
    df_tempo = df_filtered.dropna(subset=['data_hora_fim']).copy()
    
    if df_tempo.empty:
        st.info("ℹ️ Nenhum registro com data/hora de classificação (fim) disponível para análise de tempo.")
    else:
        # Remover tempos negativos (já feito globalmente) e outliers extremos (opcional)
        max_tempo = st.slider(
            "Filtrar tempo máximo (horas) para análise",
            min_value=1.0,
            max_value=720.0,  # 30 dias
            value=168.0,      # 7 dias
            step=1.0,
            help="Remover ocorrências com tempo acima deste limite para melhor visualização."
        )
        df_tempo_filtrado = df_tempo[df_tempo['tempo_horas'] <= max_tempo].copy()
        
        # Métricas
        media = df_tempo_filtrado['tempo_horas'].mean()
        mediana = df_tempo_filtrado['tempo_horas'].median()
        maximo = df_tempo_filtrado['tempo_horas'].max()
        total_registros = len(df_tempo_filtrado)
        acima_24h = df_tempo_filtrado[df_tempo_filtrado['tempo_horas'] > 24].shape[0]
        perc_acima_24h = (acima_24h / total_registros * 100) if total_registros > 0 else 0
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("📊 Média (h)", f"{media:.2f}")
        col2.metric("📊 Mediana (h)", f"{mediana:.2f}")
        col3.metric("📈 Máximo (h)", f"{maximo:.2f}")
        col4.metric("📋 Total de Registros", f"{total_registros:,}")
        col5.metric("⏰ > 24h", f"{acima_24h} ({perc_acima_24h:.1f}%)")
        
        st.divider()
        
        # Gráfico 1: Distribuição geral com destaque para > 24h
        st.subheader("Distribuição do Tempo de Atendimento (em horas)")
        # Criar uma coluna para categorizar
        df_tempo_filtrado['categoria'] = np.where(df_tempo_filtrado['tempo_horas'] <= 24, 'Até 24h', 'Acima de 24h')
        
        fig1 = px.histogram(
            df_tempo_filtrado,
            x='tempo_horas',
            color='categoria',
            nbins=50,
            title='Histograma do Tempo de Atendimento',
            labels={'tempo_horas': 'Horas', 'count': 'Número de Chamadas'},
            template='plotly_white',
            barmode='stack'
        )
        fig1.update_layout(legend_title_text='')
        st.plotly_chart(fig1, width='stretch')
        
        # Gráfico 2: Apenas > 24h (em dias)
        df_acima_24h = df_tempo_filtrado[df_tempo_filtrado['tempo_horas'] > 24].copy()
        if not df_acima_24h.empty:
            df_acima_24h['dias'] = np.ceil(df_acima_24h['tempo_horas'] / 24).astype(int)
            fig2 = px.histogram(
                df_acima_24h,
                x='dias',
                nbins=20,
                title='Distribuição dos Atendimentos com Duração > 24 horas (em dias)',
                labels={'dias': 'Dias', 'count': 'Número de Chamadas'},
                template='plotly_white'
            )
            st.plotly_chart(fig2, width='stretch')
        else:
            st.info("Nenhuma ocorrência com tempo superior a 24 horas.")
        
        # Exibir estatísticas descritivas adicionais em tabela
        st.subheader("Estatísticas Descritivas")
        desc = df_tempo_filtrado['tempo_horas'].describe().reset_index()
        desc.columns = ['Estatística', 'Horas']
        desc['Horas'] = desc['Horas'].map(lambda x: f"{x:.2f}")
        st.dataframe(desc, use_container_width=True)

st.markdown("---")
st.caption("Dashboard desenvolvido com Streamlit | Dados do COBOM-BH")