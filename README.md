# 🚒 Dashboard Interativo — COBOM-BH

Dashboard em **Streamlit** para análise operacional das chamadas do **Corpo de Bombeiros Militar de Minas Gerais (CBMMG)** recebidas no **COBOM-BH**.

A aplicação importa arquivos **CSV** e **Excel** exportados do sistema **CAD**, padroniza e enriquece os dados, aplica filtros em cascata e apresenta indicadores operacionais, séries temporais, projeções, mapas e análises de tempo de atendimento em **sete abas analíticas**.

---

## 📋 Sumário

- [Visão geral](#-visão-geral)
- [Funcionalidades principais](#-funcionalidades-principais)
- [Abas analíticas](#-abas-analíticas)
- [Estrutura do projeto](#-estrutura-do-projeto)
- [Modelo de dados](#-modelo-de-dados)
- [Regras de negócio](#-regras-de-negócio)
- [Requisitos](#-requisitos)
- [Como executar localmente](#-como-executar-localmente)
- [Como obter os dados no CAD](#-como-obter-os-dados-no-cad)
- [Deploy](#-deploy)
- [Licença](#-licença)

---

## 🔎 Visão geral

O painel foi desenvolvido para:

- processar arquivos de ocorrências em **CSV** e **XLSX/XLSM** exportados pelo CAD
- padronizar colunas, datas, horas, coordenadas e municípios mesmo com **cabeçalhos corrompidos** (mojibake) ou com **ordem fixa** de colunas
- combinar **múltiplos arquivos** em um único conjunto de dados
- filtrar por período, tipo de arquivo, município, natureza, classificação, unidade e recursos empenhados
- apresentar métricas operacionais, rankings, tendências temporais e **projeção sazonal**
- visualizar ocorrências em **mapa interativo** com três modos de camada
- analisar **tempo de atendimento** e **SLA de chamadas em andamento**
- destacar **flags operacionais** (Alerta, Destaque, Envolve autoridade), **origem do REDS** e **grupos temáticos de natureza**

---

## ⚙️ Funcionalidades principais

### Upload e carregamento de dados

- aceita arquivos `.csv`, `.xlsx`, `.xlsm` e `.xslx`
- suporta **múltiplos arquivos em paralelo**
- detecta automaticamente o tipo de arquivo (`classificadas`, `ativas` ou `generico`)
- detecta Excel pelo **magic number** (`PK\x03\x04`), não apenas pela extensão
- aplica fallback posicional quando o cabeçalho é ilegível, usando o esquema fixo de colunas do CAD
- cacheia uploads por **hash SHA-256** dos bytes do arquivo, evitando reprocessamento
- reverte **mojibake** (`ş→º`, `ă→ã`, `Ţ→Ç`, `Ę→Ê`, …) antes do mapeamento de colunas

### Dados de demonstração

- botão **"Carregar Dados de Demonstração"** gera ~1.800 chamadas sintéticas estruturalmente idênticas ao CAD
- cobre 365 dias, 7 municípios da RMBH, 9 naturezas, 8 unidades operacionais e pool de 9 viaturas
- permite explorar todo o dashboard sem nenhum arquivo real

### Filtros interativos

A barra lateral oferece:

- **Tipo de arquivo** (Classificadas / Ativas / Genérico) — multiselect
- **Período** — data inicial e data final
- **Seleção de arquivo** — individual ou "Todos"
- **Filtros em cascata**: Município → Natureza → Classificação → Unidade → Recursos Empenhados
- **Download dos dados filtrados** em CSV (UTF-8 com BOM)

### Cards de métricas globais

- Total de Chamadas
- Média Diária
- Municípios Atendidos
- Unidade Mais Acionada (BBM/CIA IND)
- Natureza Mais Comum
- Classificação Mais Frequente

---

## 📊 Abas analíticas

### 1. 📊 Rankings de Dados
- Top 15 naturezas de ocorrência
- Top 15 logradouros / vias
- Top 15 municípios
- Top 15 Batalhões / Companhias Independentes
- Top 15 frações e unidades operacionais
- Top 15 viaturas mais empenhadas
- Top 10 classificações de chamadas
- Top 10 situações operacionais distintas de **Classificada** (chamadas ativas)
- **Concentração de recursos por chamada** (gráfico de Pareto: barras + linha de concentração acumulada)

### 2. 📈 Evolução e Projeção Temporal
- Comparação mensal multi-ano (linhas por ano)
- **Projeção sazonal** para os próximos meses, combinando:
  - tendência linear (`LinearRegression`)
  - fator multiplicativo de sazonalidade mensal
  - banda de desvio-padrão histórico
- Volume diário de chamadas

### 3. 📊 Distribuição e Comparação
- 🔥 **Matriz de Calor Operacional** (7 dias × 24 horas) para planejamento de plantão
- Distribuição de chamadas por hora do dia
- Distribuição por dia da semana
- Distribuição por classificação (pizza)
- Chamadas por Batalhão / Companhia Independente
- Detalhamento por frações e unidades operacionais

### 4. 🗺️ Mapa de Ocorrências
Três modos de visualização em Folium:

| Modo | Descrição |
|---|---|
| 📍 **Cluster** | Marcadores agrupados com popup (município, natureza, local) |
| 🔥 **Heatmap** | Mancha de calor por densidade espacial (KDE) |
| ⭕ **Grouped** | Círculos por município com raio proporcional ao volume |

Slider de amostragem (100 a 20.000 pontos) para performance.

### 5. ⏱️ Tempo de Atendimento
- Filtro por modo: **Classificadas** (tempo real) / **Ativas** (tempo decorrido) / **Todas**
- Métricas: média, mediana, máximo, total, % acima de 24 h
- Histograma de duração com destaque para faixa > 24 h
- Histograma específico para atendimentos com duração > 24 h (em dias)
- Tabela resumo por classificação/situação:
  - contagem, média, mediana, desvio, máximo
  - quantidade e percentual acima de 24 h
- **Boxplot de tempo por situação operacional** (SLA por estado)

### 6. 🚨 Operacional — Chamadas em Andamento
- Total de chamadas ativas
- Tempo médio decorrido
- Natureza dominante
- Municípios ativos
- Distribuição por situação operacional (rosca)
- **SLA de chamadas em aberto** em faixas: `<1h`, `1–3h`, `3–6h`, `6–12h`, `12–24h`, `>24h`
- Tabela ordenada por tempo decorrido (mais antigas primeiro)

### 7. 🏷️ Flags, Agências e Natureza
- **Flags operacionais** (Alerta, Destaque, Envolve Autoridade): comparativo Sim/Não
- **Evolução temporal das flags** (resample mensal ou diário conforme período)
- Top 10 municípios com **Alerta**
- **Origem do REDS**: Somente PM / Somente BM / PM + BM (multiagência) / Sem REDS
- Indicador de **multiagência** (PM + BM)
- Grupos temáticos com mais chamadas multiagência
- **Natureza por grupo temático** (APH, Incêndios, Salvamentos, Preventivas, etc.)
- **Distribuição por prioridade** (1-Alta, 2-Média, 3-Baixa)
- **Pivot Natureza × Prioridade** (contagem de chamadas)

---

## 🗂️ Estrutura do projeto

```
.
├── app.py                  # Aplicação principal e interface Streamlit (7 abas)
├── data_loader.py          # Leitura, cache de filtros e pipeline de enriquecimento
├── visualizations.py       # Gráficos Plotly e mapas Folium
├── streamlit_app.py        # Entrypoint retrocompatível
├── requirements.txt        # Dependências do projeto
├── pyproject.toml          # Configuração do projeto (uv)
├── run.sh                  # Script de execução local
├── README.md               # Este arquivo
├── LICENSE                 # Licença do repositório
├── .streamlit/             # Configuração do Streamlit
└── utils/
    ├── __init__.py
    ├── helpers.py          # Funções puras de normalização e parsing
    └── demo_data.py        # Gerador de dados sintéticos do COBOM
```

### Responsabilidades dos módulos

| Módulo | Responsabilidade |
|---|---|
| `app.py` | Orquestração da UI, filtros, session_state, cache por hash de arquivo, abas |
| `data_loader.py` | I/O de CSV/XLSX, normalização de schema, enriquecimento, filtros cacheados |
| `visualizations.py` | Todas as figuras Plotly e mapas Folium, com `_apply_theme_layout` |
| `utils/helpers.py` | Funções **puras** (sem Streamlit): mojibake, parsers, extrações, detecção de tipo |
| `utils/demo_data.py` | `generate_demo_cobom_data(n)` — gerador sintético reprodutível |

---

## 🧱 Modelo de dados

### Campos de entrada mapeados (`COLUMN_MAPPING`)

| Rótulo CAD | Nome canônico |
|---|---|
| `Nº chamada` | `chamada_numero` |
| `Nº REDS` | `reds` |
| `Data/hora de criação` | `data_hora_criacao` |
| `Local do fato` | `Chamada_atendimentos.local_do_fato` |
| `Latitude do local` | `Chamada_atendimentos.local_latitude` |
| `Longitude do local` | `Chamada_atendimentos.local_longitude` |
| `Natureza` | `Chamada_atendimentos.natureza_descricao` |
| `Unidade Responsável` | `Chamada_atendimentos.unidade_servico_nome` |
| `Recursos empenhados` | `Empenhos.recurso_codigo_prefixo` |
| `Alerta` | `alerta` |
| `Destaque` | `destaque` |
| `Envolve autoridade` | `envolve_autoridade` |
| `Tipo de classificação` | `Chamada_atendimentos.chamada_classificacao_descricao` |
| `Situação` | `situacao` |
| `Data/hora da situação atual` | `data_hora_situacao_atual` |
| `Evento associado` | `evento_associado` |

### Campos derivados (criados por `process_dataframe`)

| Campo | Descrição |
|---|---|
| `chamada_data_inclusao` | Data (sem hora) da criação |
| `chamada_hora_inclusao` | Hora como `timedelta` |
| `data_hora` | Timestamp completo |
| `ano`, `mes`, `mes_ano` | Agrupamentos temporais |
| `hora` | Hora do dia (0–23) |
| `dia_semana` | 0 = Segunda … 6 = Domingo |
| `Chamada_atendimentos.local_municipio_nome` | Município extraído de `local_do_fato` |
| `data_hora_fim` | Fim efetivo (situação terminal) ou `now()` (ativa) |
| `situacao_norm` | Situação normalizada (string) |
| `situacao_terminal` | `True` apenas se situação == `Classificada` |
| `tempo_no_estado_horas` | Horas decorridas no estado atual |
| `natureza_codigo`, `natureza_grupo_letra`, `natureza_grupo` | Extração por regex `^([A-Z]\d{5})` |
| `natureza_prioridade` | Extração de `Prioridade:\s*(\d)` |
| `alerta_flag`, `destaque_flag`, `envolve_autoridade_flag` | Booleanos |
| `reds_qtd`, `reds_pm`, `reds_bm`, `reds_multiagencia`, `reds_origem` | Decomposição do REDS |
| `tempo_minutos`, `tempo_horas` | Duração calculada em `app.py` |
| `tipo_arquivo`, `arquivo` | Origem do registro |

### Grupos temáticos de natureza

| Código | Grupo |
|---|---|
| `V` | 🚑 APH / Vítimas |
| `O` | 🔥 Incêndios / Queimadas |
| `S` | 🆘 Salvamentos |
| `W` | 🛡️ Apoio / Preventivas |
| `P` | ⚠️ Perigos / Vistorias |
| `X` | 📋 Empenho Administrativo |
| `Y` | 🚁 Aéreas / Apoio a Órgãos |
| `Q` | 🎓 Treinamento / Palestras |
| `R` | 🤝 Ações Comunitárias / Risco |
| `A` | 💔 Autoextermínio |
| `B` | 🏗️ Brigada / Apoio Especial |

---

## 📐 Regras de negócio

### Situação terminal

**Apenas `Classificada` encerra o ciclo operacional.** Todos os demais valores (`Terminada`, `Atribuída ao órgão`, `Em controle`, `Em direção`, `À caminho`, `No local`, `Despachada`, `Em retorno`, `Suspensa`, `Nada constatado`, `Teste`, `RAT`, `Duplicada`, `Dispensada pelo solicitante`, `Solicitante não encontrado`, `Não atendida: falta de viatura/efetivo`, `Atendida pelo SAMU`, `Repassada a outros órgãos`, `Orientação`, `Orientação da regulação médica`, etc.) mantêm a chamada **ATIVA** no sistema.

Consequências:

- o tempo decorrido de chamadas ativas é medido em relação a **agora** (`now()`)
- a **Tab 6 (Operacional)** é dedicada exclusivamente a essas chamadas
- a **Tab 5** permite alternar entre `Classificadas`, `Ativas` e `Todas`

### Detecção de tipo de arquivo

1. Nome contém `ativ` → `ativas`; contém `classific` → `classificadas`
2. Caso contrário, inspeciona `situacao`:
   - único valor `classificada` → `classificadas`
   - múltiplos valores → `ativas`
3. Fallback → `generico`

### Compatibilidade de encoding

Exports do CAD gerados em CP1252 e lidos como UTF-8 (ou vice-versa) produzem mojibake em acentos e no símbolo `º`. A função `fix_mojibake` reverte:

```
ş → º      ă → ã      Ă → Ã      Ŕ → À      Ę → Ê
ę → ê      Ţ → Ç      ţ → ç      ł → õ
```

### Coordenadas

- aceita decimal com vírgula ou ponto
- detecta e corrige valores não formatados (ex.: `19916700` → `-19.9167`) dividindo por potências de 10
- valida faixa (`|lat| ≤ 90`, `|lon| ≤ 180`)

---

## 🧰 Requisitos

- **Python 3.11+** (recomendado 3.12/3.13)
- `uv` (recomendado) ou `pip` + ambiente virtual

Dependências principais (`requirements.txt`):

- `streamlit`
- `streamlit-folium`
- `pandas`
- `numpy`
- `plotly`
- `folium`
- `scikit-learn`
- `openpyxl`
- `chardet`

---

## 🚀 Como executar localmente

### Opção 1 — com `uv` (recomendado)

```bash
uv sync
uv run streamlit run app.py
```

### Opção 2 — com ambiente virtual

```bash
python -m venv .venv
source .venv/bin/activate     # Linux/macOS
# .venv\Scripts\activate      # Windows
pip install -r requirements.txt
streamlit run app.py
```

### Opção 3 — com o script auxiliar

```bash
bash run.sh
```

A aplicação abre por padrão em `http://localhost:8501`.

---

## 🧭 Como obter os dados no CAD

O painel foi pensado para consumir exports gerados diretamente pelo sistema CAD do CBMMG. O passo a passo é:

1. **Acesso ao Módulo de Chamadas**
   Entre no **Sistema CAD**, acesse o menu **"Chamadas"** e selecione a opção **"Pesquisa de chamadas"**.

2. **Definição de Critérios de Pesquisa**
   Defina os critérios selecionando **"Data/Hora de criação"**, **"Filtro de chamada"** e **"Pesquisar por"**.

3. **Execução da Pesquisa**
   Clique em **"Pesquisar"** para confirmar se existem chamadas para os critérios definidos.

4. **Exportação dos Dados**
   Clique em **"Exportar CSV"** para gerar o arquivo com os dados das chamadas.

5. **Upload no Portal**
   Salve o CSV em uma pasta de fácil acesso e faça o **upload na barra lateral** do dashboard.

> 💡 Você pode carregar **mais de um arquivo** simultaneamente. O painel unificará todos os registros e permitirá filtrar por tipo (classificadas, ativas ou ambos).

---

## ☁️ Deploy

O projeto pode ser publicado no **Streamlit Community Cloud** com a configuração padrão:

- repositório GitHub conectado
- branch principal
- arquivo principal: `app.py`

Nenhuma variável de ambiente ou segredo é necessário.

---

## 🧠 Notas técnicas

- **Cache em duas camadas**: `@st.cache_data` no loader e nos filtros + cache manual por **SHA-256** em `st.session_state` para detectar arquivos alterados.
- **Filtros hashable**: `_filters_key` converte o dicionário de filtros em tupla ordenada, permitindo cache.
- **Fallback em cascata** para schemas: nome → mojibake revertido → posição fixa (`CSV_COLUMNS` / `XLSX_COLUMNS`).
- **Separação estrita de camadas**: `helpers.py` é puro (sem Streamlit); `data_loader.py` faz I/O e cache; `visualizations.py` só Plotly/Folium; `app.py` só orquestra UI.
- **Tema claro/escuro**: todas as figuras usam `paper_bgcolor="rgba(0,0,0,0)"` via `_apply_theme_layout`.
- **Leitura Excel em modo `read_only`** com `openpyxl`, buscando primeiro a aba `bd_cobom` e depois a aba com mais dados.

---

## 📄 Licença

Este projeto está sob a licença do repositório, conforme arquivo `LICENSE`.

---

<p align="center">
  Dashboard desenvolvido com <b>Streamlit</b> · Corpo de Bombeiros Militar de Minas Gerais · <b>COBOM-BH</b>
</p>
