# Radar de vagas — Database & Dashboard

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
- **Percurso conectado:** índice fixo com etapa atual, ligações entre perspectivas e atalhos de volta. Navegar preserva o recorte. No panorama, os filtros ativos podem ser removidos individualmente ou limpos em conjunto; os botões de colunas ajudam a percorrer a tabela horizontalmente.
- **Leitura rápida:** resumo do recorte com taxa de fraude, diferença em pontos percentuais em relação à base completa, concentração por país e cobertura dos dez maiores países. Com status filtrado, a comparação dá lugar a um aviso de interpretação.
- **Quatro formas de visualizar:** pontos por setor (tamanho = volume, linha = taxa do recorte), mapa de calor de logo × remoto (escala fixa de 0–100%, com amostras e lacunas sem dados), rosca com composição dos contratos e barras empilhadas por país.
- **Comparação de setores:** escolha entre maior volume e maior taxa; exija pelo menos 1, 30, 100 ou 500 anúncios por setor. Esses controles alteram apenas a comparação de setores, não o recorte nem o CSV. Até dez setores elegíveis são mostrados; uma amostra mínima não elimina a incerteza estatística.
- **Investigação interativa:** clique em um ponto de setor ou barra de país para aplicar esse filtro ao dashboard e ao CSV. Os filtros tradicionais oferecem o mesmo caminho por teclado. Limpar filtros também restaura a ordenação, amostra mínima e seleção dos gráficos. As ferramentas dos gráficos permitem salvar imagens PNG.
- **Interpretação das taxas:** o denominador é sempre o recorte atual; ao filtrar o status, as taxas refletem apenas os rótulos selecionados, não uma estimativa de risco.
- **Explorador de todos os registros:** ordene, filtre as colunas e selecione uma linha para ler descrição, requisitos, perfil da empresa e benefícios. Os filtros da tabela afetam apenas a tabela; os filtros acima dela afetam indicadores, gráficos e exportação.
- **Exportação:** baixe todas as vagas do recorte definido nos filtros principais e avançados em `.csv`, incluindo o texto completo. O arquivo é montado no navegador em partes para evitar o limite de resposta serverless; mantenha a página aberta até o download começar.
- **Interpretação:** os rótulos são históricos e vêm da base original. A ferramenta não classifica vagas atuais; correlação e ausência de logo não comprovam fraude.

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

Para verificar as consultas, indicadores e exportação:

```bash
python -m unittest discover -s tests
```

## Como Publicar na Vercel

1. Faça push deste repositório para o GitHub:

   ```bash
   git add -A
   git commit -m "chore: organize project structure and configure Vercel deployment"
   git push origin main
   ```

2. Acesse [vercel.com/new](https://vercel.com/new), importe o repositório `barbaracohenguilhem/DataSet_limpo_em_partes` e clique em **Deploy** (o [`vercel.json`](./vercel.json) já configura automaticamente o Python Dash + SQLite).
