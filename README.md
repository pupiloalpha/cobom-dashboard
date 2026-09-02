# 🚒 Dashboard Interativo - COBOM-BH

Dashboard em Streamlit para análise de chamadas do Corpo de Bombeiros Militar de Minas Gerais (CBMMG) recebidas no COBOM-BH.

A aplicação permite importar arquivos em CSV ou Excel, padronizar os dados, aplicar filtros e visualizar indicadores operacionais em diferentes abas analíticas.

## Visão geral

O painel foi desenvolvido para:

- processar arquivos de ocorrências em CSV e XLSX
- padronizar colunas e campos de data, hora, lokasi e município
- combinar múltiplos arquivos em um único conjunto de dados
- filtrar por período, município, natureza, classificação e unidade
- apresentar métricas operacionais e tendências temporais
- visualizar ocorrências em mapa geográfico
- analisar tempo de atendimento

## Funcionalidades principais

### Upload e carregamento de dados

- aceita arquivos `.csv` e `.xlsx`
- suporta múltiplos arquivos em paralelo
- detecta automaticamente formatos antigos e novos de CSV
- ajusta colunas, datas, horas, coordenadas e município

### Filtros interativos

A barra lateral oferece:

- seleção de arquivo ou todos os arquivos
- filtro por período
- filtragem por município
- filtragem por natureza da ocorrência
- filtragem por classificação da chamada
- filtragem por unidade

### Cards de métricas

O dashboard apresenta indicadores como:

- total de chamadas
- média diária
- municípios atendidos
- unidade mais acionada
- natureza mais comum
- classificação mais frequente

### Abas de análise

#### 1. Rankings de Dados
- Top 15 naturezas
- Top 15 logradouros
- Top 15 municípios
- Top 15 unidades
- Top 15 viaturas mais empenhadas
- Top 10 classificações

#### 2. Evolução e Projeção Temporal
- comparação mensal por ano
- projeção de chamadas para os próximos meses
- tendência por dia

#### 3. Distribuição e Comparação
- chamadas por hora do dia
- chamadas por dia da semana
- distribuição por classificação
- chamadas por BBM / CIA IND

#### 4. Mapa de Ocorrências
- exibe ocorrências com coordenadas válidas em mapa interativo
- agrupa marcadores por cluster
- mostra município, natureza e local em popup

#### 5. Tempo de Atendimento
- média, mediana e máximo de tempo de atendimento
- histograma de duração
- análise de ocorrências acima de 24 horas
- estatísticas descritivas

## Estrutura do projeto

- `app.py`: aplicação principal e interface Streamlit
- `data_loader.py`: leitura, cache de filtros e processamento inicial
- `visualizations.py`: gráficos Plotly e mapa Folium
- `utils/helpers.py`: funções puras de normalização e parsing
- `streamlit_app.py`: entrada retrocompatível
- `requirements.txt`: dependências do projeto
- `pyproject.toml`: configuração do projeto e dependências
- `run.sh`: script para execução local
- `.streamlit/`: configuração do Streamlit

## Requisitos

- Python 3.11+ (recomendado 3.12/3.13, conforme ambiente)
- `uv` ou ambiente virtual Python
- dependências listadas em `requirements.txt`

## Como executar localmente

### Opção 1: com `uv`

```bash
uv sync
uv run streamlit run app.py
```

### Opção 2: com ambiente virtual

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Observações sobre os dados

A aplicação foi pensada para trabalhar com arquivos de ocorrência exportados pelo COBOM-BH, incluindo campos como:

- `chamada_numero`
- `Chamada_atendimentos.local_do_fato`
- `Chamada_atendimentos.local_latitude`
- `Chamada_atendimentos.local_longitude`
- `Chamada_atendimentos.natureza_descricao`
- `Chamada_atendimentos.unidade_servico_nome`
- `Chamada_atendimentos.chamada_classificacao_descricao`
- `chamada_data_inclusao`
- `chamada_hora_inclusao`

A lógica de importação tenta suportar diferentes formatos de CSV e arquivos Excel, normalizando os dados antes da análise.

## Deploy

O projeto pode ser publicado no Streamlit Community Cloud com a configuração padrão:

- repositório GitHub
- branch principal
- arquivo principal: `app.py`

## Licença

Este projeto está sob a licença do repositório, conforme arquivo `LICENSE`.
