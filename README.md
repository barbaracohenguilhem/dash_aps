# Radar de vagas

**Um dashboard Python/Dash e um dashboard Excel interativo, sobre a mesma base histórica.**

Design editorial em tons de papel, filtros conectados e investigação dos anúncios. Os rótulos vêm da base original: o projeto **não classifica vagas atuais** e associações não comprovam fraude.

## O que abrir

- **Web:** [dash-aps.vercel.app](https://dash-aps.vercel.app) — versão publicada; mudanças de PR aparecem primeiro em preview.
- **Excel:** [Jobs_Database.xlsx](Jobs_Database.xlsx) → **Download raw file** → abra no Microsoft Excel com cálculo automático.
- **Dados somente:** [Jobs_Data.xlsx](Jobs_Data.xlsx), uma única aba sem fórmulas ou gráficos.
- **Python:** [app.py](app.py) e [Analise.ipynb](Analise.ipynb), caderno executado com cálculos explicados e limitações.

## Estrutura enxuta

```text
app.py                    # Dashboard e endpoints de consulta/exportação
assets/                   # Estilo, ilustração, fonte local e JavaScript
Jobs_Database.xlsx        # Dashboard Excel + anúncios completos, sem macros
Jobs_Data.xlsx            # Excel somente dados, com todas as colunas
Analise.ipynb              # Caderno Python reproduzível e comentado
data/jobs_database.db     # Mesma base em SQLite, leitura rápida no servidor
scripts/build_workbook.py # Reconstrói o Excel a partir dessa base
tests/                    # Regressão de dados, Excel e acessibilidade
requirements.txt          # Dependências da aplicação
requirements-dev.txt      # Ferramentas de testes e geração do Excel
vercel.json               # Publicação da aplicação
```

A base SQLite é mantida para o site não carregar uma planilha de 10 MB a cada execução. Os 10.000 registros e seus IDs foram preservados. CSVs duplicados, partes do dataset, notebooks de modelagem e configurações de editor foram retirados desta versão; continuam disponíveis no histórico Git. Não há modelos de machine learning no aplicativo.

## Executar o dashboard

Python **3.12 ou 3.13**:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abra `http://localhost:8050`. Não exige API key nem serviço externo.

### Na web

1. Comece pela composição da base: o mosaico usa blocos de 1% e um bloco parcial para preservar a fração exata. É sempre a **base completa**, não o recorte.
2. Escolha uma pergunta pronta ou combine os filtros principais e avançados. Perguntas prontas **substituem** o recorte anterior.
3. Siga o percurso de combinações (Sankey), a distribuição acumulada dos comprimentos dos textos e o caderno de dois registros. Os exemplos usam o menor ID por rótulo disponível, não uma seleção representativa. As tabelas e os resumos textuais dão os números fora dos gráficos.
4. Abra o **atlas analítico** opcional para quatro perspectivas: setor, logo × remoto, contrato e país. Clicar em um setor ou país aplica esse filtro ao recorte; os filtros tradicionais oferecem a alternativa por teclado.
5. Ordene e filtre a tabela; selecione um anúncio para ler os textos completos. Filtros da tabela afetam **apenas a tabela**.
6. **Exportar CSV** leva o recorte dos filtros principais/avançados, com textos completos. O download é montado no navegador em partes; mantenha a página aberta.
7. **Excel** leva à planilha completa da revisão publicada — não é exportação do recorte web. Os gráficos permitem salvar PNG pelas ferramentas do Plotly.

O gráfico de setores tem ordenação e amostra mínima próprias; esses controles não mudam o recorte ou o CSV. Taxas usam o recorte como denominador. Ao filtrar Status, não interprete a taxa resultante como previsão de risco.

## Usar o Excel interativo

Arquivo `.xlsx` com fórmulas e gráficos nativos, **sem macros, sem conexões externas e sem segmentações de Tabela Dinâmica**.

| Aba | Como funciona |
| --- | --- |
| **Dashboard** | Seis listas em **B6, F6, J6, B9, F9, J9**: País, Setor, Contrato, Status, Logo e Remoto. Condições combinadas atualizam três indicadores e quatro gráficos. `Todos` remove cada filtro. |
| **Base_Interativa_Vagas** | Todos os anúncios e textos em tabela com AutoFiltro. Subtotais no topo acompanham as linhas visíveis. |
| **Analises** | Contagens, rótulos de fraude e taxas de todas as categorias, respondendo às listas do Dashboard. |
| **Leia-me** | Instruções, denominadores e limitações dentro do arquivo. |

**Importante:** os filtros nativos da tabela e as seis listas do Dashboard são independentes. Gráficos de setor e país mostram o recorte **nas dez maiores categorias da base completa** (categorias fixas para comparação); não são um ranking dinâmico do recorte. Todas as categorias continuam na aba Analises. Sem anúncios, a taxa mostrada é 0%.

Use Microsoft Excel com cálculo automático. Visualizadores podem mostrar apenas os valores salvos. Os valores iniciais foram calculados a partir dos dados reais. Não se alega equivalência em Google Sheets/LibreOffice nem teste manual no Microsoft Excel neste ambiente.

### Reconstruir a planilha

```bash
pip install -r requirements-dev.txt
python scripts/build_workbook.py
# ou, sem sobrescrever o arquivo principal:
python scripts/build_workbook.py --output /tmp/Radar_de_Vagas.xlsx --data-output /tmp/Dados.xlsx
```

`data/jobs_database.db` é a fonte canônica desta versão; a aplicação só a abre para leitura. Após uma atualização controlada da base, reconstrua o Excel, rode os testes e publique os dois juntos. Alterar a cópia baixada no Excel não altera o site.

## Verificar

```bash
pip install -r requirements-dev.txt
python -m pytest -q
flake8 app.py scripts tests --select=E9,F63,F7,F82
```

Regressão de navegador local, em outro terminal com `python app.py` rodando:

```bash
cd tests/browser
npm ci
npx playwright install chromium
npm test
```

As dependências de navegador e geração da planilha são isoladas das dependências de produção. Os testes foram executados localmente em Python 3.12 e 3.13. **Atenção:** os workflows GitHub Actions antigos permanecem nesta PR, pois a integração não pode alterar arquivos de workflow. Uma correção de CI é entregue como patch separado para aplicação manual; até lá, as verificações antigas podem continuar falhando.

## Publicação

O repositório já está conectado ao projeto Vercel **dash-aps**. O `vercel.json` inclui SQLite e assets; a planilha fica no GitHub, fora da função serverless. O link no site usa `VERCEL_GIT_COMMIT_SHA` para apontar ao arquivo da mesma revisão (localmente, usa `main`). Não é necessário copiar arquivos de ambiente nem adicionar segredos.

Mudanças ficam em pull request para revisão; nenhum merge ou promoção de produção faz parte da preparação.

## Design e metodologia

A organização narrativa foi informada pelos princípios de [Searching for Birds, Visual Cinnamon](https://www.visualcinnamon.com/portfolio/searching-for-birds/): forma visual ligada aos dados, progressão de perguntas e exploração com contexto. Não foram copiados código, imagens ou composição. O mosaico de anúncios, as comparações e o caderno de registros são específicos desta base.

O Sankey mostra duas transições agregadas da mesma população; não se somam etapas nem se rastreiam indivíduos através da etapa intermediária. A ECDF usa todos os comprimentos observados, sem amostragem; cada rótulo tem seu próprio denominador. Não há causalidade, classificação automática ou avaliação de anúncios atuais.

O caderno Python foi preparado com assistência de IA e identifica isso explicitamente. Não representa um diário retroativo de seis meses de trabalho; revise a metodologia e siga as regras de atribuição da instituição.
