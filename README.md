# Job Postings Fraud Analytics — Database & Dashboard

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/barbaracohenguilhem/DataSet_limpo_em_partes)

Projeto de tratamento de dados, estruturação de **Database Interativa (Excel & SQLite)** e **Dashboard Analítico em Python Dash** para detecção e análise exploratória de anúncios de vagas de emprego reais vs. fraudulentos.

---

## Links do Projeto

- **Aplicação Web (Vercel):** `https://dataset-limpo-em-partes.vercel.app` *(ou clique no botão **Deploy with Vercel** acima para publicar/atualizar)*
- **Código da Aplicação Dash:** [`app.py`](./app.py)
- **Database Interativa em Excel:** [`Jobs_Database.xlsx`](./Jobs_Database.xlsx)
- **Banco de Dados SQLite:** [`data/jobs_database.db`](./data/jobs_database.db)
- **Dataset Consolidado Limpo (CSV):** [`data/jobs_cleaned.csv`](./data/jobs_cleaned.csv)

---

## Estrutura do Repositório

```text
├── app.py                          # Aplicação Web Python Dash (WSGI compatível com Vercel)
├── vercel.json                     # Configuração serverless (@vercel/python)
├── requirements.txt                # Dependências de produção (dash, pandas, plotly)
├── Jobs_Database.xlsx              # Planilha Database com AutoFiltro, SUBTOTAL dinâmico e gráficos
├── data/
│   ├── jobs_database.db            # Banco SQLite indexado (10.000 vagas higienizadas)
│   ├── jobs_cleaned.csv            # Base consolidada limpa em CSV
│   └── parts/                      # Partes individuais do dataset (dataset_part_01..09.csv)
├── scripts/
│   ├── clean_dataset.py            # Pipeline de limpeza de HTML/CSS, encoding e hashes
│   └── build_database.py           # Gerador do banco SQLite e da planilha Excel interativa
└── notebooks/
    ├── eda_and_modelling.ipynb
    ├── fake_job_prediction.ipynb
    ├── realtime_ml_application.ipynb
    └── text_classification_keras_nb.ipynb
```

---

## Principais Funcionalidades

### 1. Dashboard Python Dash ([`app.py`](./app.py))

- **10 Filtros Interativos Combinados:** Status (`Todas` / `Reais` / `Fraudulentas`), Busca livre por palavra-chave, Logo da Empresa, Trabalho Remoto, País, Setor/Indústria, Tipo de Contrato, Nível de Experiência, Escolaridade e Faixa de Tamanho da Descrição.
- **5 Indicadores (KPIs) em Tempo Real + 4 Gráficos Plotly Interativos.**
- **Tabela da Database Pesquisável:** ordenação e filtro por coluna, destaque visual para vagas fraudulentas e **Inspetor de Registro** (clique em qualquer vaga para visualizar a descrição, requisitos e benefícios completos já limpos).
- **Exportação Instantânea:** download do recorte filtrado em `.csv`.

### 2. Database em Excel ([`Jobs_Database.xlsx`](./Jobs_Database.xlsx))

- **Aba `Base_Interativa_Vagas`:** formatada como Tabela Oficial com AutoFiltro e barra superior dinâmica (`SUBTOTAL`) que recalcula vagas visíveis, total de fraudes e taxa de fraude ao filtrar qualquer coluna.
- **Aba `Resumo_Dashboard`:** consolidação executiva por setor e tipo de contrato com gráficos nativos do Excel.

### 3. Pipeline de Limpeza ([`scripts/clean_dataset.py`](./scripts/clean_dataset.py))

- Remoção de resíduos de HTML/CSS quebrados (`mso-...`) e vazamentos de buffer do dataset original;
- Correção de caracteres mal codificados (`Windows-1252` / BOM UTF-8);
- Padronização dos hashes de anonimização (`#URL_...#`, `#EMAIL_...#`, `#PHONE_...#`) para marcadores limpos (`[URL]`, `[EMAIL]`, `[TELEFONE]`).

---

## Como Executar Localmente

```bash
pip install -r requirements.txt
python app.py
```

Acesse em `http://localhost:8050`.

## Como Publicar na Vercel

1. Faça push deste repositório para o GitHub:

   ```bash
   git add -A
   git commit -m "chore: organize project structure and configure Vercel deployment"
   git push origin main
   ```

2. Acesse [vercel.com/new](https://vercel.com/new), importe o repositório `barbaracohenguilhem/DataSet_limpo_em_partes` e clique em **Deploy** (o [`vercel.json`](./vercel.json) já configura automaticamente o Python Dash + SQLite).
