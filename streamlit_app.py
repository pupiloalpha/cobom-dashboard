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
        valor_str = str(valor).strip().replace(' ', '')
        
        # Tenta converter diretamente
        try:
            return float(valor_str)
        except:
            pass
        
        # Converte formato brasileiro (ex: -199.534.999)
        if '.' in valor_str and valor_str.count('.') > 1:
            partes = valor_str.split('.')
            
            if partes[0].startswith('-'):
                sinal = '-'
                partes[0] = partes[0][1:]
            else:
                sinal = ''
            
            primeira = partes[0].lstrip('0')
            if not primeira:
                primeira = '0'
            
            if len(partes) >= 3:
                valor_convertido = sinal + primeira + ''.join(partes[1:-1]) + '.' + partes[-1]
                try:
                    return float(valor_convertido)
                except:
                    pass
        
        # Tenta com vírgula como separador decimal
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
            municipio = partes[-1].strip()
            if '(' in municipio:
                municipio = municipio.split('(')[0].strip()
            return municipio
        return np.nan
    except:
        return np.nan

@st.cache_data
def load_data(uploaded_file):
    """Carrega e processa o arquivo de dados"""
    
    # Definição dos nomes padronizados das colunas
    COLUNAS_PADRONIZADAS = {
        'Nº chamada': 'chamada_numero',
        'Nş chamada': 'chamada_numero',
        'N° chamada': 'chamada_numero',
        'Número chamada': 'chamada_numero',
        
        'Nº REDS': 'reds',
        'Nş REDS': 'reds',
        'N° REDS': 'reds',
        
        'Data/hora de criação': 'data_hora_criacao',
        'Data/hora de criaçăo': 'data_hora_criacao',
        'Data/hora criacao': 'data_hora_criacao',
        
        'Local do fato': 'Chamada_atendimentos.local_do_fato',
        
        'Latitude  do local': 'Chamada_atendimentos.local_latitude',
        'Latitude do local': 'Chamada_atendimentos.local_latitude',
        
        'Longitude do local': 'Chamada_atendimentos.local_longitude',
        
        'Natureza': 'Chamada_atendimentos.natureza_descricao',
        
        'Unidade Responsável': 'Chamada_atendimentos.unidade_servico_nome',
        'Unidade Responsavel': 'Chamada_atendimentos.unidade_servico_nome',
        
        'Recursos empenhados': 'Empenhos.recurso_codigo_prefixo',
        
        'Alerta': 'alerta',
        'Destaque': 'destaque',
        'Envolve autoridade': 'envolve_autoridade',
        
        'Tipo de classificação': 'Chamada_atendimentos.chamada_classificacao_descricao',
        'Tipo de classificaçăo': 'Chamada_atendimentos.chamada_classificacao_descricao',
        'Classificacao': 'Chamada_atendimentos.chamada_classificacao_descricao',
        'classificacao': 'Chamada_atendimentos.chamada_classificacao_descricao',
        
        'Situação': 'situacao',
        'Situaçăo': 'situacao',
        
        'Data/hora da situação atual': 'data_hora_situacao_atual',
        'Data/hora da situaçăo atual': 'data_hora_situacao_atual',
        
        'Evento associado': 'evento_associado'
    }
    
    # Lista de colunas obrigatórias
    COLUNAS_OBRIGATORIAS = [
        'chamada_numero',
        'data_hora_criacao',
        'Chamada_atendimentos.local_do_fato'
    ]
    
    # Lista de encodings para tentar
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    
    # Lista de separadores para tentar
    separadores = [';', ',', '\t', '|']
    
    df = None
    
    # Tenta diferentes combinações de encoding e separador
    for encoding in encodings:
        for sep in separadores:
            try:
                uploaded_file.seek(0)
                
                # Lê o arquivo
                df_temp = pd.read_csv(
                    uploaded_file, 
                    sep=sep, 
                    encoding=encoding, 
                    dtype=str,
                    on_bad_lines='warn',
                    engine='python'
                )
                
                # Limpa nomes das colunas
                df_temp.columns = df_temp.columns.str.strip()
                
                # Verifica se alguma coluna conhecida está presente
                colunas_encontradas = set(df_temp.columns)
                colunas_conhecidas = set(COLUNAS_PADRONIZADAS.keys())
                
                if colunas_encontradas.intersection(colunas_conhecidas):
                    df = df_temp
                    st.info(f"✅ Arquivo lido com encoding: {encoding}, separador: '{sep}'")
                    break
                    
            except Exception as e:
                continue
        
        if df is not None:
            break
    
    # Se não conseguiu ler, tenta uma abordagem mais flexível
    if df is None:
        try:
            uploaded_file.seek(0)
            # Tenta ler todas as linhas como texto e detectar separador
            conteudo = uploaded_file.read().decode('utf-8', errors='ignore')
            linhas = conteudo.split('\n')
            
            if len(linhas) > 1:
                # Detecta separador pela primeira linha
                primeira_linha = linhas[0]
                for sep in [';', '\t', '|', ',']:
                    if sep in primeira_linha:
                        uploaded_file.seek(0)
                        df = pd.read_csv(
                            uploaded_file, 
                            sep=sep, 
                            encoding='utf-8',
                            dtype=str,
                            on_bad_lines='skip',
                            engine='python'
                        )
                        break
        except:
            pass
    
    if df is None:
        st.error("❌ Não foi possível ler o arquivo. Verifique o formato.")
        return None
    
    # Limpa nomes das colunas novamente
    df.columns = df.columns.str.strip()
    
    # Cria dicionário de mapeamento baseado nas colunas encontradas
    rename_dict = {}
    colunas_originais = list(df.columns)
    
    for col_original in colunas_originais:
        col_limpa = col_original.strip()
        for nome_original, nome_padronizado in COLUNAS_PADRONIZADAS.items():
            if col_limpa == nome_original or col_limpa.lower() == nome_original.lower():
                rename_dict[col_original] = nome_padronizado
                break
    
    # Aplica renomeação
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    # Verifica se temos as colunas obrigatórias
    colunas_faltando = [col for col in COLUNAS_OBRIGATORIAS if col not in df.columns]
    if colunas_faltando:
        st.warning(f"⚠️ Colunas não encontradas: {colunas_faltando}")
        st.warning(f"Colunas disponíveis: {list(df.columns)}")
        
        # Tenta encontrar colunas similares
        for col in colunas_faltando:
            for col_existente in df.columns:
                if col.lower() in col_existente.lower() or col_existente.lower() in col.lower():
                    df[col] = df[col_existente]
                    st.info(f"✅ Mapeamento automático: '{col_existente}' → '{col}'")
                    break
    
    # Verifica novamente após mapeamento automático
    colunas_faltando = [col for col in COLUNAS_OBRIGATORIAS if col not in df.columns]
    if colunas_faltando:
        st.error(f"❌ Colunas obrigatórias não encontradas: {colunas_faltando}")
        st.error("Verifique se o arquivo está no formato correto.")
        return None
    
    # Adiciona coluna de município
    if 'Chamada_atendimentos.local_do_fato' in df.columns:
        df['Chamada_atendimentos.local_municipio_nome'] = df['Chamada_atendimentos.local_do_fato'].apply(extract_municipio)
    
    # Função de parsing de data
    def parse_dt(dt_str):
        if pd.isna(dt_str):
            return pd.NaT
        
        dt_str = str(dt_str).strip()
        if not dt_str or dt_str.lower() in ['nan', 'null', '']:
            return pd.NaT
        
        # Lista de formatos possíveis
        formatos = [
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%d/%m/%Y',
            '%Y-%m-%d'
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
    
    # Processa datas
    if 'data_hora_criacao' in df.columns:
        df['data_hora_dt'] = df['data_hora_criacao'].apply(parse_dt)
        
        # Remove registros com data inválida
        df = df.dropna(subset=['data_hora_dt'])
        
        if df.empty:
            st.error("❌ Nenhuma data válida encontrada no arquivo.")
            return None
        
        df['chamada_data_inclusao'] = df['data_hora_dt'].dt.normalize()
        df['chamada_hora_inclusao'] = df['data_hora_dt'].dt.time
        df['chamada_hora_inclusao'] = pd.to_timedelta(df['chamada_hora_inclusao'].astype(str))
        df['data_hora'] = df['chamada_data_inclusao'] + df['chamada_hora_inclusao']
        df.drop(columns=['data_hora_criacao', 'data_hora_dt'], inplace=True, errors='ignore')
    
    if 'data_hora_situacao_atual' in df.columns:
        df['data_hora_fim_dt'] = df['data_hora_situacao_atual'].apply(parse_dt)
        df['data_hora_fim'] = df['data_hora_fim_dt']
        df.drop(columns=['data_hora_situacao_atual', 'data_hora_fim_dt'], inplace=True, errors='ignore')
    
    # Processa coordenadas
    if 'Chamada_atendimentos.local_latitude' in df.columns:
        df['Chamada_atendimentos.local_latitude'] = df['Chamada_atendimentos.local_latitude'].apply(parse_coordinate)
    if 'Chamada_atendimentos.local_longitude' in df.columns:
        df['Chamada_atendimentos.local_longitude'] = df['Chamada_atendimentos.local_longitude'].apply(parse_coordinate)
    
    # Adiciona colunas de tempo
    if 'chamada_data_inclusao' in df.columns:
        df['ano'] = df['chamada_data_inclusao'].dt.year
        df['mes'] = df['chamada_data_inclusao'].dt.month
        df['mes_ano'] = df['chamada_data_inclusao'].dt.to_period('M').astype(str)
        if 'chamada_hora_inclusao' in df.columns:
            df['hora'] = df['chamada_hora_inclusao'].dt.total_seconds() // 3600
            df['hora'] = df['hora'].astype(int)
        df['dia_semana'] = df['chamada_data_inclusao'].dt.dayofweek
    
    if df.empty:
        st.error("❌ Nenhum dado válido encontrado no arquivo.")
        return None
    
    st.success(f"✅ Arquivo carregado com sucesso! {len(df)} registros encontrados.")
    
    # Mostra informações sobre as colunas encontradas
    with st.expander("📋 Estrutura do arquivo carregado"):
        st.write("**Colunas encontradas:**")
        for col in df.columns:
            st.write(f"- {col}")
    
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
    st.plotly_chart(fig, use_container_width=True)

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
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        dias_semana = {0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'}
        df_filtered['dia_semana_nome'] = df_filtered['dia_semana'].map(dias_semana)
        week_counts = df_filtered['dia_semana_nome'].value_counts().reindex(
            ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        ).reset_index()
        week_counts.columns = ['dia', 'chamadas']
        fig = px.bar(week_counts, x='dia', y='chamadas', title='Chamadas por Dia da Semana',
                     labels={'dia': '', 'chamadas': 'Chamadas'}, template='plotly_white')
        st.plotly_chart(fig, use_container_width=True)
    
    col3, col4 = st.columns(2)
    
    with col3:
        class_col = coluna_ou_none(df_filtered,
            'Chamada_atendimentos.chamada_classificacao_descricao',
            'chamada_classificacao_descricao',
            'Classificacao',
            'classificacao'
        )
        if class_col:
            class_counts = df_filtered[class_col].value_counts().reset_index()
            class_counts.columns = ['classificacao', 'count']
            fig = px.pie(class_counts, names='classificacao', values='count',
                         title='Distribuição por Classificação', template='plotly_white')
            st.plotly_chart(fig, use_container_width=True)
    
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
                st.plotly_chart(fig, use_container_width=True)

            fracoes = df_filtered['Chamada_atendimentos.unidade_servico_nome'].dropna().apply(extrair_fracao)
            fracoes = fracoes[fracoes != 'Outros']
            if not fracoes.empty:
                frac_counts = fracoes.value_counts().reset_index()
                frac_counts.columns = ['fracao', 'chamadas']
                frac_counts = frac_counts.head(15)
                fig = px.bar(frac_counts, x='fracao', y='chamadas', title='Detalhamento por Frações / Unidades',
                             labels={'fracao': 'Unidade e Fração', 'chamadas': 'Chamadas'}, template='plotly_white')
                fig.update_layout(
                    xaxis={'categoryorder': 'total descending'},
                    margin={'l': 40, 'r': 20, 't': 60, 'b': 180}
                )
                st.plotly_chart(fig, use_container_width=True)

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
                        text = text[:max_len] + '...'
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
    
    df_tempo = df_filtered.dropna(subset=['data_hora_fim']).copy()
    
    if df_tempo.empty:
        st.info("ℹ️ Nenhum registro com data/hora de classificação (fim) disponível para análise de tempo.")
    else:
        max_tempo = st.slider(
            "Filtrar tempo máximo (horas) para análise",
            min_value=1.0,
            max_value=720.0,
            value=168.0,
            step=1.0,
            help="Remover ocorrências com tempo acima deste limite para melhor visualização."
        )
        df_tempo_filtrado = df_tempo[df_tempo['tempo_horas'] <= max_tempo].copy()
        
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
        
        st.subheader("Distribuição do Tempo de Atendimento (em horas)")
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
        st.plotly_chart(fig1, use_container_width=True)
        
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
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Nenhuma ocorrência com tempo superior a 24 horas.")
        
        st.subheader("📋 Resumo por Classificação da Chamada")
        
        class_col = coluna_ou_none(df_tempo_filtrado,
            'Chamada_atendimentos.chamada_classificacao_descricao',
            'chamada_classificacao_descricao',
            'Classificacao',
            'classificacao'
        )
        if class_col:
            df_class = df_tempo_filtrado.groupby(class_col).agg(
                media_horas=('tempo_horas', 'mean'),
                mediana_horas=('tempo_horas', 'median'),
                desvio_horas=('tempo_horas', 'std'),
                contagem=('tempo_horas', 'count'),
                maximo_horas=('tempo_horas', 'max')
            ).reset_index()
            
            acima_24h = df_tempo_filtrado[df_tempo_filtrado['tempo_horas'] > 24].groupby(class_col).size()
            df_class['acima_24h'] = df_class[class_col].map(acima_24h).fillna(0).astype(int)
            df_class['perc_acima_24h'] = (df_class['acima_24h'] / df_class['contagem'] * 100).round(1)
            df_class['perc_acima_24h'] = df_class['perc_acima_24h'].fillna(0)
        else:
            df_class = pd.DataFrame(columns=['classificacao', 'media_horas', 'mediana_horas', 'desvio_horas', 'contagem', 'maximo_horas', 'acima_24h', 'perc_acima_24h'])
        
        min_registros = st.number_input(
            "Mínimo de registros por classificação para exibição",
            min_value=1,
            max_value=100,
            value=5,
            step=1,
            key="min_reg_class"
        )
        df_class_filtrada = df_class[df_class['contagem'] >= min_registros].copy()
        
        if df_class_filtrada.empty:
            st.info(f"Nenhuma classificação com pelo menos {min_registros} registros.")
        else:
            df_class_filtrada = df_class_filtrada.sort_values('media_horas', ascending=False)
            
            tabela = df_class_filtrada.copy()
            tabela['media_horas'] = tabela['media_horas'].map(lambda x: f"{x:.2f}")
            tabela['mediana_horas'] = tabela['mediana_horas'].map(lambda x: f"{x:.2f}")
            tabela['desvio_horas'] = tabela['desvio_horas'].map(lambda x: f"{x:.2f}" if pd.notna(x) else "-")
            tabela['maximo_horas'] = tabela['maximo_horas'].map(lambda x: f"{x:.2f}")
            tabela['perc_acima_24h'] = tabela['perc_acima_24h'].map(lambda x: f"{x:.1f}%")
            
            rename_map = {
                'media_horas': 'Média (h)',
                'mediana_horas': 'Mediana (h)',
                'desvio_horas': 'Desvio (h)',
                'contagem': 'Nº Chamadas',
                'maximo_horas': 'Máximo (h)',
                'acima_24h': '> 24h',
                'perc_acima_24h': '% > 24h'
            }
            if class_col:
                rename_map[class_col] = 'Classificação'
            tabela = tabela.rename(columns=rename_map)
            st.dataframe(tabela, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("Dashboard desenvolvido com Streamlit | Dados do COBOM-BH")
