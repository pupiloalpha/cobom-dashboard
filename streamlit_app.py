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

def parse_coordinate(valor):
    """Converte coordenada no formato -199.534.999 para -19.9534999"""
    if pd.isna(valor) or valor == '' or valor == ' ':
        return np.nan
    
    try:
        # Converte para string e remove espaços
        valor_str = str(valor).strip().replace(' ', '')
        
        # Se já for um número float, retorna
        try:
            return float(valor_str)
        except:
            pass
        
        # Remove pontos que separam milhares (mantém apenas o último ponto como separador decimal)
        if '.' in valor_str and valor_str.count('.') > 1:
            partes = valor_str.split('.')
            
            # Verifica se há sinal negativo
            if partes[0].startswith('-'):
                sinal = '-'
                partes[0] = partes[0][1:]
            else:
                sinal = ''
            
            # Remove zeros à esquerda da primeira parte
            primeira = partes[0].lstrip('0')
            if not primeira:
                primeira = '0'
            
            # Junta tudo: sinal + primeira parte + partes intermediárias + '.' + última parte
            if len(partes) >= 3:
                valor_convertido = sinal + primeira + ''.join(partes[1:-1]) + '.' + partes[-1]
                try:
                    return float(valor_convertido)
                except:
                    pass
        
        # Tenta substituir vírgula por ponto
        try:
            return float(valor_str.replace(',', '.'))
        except:
            pass
        
        return np.nan
    except:
        return np.nan

def extract_municipio(local):
    """Extrai município do campo local_do_fato"""
    if pd.isna(local):
        return np.nan
    try:
        local_str = str(local)
        partes = local_str.split(' - ')
        if len(partes) >= 2:
            # Pega a última parte que geralmente é o município
            municipio = partes[-1].strip()
            # Remove informações extras entre parênteses
            if '(' in municipio:
                municipio = municipio.split('(')[0].strip()
            return municipio
        return np.nan
    except:
        return np.nan

