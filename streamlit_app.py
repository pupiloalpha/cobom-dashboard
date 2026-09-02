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

def detect_file_format(file):
    """Detecta se o arquivo é no formato novo (;) ou antigo (|)."""
    try:
        file.seek(0)
        # Tenta ler com latin-1 primeiro
        first_line = file.readline().decode('latin-1', errors='ignore').strip()
        file.seek(0)
        
        # Verifica se é o novo formato (separador ;)
        if ';' in first_line and '|' not in first_line:
            return 'novo'
        
        # Verifica se é o formato antigo (separador |)
        if '|' in first_line:
            return 'antigo'
        
        # Tenta detectar pelo cabeçalho
        if 'Nş chamada' in first_line or 'Número chamada' in first_line or 'N° chamada' in first_line:
            return 'novo'
        
        return 'desconhecido'
    except:
        return 'desconhecido'

def parse_coordinate(valor):
    """Converte coordenada no formato -199.534.999 para -19.9534999"""
    if pd.isna(valor) or valor == '':
        return np.nan
    
    try:
        # Remove espaços e converte para string
        valor_str = str(valor).strip().replace(' ', '')
        
        # Se já for um número float, retorna
        try:
            return float(valor_str)
        except:
            pass
        
        # Remove pontos que separam milhares (mantém apenas o último ponto como separador decimal)
        # Exemplo: -199.534.999 -> -19.9534999
        if '.' in valor_str and valor_str.count('.') > 1:
            # Separa por pontos
            partes = valor_str.split('.')
            # Se houver sinal negativo, preserva
            if partes[0].startswith('-'):
                sinal = '-'
                partes[0] = partes[0][1:]  # Remove o sinal
            else:
                sinal = ''
            
            # Junta todas as partes exceto a última sem ponto
            # e adiciona um ponto antes da última parte
            if len(partes) >= 3:
                # Exemplo: ['-199', '534', '999'] -> '-19.9534999'
                # Primeiro remove zeros à esquerda da primeira parte
                primeira = partes[0].lstrip('0')
                if not primeira:
                    primeira = '0'
                valor_convertido = sinal + primeira + ''.join(partes[1:-1]) + '.' + partes[-1]
                try:
                    return float(valor_convertido)
                except:
                    pass
        
        # Se tiver apenas um ponto, tenta converter diretamente
        try:
            return float(valor_str.replace(',', '.'))
        except:
            pass
        
        return np.nan
    except:
        return np.nan

@st.cache_data
def load_data(uploaded_file):
    file_name = uploaded_file.name.lower()
    formato = detect_file_format(uploaded_file)
    
    # ----- TENTATIVA 1: CSV separado por ";" (novo formato) -----
    if file_name.endswith('.csv') and (formato == 'novo' or formato == 'desconhecido'):
        # Tenta diferentes encodings, priorizando latin-1
        encodings = ['latin-1', 'utf-8', 'utf-8-sig']
        
        for encoding in encodings:
            try:
                uploaded_file.seek(0)
                # Primeiro tenta ler com sep=';'
                df = pd.read_csv(uploaded_file, sep=';', encoding=encoding,
                                 dtype=str, on_bad_lines='skip')
                df.columns = df.columns.str.strip()
                
                # Verifica se tem pelo menos as colunas mínimas do novo formato
                if df.shape[1] >= 16:
                    # Mapeamento correto das colunas
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
                    col_names = list(df.columns)
                    for i, new_name in col_map.items():
                        if i < len(col_names):
                            col_names[i] = new_name
                    df.columns = col_names
                    df = df[list(col_map.values())]
                    
                    st.info("📄 Formato CSV novo detectado (separador ;).")
                    
                    # Extrai município
                    def extract_municipio(local):
                        if pd.isna(local):
                            return np.nan
                        partes = str(local).split(' - ')
                        if len(partes) >= 2:
                            return partes[-1].strip()
                        return np.nan
                    
                    df['Chamada_atendimentos.local_municipio_nome'] = df['Chamada_atendimentos.local_do_fato'].apply(extract_municipio)
                    
                    # Converte data/hora de início - tenta múltiplos formatos
                    def parse_datetime(dt_str):
                        if pd.isna(dt_str):
                            return pd.NaT
                        dt_str = str(dt_str).strip()
                        # Tenta diferentes formatos
                        formatos = [
                            '%d/%m/%Y %H:%M',
                            '%d/%m/%Y %H:%M:%S',
                            '%d/%m/%Y %H:%M:%S.%f',
                            '%Y-%m-%d %H:%M:%S',
                            '%Y-%m-%d %H:%M'
                        ]
                        for fmt in formatos:
                            try:
                                return pd.to_datetime(dt_str, format=fmt)
                            except:
                                continue
                        # Se nenhum formato funcionar, tenta o pandas
                        try:
                            return pd.to_datetime(dt_str)
                        except:
                            return pd.NaT
                    
                    df['data_hora_criacao_dt'] = df['data_hora_criacao'].apply(parse_datetime)
                    
                    # Se falhou completamente, tenta o pandas direto
                    if df['data_hora_criacao_dt'].isna().all():
                        df['data_hora_criacao_dt'] = pd.to_datetime(df['data_hora_criacao'], errors='coerce')
                    
                    df['chamada_data_inclusao'] = df['data_hora_criacao_dt'].dt.normalize()
                    df['chamada_hora_inclusao'] = df['data_hora_criacao_dt'].dt.time
                    df['chamada_hora_inclusao'] = pd.to_timedelta(df['chamada_hora_inclusao'].astype(str))
                    df['data_hora'] = df['chamada_data_inclusao'] + df['chamada_hora_inclusao']
                    df.drop(columns=['data_hora_criacao', 'data_hora_criacao_dt'], inplace=True, errors='ignore')
                    
                    # Converte data/hora de fim
                    def parse_datetime_fim(dt_str):
                        if pd.isna(dt_str):
                            return pd.NaT
                        dt_str = str(dt_str).strip()
                        if dt_str == '':
                            return pd.NaT
                        formatos = [
                            '%d/%m/%Y %H:%M',
                            '%d/%m/%Y %H:%M:%S',
                            '%d/%m/%Y %H:%M:%S.%f',
                            '%Y-%m-%d %H:%M:%S',
                            '%Y-%m-%d %H:%M'
                        ]
                        for fmt in formatos:
                            try:
                                return pd.to_datetime(dt_str, format=fmt)
                            except:
                                continue
                        try:
                            return pd.to_datetime(dt_str)
                        except:
                            return pd.NaT
                    
                    df['data_hora_fim'] = df['data_hora_situacao_atual'].apply(parse_datetime_fim)
                    if df['data_hora_fim'].isna().all():
                        df['data_hora_fim'] = pd.to_datetime(df['data_hora_situacao_atual'], errors='coerce')
                    df.drop(columns=['data_hora_situacao_atual'], inplace=True, errors='ignore')
                    
                    # Converte coordenadas usando a função especializada
                    df['Chamada_atendimentos.local_latitude'] = df['Chamada_atendimentos.local_latitude'].apply(parse_coordinate)
                    df['Chamada_atendimentos.local_longitude'] = df['Chamada_atendimentos.local_longitude'].apply(parse_coordinate)
                    
                    # Colunas auxiliares
                    df['ano'] = df['chamada_data_inclusao'].dt.year
                    df['mes'] = df['chamada_data_inclusao'].dt.month
                    df['mes_ano'] = df['chamada_data_inclusao'].dt.to_period('M').astype(str)
                    df['hora'] = df['chamada_hora_inclusao'].dt.total_seconds() // 3600
                    df['hora'] = df['hora'].astype(int)
                    df['dia_semana'] = df['chamada_data_inclusao'].dt.dayofweek
                    
                    df = df.dropna(subset=['chamada_data_inclusao'])
                    st.success(f"✅ Arquivo carregado com sucesso! {len(df)} registros encontrados.")
                    return df
                    
            except Exception as e:
                st.warning(f"Erro ao ler com encoding {encoding}: {str(e)[:100]}")
                continue
        
        # Se chegou aqui, tenta o formato antigo
        st.warning("Não foi possível ler o arquivo com os encodings testados. Tentando formato antigo...")
        uploaded_file.seek(0)

    # ----- TENTATIVA 2: CSV separado por "|" (formato antigo) ou Excel -----
    if file_name.endswith('.csv'):
        header_line = detect_csv_header(uploaded_file)
        try:
            uploaded_file.seek(0)
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
    
    # Data/hora de fim (classificação)
    if 'Chamada_atendimentos.chamada_classificacao_data' in df.columns and 'Chamada_atendimentos.chamada_classificacao_hora' in df.columns:
        df['data_hora_fim'] = pd.to_datetime(
            df['Chamada_atendimentos.chamada_classificacao_data'].astype(str) + ' ' + 
            df['Chamada_atendimentos.chamada_classificacao_hora'].astype(str),
            format='%d/%m/%Y %H:%M:%S', errors='coerce'
        )
    else:
        df['data_hora_fim'] = pd.NaT
    
    # Converte coordenadas
    if 'Chamada_atendimentos.local_latitude' in df.columns:
        df['Chamada_atendimentos.local_latitude'] = df['Chamada_atendimentos.local_latitude'].apply(parse_coordinate)
    
    if 'Chamada_atendimentos.local_longitude' in df.columns:
        df['Chamada_atendimentos.local_longitude'] = df['Chamada_atendimentos.local_longitude'].apply(parse_coordinate)
    
    # Extrai município (se não existir)
    if 'Chamada_atendimentos.local_municipio_nome' not in df.columns:
        def extract_municipio(local):
            if pd.isna(local):
                return np.nan
            partes = str(local).split(' - ')
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
    """Retorna o nome completo da unidade com seu detalhamento de fração."""
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
    """Retorna lista ordenada de códigos de recursos únicos."""
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
    """Retorna o primeiro nome de coluna existente na lista, ou None."""
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

# [O restante do código permanece igual ao original...]