@st.cache_data
def load_data(uploaded_file):
    """Carrega e processa o arquivo de dados"""
    file_name = uploaded_file.name.lower()
    
    # Tenta ler com diferentes encodings e separadores
    encodings = ['latin-1', 'utf-8', 'utf-8-sig']
    separadores = [';', ',', '\t', '|']
    
    df = None
    
    # Primeiro, tenta identificar o formato pelo cabeçalho
    for encoding in encodings:
        try:
            uploaded_file.seek(0)
            first_line = uploaded_file.readline().decode(encoding, errors='ignore').strip()
            uploaded_file.seek(0)
            
            # Verifica se é o formato novo (com Nş chamada)
            if 'Nş chamada' in first_line or 'N° chamada' in first_line or 'Número chamada' in first_line:
                # Formato novo - separador ; e colunas específicas
                try:
                    df = pd.read_csv(uploaded_file, sep=';', encoding=encoding, dtype=str, on_bad_lines='skip')
                    if df.shape[1] >= 16:
                        break
                except:
                    continue
            elif '|' in first_line:
                # Formato antigo - separador |
                try:
                    df = pd.read_csv(uploaded_file, sep='|', encoding=encoding, dtype=str, on_bad_lines='skip')
                    if 'chamada_data_inclusao' in df.columns or df.shape[1] >= 10:
                        break
                except:
                    continue
            elif ',' in first_line:
                # Tentativa com vírgula
                try:
                    df = pd.read_csv(uploaded_file, sep=',', encoding=encoding, dtype=str, on_bad_lines='skip')
                    if df.shape[1] >= 10:
                        break
                except:
                    continue
        except:
            continue
    
    if df is None:
        st.error("❌ Não foi possível ler o arquivo. Verifique o formato.")
        return None
    
    # Limpa os nomes das colunas
    df.columns = df.columns.str.strip()
    
    # Verifica se é o formato novo (16 colunas)
    if df.shape[1] >= 16:
        # Mapeamento das colunas do novo formato
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
            14: 'data_hora_situacao_atual',
            15: 'evento_associado'
        }
        
        # Renomeia as colunas
        col_names = list(df.columns)
        for i, new_name in col_map.items():
            if i < len(col_names):
                col_names[i] = new_name
        df.columns = col_names
        # Mantém apenas as colunas mapeadas
        df = df[list(col_map.values())]
        
        st.info("📄 Formato CSV novo detectado (separador ;).")
        
        # Extrai município
        df['Chamada_atendimentos.local_municipio_nome'] = df['Chamada_atendimentos.local_do_fato'].apply(extract_municipio)
        
        # Converte data/hora de início
        def parse_dt(dt_str):
            if pd.isna(dt_str):
                return pd.NaT
            dt_str = str(dt_str).strip()
            # Tenta diferentes formatos
            formatos = ['%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
            for fmt in formatos:
                try:
                    return pd.to_datetime(dt_str, format=fmt)
                except:
                    continue
            try:
                return pd.to_datetime(dt_str)
            except:
                return pd.NaT
        
        df['data_hora_dt'] = df['data_hora_criacao'].apply(parse_dt)
        df['chamada_data_inclusao'] = df['data_hora_dt'].dt.normalize()
        df['chamada_hora_inclusao'] = df['data_hora_dt'].dt.time
        df['chamada_hora_inclusao'] = pd.to_timedelta(df['chamada_hora_inclusao'].astype(str))
        df['data_hora'] = df['chamada_data_inclusao'] + df['chamada_hora_inclusao']
        df.drop(columns=['data_hora_criacao', 'data_hora_dt'], inplace=True, errors='ignore')
        
        # Converte data/hora de fim
        df['data_hora_fim_dt'] = df['data_hora_situacao_atual'].apply(parse_dt)
        df['data_hora_fim'] = df['data_hora_fim_dt']
        df.drop(columns=['data_hora_situacao_atual', 'data_hora_fim_dt'], inplace=True, errors='ignore')
        
        # Converte coordenadas
        df['Chamada_atendimentos.local_latitude'] = df['Chamada_atendimentos.local_latitude'].apply(parse_coordinate)
        df['Chamada_atendimentos.local_longitude'] = df['Chamada_atendimentos.local_longitude'].apply(parse_coordinate)
        
    else:
        # Formato antigo
        if 'chamada_data_inclusao' not in df.columns:
            st.error("❌ Formato de arquivo não reconhecido.")
            return None
        
        df['chamada_data_inclusao'] = pd.to_datetime(df['chamada_data_inclusao'], format='%d/%m/%Y', errors='coerce')
        df['chamada_hora_inclusao'] = pd.to_timedelta(df['chamada_hora_inclusao'], errors='coerce')
        df['data_hora'] = df['chamada_data_inclusao'] + df['chamada_hora_inclusao']
        
        # Extrai município se necessário
        if 'Chamada_atendimentos.local_municipio_nome' not in df.columns:
            df['Chamada_atendimentos.local_municipio_nome'] = df['Chamada_atendimentos.local_do_fato'].apply(extract_municipio)
        
        # Converte coordenadas
        if 'Chamada_atendimentos.local_latitude' in df.columns:
            df['Chamada_atendimentos.local_latitude'] = df['Chamada_atendimentos.local_latitude'].apply(parse_coordinate)
        if 'Chamada_atendimentos.local_longitude' in df.columns:
            df['Chamada_atendimentos.local_longitude'] = df['Chamada_atendimentos.local_longitude'].apply(parse_coordinate)
    
    # Colunas auxiliares
    if 'chamada_data_inclusao' in df.columns:
        df['ano'] = df['chamada_data_inclusao'].dt.year
        df['mes'] = df['chamada_data_inclusao'].dt.month
        df['mes_ano'] = df['chamada_data_inclusao'].dt.to_period('M').astype(str)
        df['hora'] = df['chamada_hora_inclusao'].dt.total_seconds() // 3600
        df['hora'] = df['hora'].astype(int)
        df['dia_semana'] = df['chamada_data_inclusao'].dt.dayofweek
    
    # Remove linhas sem data
    df = df.dropna(subset=['chamada_data_inclusao'])
    
    if df.empty:
        st.error("❌ Nenhum dado válido encontrado no arquivo.")
        return None
    
    st.success(f"✅ Arquivo carregado com sucesso! {len(df)} registros encontrados.")
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

def extrair_fracao(unidade):
    if pd.isna(unidade):
        return 'Outros'
    unidade_str = str(unidade).strip()
    if not unidade_str or unidade_str.lower() == 'nan':
        return 'Outros'
    unidade_str = re.sub(r'\s*\([^)]*\)', '', unidade_str)
    partes = [p.strip() for p in unidade_str.split('/') if p.strip()]
    if not partes:
        return 'Outros'
    return ' / '.join(partes)

def extrair_recursos(df):
    if 'Empenhos.recurso_codigo_prefixo' not in df.columns:
        return []
    recursos = set()
    for val in df['Empenhos.recurso_codigo_prefixo'].dropna():
        val_str = str(val).strip()
        if not val_str:
            continue
        val_str = val_str.replace(' / ', ',')
        if ',' in val_str:
            for item in val_str.split(','):
                item = item.strip()
                if item:
                    recursos.add(item)
        else:
            recursos.add(val_str)
    return sorted(recursos)

def coluna_ou_none(df, *nomes):
    for nome in nomes:
        if nome in df.columns:
            return nome
    return None

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
    
    rec_filter = []

    if uploaded_files:
        dfs = {}
        for file in uploaded_files:
            try:
                df = load_data(file)
                if df is not None and not df.empty:
                    dfs[file.name] = df
                else:
                    st.warning(f"⚠️ O arquivo {file.name} não contém dados válidos.")
            except Exception as e:
                st.error(f"❌ Erro ao processar {file.name}: {str(e)[:200]}")
        
        if not dfs:
            st.error("❌ Nenhum arquivo pôde ser carregado. Verifique o formato dos arquivos.")
            st.stop()
        
        combined_df = pd.concat(
            [df.assign(arquivo=name) for name, df in dfs.items()],
            ignore_index=True
        )
        
        st.success(f"✅ {len(dfs)} arquivo(s) carregado(s)! Total: {len(combined_df)} registros.")
        
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
        
        municipios = sorted(df_filtro['Chamada_atendimentos.local_municipio_nome'].dropna().unique()) if 'Chamada_atendimentos.local_municipio_nome' in df_filtro.columns else []
        natureza = sorted(df_filtro['Chamada_atendimentos.natureza_descricao'].dropna().unique()) if 'Chamada_atendimentos.natureza_descricao' in df_filtro.columns else []
        coluna_classificacao = coluna_ou_none(df_filtro,
            'Chamada_atendimentos.chamada_classificacao_descricao',
            'chamada_classificacao_descricao',
            'Classificacao',
            'classificacao'
        )
        classificacoes = sorted(df_filtro[coluna_classificacao].dropna().unique()) if coluna_classificacao else []
        unidades = sorted(df_filtro['Chamada_atendimentos.unidade_servico_nome'].dropna().unique()) if 'Chamada_atendimentos.unidade_servico_nome' in df_filtro.columns else []
        recursos_unicos = extrair_recursos(df_filtro)

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
        if class_filter and coluna_classificacao:
            df_filtered = df_filtered[df_filtered[coluna_classificacao].isin(class_filter)]
        if uni_filter:
            df_filtered = df_filtered[df_filtered['Chamada_atendimentos.unidade_servico_nome'].isin(uni_filter)]
        if rec_filter:
            def has_selected_resource(val):
                if pd.isna(val):
                    return False
                resources = [r.strip() for r in str(val).split(',') if r.strip()]
                return any(r in resources for r in rec_filter)
            df_filtered = df_filtered[df_filtered['Empenhos.recurso_codigo_prefixo'].apply(has_selected_resource)]
        
        st.session_state.df_filtered = df_filtered
    else:
        st.info("👈 Faça upload de um ou mais arquivos .xlsx ou .csv para começar a análise.")
        st.stop()

if 'df_filtered' not in st.session_state:
    st.stop()

df_filtered = st.session_state.df_filtered

# Verifica se há dados
if df_filtered.empty:
    st.warning("⚠️ Nenhum dado disponível para análise. Tente carregar outro arquivo.")
    st.stop()

# Debug: Mostra informações sobre os dados carregados
with st.expander("ℹ️ Informações dos dados carregados", expanded=False):
    st.write(f"**Total de registros:** {len(df_filtered)}")
    st.write(f"**Colunas disponíveis:** {list(df_filtered.columns)}")
    st.write(f"**Primeiras linhas:**")
    st.dataframe(df_filtered.head(3))

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

natureza_top = df_filtered['Chamada_atendimentos.natureza_descricao'].mode()[0] if not df_filtered.empty and 'Chamada_atendimentos.natureza_descricao' in df_filtered.columns else "N/A"
class_col = coluna_ou_none(df_filtered,
    'Chamada_atendimentos.chamada_classificacao_descricao',
    'chamada_classificacao_descricao',
    'Classificacao',
    'classificacao'
)
classificacao_top = "N/A"
if class_col and not df_filtered.empty:
    mode_series = df_filtered[class_col].mode()
    if not mode_series.empty:
        classificacao_top = mode_series.iloc[0]

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
# CÁLCULO DO TEMPO DE ATENDIMENTO
# ==========================
if 'data_hora_fim' not in df_filtered.columns:
    df_filtered['data_hora_fim'] = pd.NaT

df_filtered['tempo_minutos'] = (df_filtered['data_hora_fim'] - df_filtered['data_hora']).dt.total_seconds() / 60
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
    
    if df_filtered.empty:
        st.warning("⚠️ Sem dados para exibir.")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            if 'Chamada_atendimentos.natureza_descricao' in df_filtered.columns and not df_filtered['Chamada_atendimentos.natureza_descricao'].dropna().empty:
                nat_counts = df_filtered['Chamada_atendimentos.natureza_descricao'].value_counts().reset_index()
                nat_counts.columns = ['natureza', 'count']
                nat_counts = nat_counts.head(15)
                fig = px.bar(nat_counts, x='natureza', y='count', title='Top 15 Naturezas',
                             labels={'natureza': '', 'count': 'Chamadas'}, template='plotly_white')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("ℹ️ Nenhum dado de natureza disponível.")
            
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
                    st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if 'Chamada_atendimentos.local_municipio_nome' in df_filtered.columns and not df_filtered['Chamada_atendimentos.local_municipio_nome'].dropna().empty:
                mun_counts = df_filtered['Chamada_atendimentos.local_municipio_nome'].value_counts().reset_index()
                mun_counts.columns = ['municipio', 'count']
                mun_counts = mun_counts.head(15)
                fig = px.bar(mun_counts, x='municipio', y='count', title='Top 15 Municípios',
                             labels={'municipio': '', 'count': 'Chamadas'}, template='plotly_white')
                st.plotly_chart(fig, use_container_width=True)
            
            if 'Chamada_atendimentos.unidade_servico_nome' in df_filtered.columns:
                df_filtered['bbm_rank'] = df_filtered['Chamada_atendimentos.unidade_servico_nome'].apply(extrair_bbm)
                uni_counts = df_filtered['bbm_rank'].value_counts().reset_index()
                uni_counts.columns = ['unidade', 'count']
                uni_counts = uni_counts[uni_counts['unidade'] != 'Outros'].head(15)
                if not uni_counts.empty:
                    fig = px.bar(uni_counts, x='unidade', y='count', title='Top 15 Unidades',
                                 labels={'unidade': '', 'count': 'Chamadas'}, template='plotly_white')
                    st.plotly_chart(fig, use_container_width=True)

                fracoes = df_filtered['Chamada_atendimentos.unidade_servico_nome'].dropna().apply(extrair_fracao)
                fracoes = fracoes[fracoes != 'Outros']
                if not fracoes.empty:
                    frac_counts = fracoes.value_counts().reset_index()
                    frac_counts.columns = ['fracao', 'count']
                    frac_counts = frac_counts.head(15)
                    fig = px.bar(frac_counts, x='fracao', y='count', title='Top 15 Frações / Unidades',
                                 labels={'fracao': 'Unidade e Fração', 'count': 'Chamadas'}, template='plotly_white')
                    fig.update_layout(
                        xaxis={'categoryorder': 'total descending'},
                        margin={'l': 40, 'r': 20, 't': 60, 'b': 180}
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
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
                        st.plotly_chart(fig, use_container_width=True)
        
        with col4:
            class_col = coluna_ou_none(df_filtered,
                'Chamada_atendimentos.chamada_classificacao_descricao',
                'chamada_classificacao_descricao',
                'Classificacao',
                'classificacao'
            )
            if class_col and not df_filtered[class_col].dropna().empty:
                class_counts = df_filtered[class_col].value_counts().reset_index()
                class_counts.columns = ['classificacao', 'count']
                class_counts = class_counts.head(10)
                fig = px.bar(class_counts, x='classificacao', y='count', title='Top 10 Classificações',
                             labels={'classificacao': '', 'count': 'Chamadas'}, template='plotly_white')
                st.plotly_chart(fig, use_container_width=True)

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
            st.plotly_chart(fig, use_container_width=True)
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
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("ℹ️ Dados insuficientes para realizar a projeção (mínimo 2 meses com ocorrências).")
    else:
        st.info("ℹ️ Nenhum dado disponível após os filtros aplicados.")
    
    daily = df_filtered.groupby(df_filtered['chamada_data_inclusao'].dt.date).size().reset_index(name='count')
    daily.columns = ['data', 'chamadas']
    fig = px.line(daily, x='data', y='chamadas', title='Chamadas por Dia',
                  labels={'data': 'Data', 'chamadas': 'Chamadas'}, template='plotly_white')
    st.plotly_chart(fig, use_container_width
