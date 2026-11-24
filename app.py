#!/usr/bin/env python3
"""Explorador dos rótulos de fraude da base de anúncios de emprego."""

import os
import sqlite3
from contextlib import closing
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, ClientsideFunction, Dash, Input, Output, State, ctx, dash_table, dcc, html, no_update
from flask import Response, abort, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Immutable workbook link on deployments; main is the local-development fallback.
WORKBOOK_REF = os.environ.get("VERCEL_GIT_COMMIT_SHA") or "main"
WORKBOOK_URL = f"https://github.com/barbaracohenguilhem/dash_aps/blob/{quote(WORKBOOK_REF, safe='')}/Jobs_Database.xlsx?raw=true"
SOURCE_URL = f"https://github.com/barbaracohenguilhem/dash_aps/blob/{quote(WORKBOOK_REF, safe='')}"
DB_PATH = os.path.join(BASE_DIR, "data", "jobs_database.db")
DIMENSIONS = ["pais", "industry_clean", "employment_type_clean", "experience_clean", "education_clean"]
TABLE_COLS = [
    "id_vaga", "title", "status_vaga", "pais", "industry_clean",
    "employment_type_clean", "experience_clean", "salary_range",
    "tem_logo", "remoto", "tamanho_descricao",
]
DETAIL_COLS = ["location", "education_clean", "tem_perguntas", "company_profile", "description", "requirements", "benefits"]


def get_db_connection() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{quote(DB_PATH)}?mode=ro", uri=True)


def get_filter_options() -> dict:
    opts = {}
    with closing(get_db_connection()) as conn:
        for col in DIMENSIONS:
            rows = conn.execute(
                f"SELECT {col}, COUNT(*) FROM vagas GROUP BY {col} ORDER BY COUNT(*) DESC"
            ).fetchall()
            opts[col] = [{"label": f"{value} ({count:,})", "value": value} for value, count in rows if value]
        total, frauds, max_len = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(fraude_bin), 0), MAX(tamanho_descricao) FROM vagas"
        ).fetchone()
    opts.update(total=total, frauds=frauds, max_len=int(max_len or 0))
    return opts


def query_vagas(
    status: str, paises: list | None, setores: list | None, contratos: list | None,
    experiencias: list | None, escolaridades: list | None, tem_logo: str,
    remoto: str, busca: str | None, tam_range: list | None, include_details: bool = False,
    limit: int | None = None, offset: int = 0,
) -> pd.DataFrame:
    clauses = ["1=1"]
    params: list = []
    if status and status != "Todas":
        clauses.append("status_vaga = ?")
        params.append(status)
    for column, values in zip(DIMENSIONS, [paises, setores, contratos, experiencias, escolaridades]):
        if values:
            clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    for column, value in [("tem_logo", tem_logo), ("remoto", remoto)]:
        if value and value != "Todos":
            clauses.append(f"{column} = ?")
            params.append(value)
    if tam_range and len(tam_range) == 2:
        clauses.append("tamanho_descricao BETWEEN ? AND ?")
        params.extend([int(tam_range[0]), int(tam_range[1])])
    if busca and busca.strip():
        clauses.append("(title LIKE ? OR description LIKE ? OR requirements LIKE ? OR company_profile LIKE ? OR location LIKE ?)")
        params.extend([f"%{busca.strip()}%"] * 5)
    columns = TABLE_COLS + ["fraude_bin"]
    if include_details:
        columns += DETAIL_COLS
    sql = f"SELECT {', '.join(columns)} FROM vagas WHERE {' AND '.join(clauses)} ORDER BY id_vaga ASC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    with closing(get_db_connection()) as conn:
        return pd.read_sql_query(sql, conn, params=params)


OPTS = get_filter_options()
MAX_DESC_LEN = OPTS["max_len"]
BASE_RATE = 100 * OPTS["frauds"] / OPTS["total"] if OPTS["total"] else 0

dash_app = Dash(__name__, title="Radar de vagas | Análise de fraude", update_title="Atualizando análise…")
# Dash does not expose a document-language option; retain its standard template.
dash_app.index_string = dash_app.index_string.replace("<html>", '<html lang="pt-BR">', 1)
app = dash_app.server
server = app


def field(label, component, extra_class=""):
    return html.Div([html.Label(label, htmlFor=component.id), component], className=f"field {extra_class}")


def dropdown(id, options, placeholder, multi=True, value=None):
    return dcc.Dropdown(id=id, options=options, value=value, multi=multi, clearable=multi, placeholder=placeholder)


def story_links(label, links):
    return html.Nav([
        html.Span(label, className="bridge-label"),
        *[html.A(text, href=f"#{target}") for text, target in links],
    ], className="story-links", **{"aria-label": label})


CHART_CONNECTIONS = {
    "g-setores": ("O setor é uma pista. Que outras perguntas fazer?", [
        ("Cruzar logo e trabalho remoto →", "sinais"), ("Localizar nos países →", "paises"),
    ]),
    "g-logo-fraude": ("Uma associação não explica tudo. Amplie o olhar.", [
        ("Conhecer os contratos →", "contratos"), ("Ler os anúncios →", "explorador"),
    ]),
    "g-contrato-exp": ("Você viu o perfil. Onde estão esses anúncios?", [
        ("Explorar os países →", "paises"), ("Rever os setores →", "setores"),
    ]),
    "g-paises": ("Dos padrões aos registros: veja o que há por trás.", [
        ("Investigar os anúncios →", "explorador"), ("Comparar os setores →", "setores"),
    ]),
}
CHART_ANCHORS = {"g-setores": "setores", "g-logo-fraude": "sinais", "g-contrato-exp": "contratos", "g-paises": "paises"}


def graph_card(eyebrow, title, description, graph_id, wide=False, controls=None):
    return html.Section(
        [
            html.Div(eyebrow, className="eyebrow"),
            html.H3(title),
            html.P(description, className="card-description"),
            *([controls] if controls is not None else []),
            dcc.Graph(
                id=graph_id, config={"displayModeBar": "hover", "displaylogo": False, "responsive": True,
                                     "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "sendChartToCloud", "sendDataToCloud"],
                                     "toImageButtonOptions": {"filename": graph_id, "scale": 2}},
                style={"height": "390px" if graph_id in ("g-setores", "g-logo-fraude") else "330px"},
            ),
            html.Div(className="chart-context", children=[
                html.Div(id=f"recorte-{graph_id}", role="status", **{"aria-live": "polite"}),
                html.A("Ver ou editar o recorte ↑", href="#panorama"),
            ]),
            story_links(*CHART_CONNECTIONS[graph_id]),
        ],
        id=CHART_ANCHORS[graph_id], tabIndex=-1,
        className=f"panel chart-card{' chart-wide' if wide else ''}",
    )


def format_count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def population_mosaic():
    """100 equal-area tiles; fractional tile preserves the exact historical share."""
    share = 100 * OPTS["frauds"] / OPTS["total"] if OPTS["total"] else 0
    return html.Div([
        html.Div(className="population-tiles", **{"aria-hidden": "true"}, children=[
            html.Span(style={"--fraud-share": f"{max(0, min(1, share - i)) * 100}%"}) for i in range(100)
        ]),
        html.Div([html.Span("● Real", className="mosaic-real"), html.Span("● Fraudulenta", className="mosaic-fraud")], className="mosaic-legend"),
        html.P([html.Strong(f"{format_count(OPTS['frauds'])} de {format_count(OPTS['total'])}"),
                " anúncios receberam o rótulo de fraude. Cada bloco = 1% da base; o bloco parcial preserva a proporção exata."], className="mosaic-caption"),
    ], className="population-art", role="img", **{"aria-label": f"Base histórica: {OPTS['total']} anúncios, {OPTS['frauds']} rotulados como fraude, {share:.2f} por cento."})


def story_graph(id, height):
    return dcc.Graph(id=id, config={"displayModeBar": False, "displaylogo": False, "responsive": True,
                                    "modeBarButtonsToRemove": ["lasso2d", "select2d"]}, style={"height": f"{height}px"})


dash_app.layout = html.Div(className="app-shell", children=[
    html.Header(className="topbar", children=[
        html.Div(className="brand", children=[
            html.Div(className="brand-mark", **{"aria-hidden": "true"}),
            html.Div([html.Div("RADAR DE VAGAS", className="brand-name"), html.Div("Workspace de análise", className="brand-subtitle")]),
        ]),
        html.Nav(className="topbar-nav", **{"aria-label": "Navegação principal"}, children=[
            html.Span("ANÁLISE", className="nav-group-label"),
            html.A("Visão geral", href="#visao-geral"),
            html.A("Filtros e recorte", href="#recorte"),
            html.A("Gráficos e padrões", href="#percurso"),
            html.A("Explorador de vagas", href="#explorador"),
            html.Span("ARQUIVOS E FERRAMENTAS", className="nav-group-label"),
            html.A([html.Span("XLSX", className="nav-file"), "Excel · base de dados"], href="#excel-dados"),
            html.A([html.Span("DASH", className="nav-file"), "Dashboard no Excel"], href="#excel"),
            html.A([html.Span("PY", className="nav-file"), "Python + Excel"], href="#python-excel"),
        ]),
        html.Div(className="topbar-right", children=[
            html.Span("BASE HISTÓRICA", className="data-badge"),
            html.Span("Análise exploratória", className="topbar-note"),
        ]),
    ]),
    html.Main(id="visao-geral", tabIndex=-1, className="main-content", children=[
        html.Div(className="page-intro", children=[
            html.Div(className="intro-story", children=[
                html.Div("WORKSPACE / VISÃO GERAL", className="eyebrow"),
                html.H1(["Radar de vagas", html.Span(" / Dashboard")]),
                html.P("Explore a base histórica, cruze indicadores e leve a análise para Excel ou Python. Tudo parte dos mesmos dados.", className="intro-copy"),
                html.A(["Explorar os indicadores", html.Span(" ↓", **{"aria-hidden": "true"})], href="#recorte", className="explore-link"),
            ]),
            population_mosaic(),
            html.Div(className="intro-actions", children=[
                html.Div("PAINEL INTERATIVO · PYTHON / DASH", className="intro-caption"),
                html.Button("Limpar filtros", id="btn-reset", n_clicks=0, className="button button-secondary"),
                html.Button("↓  Exportar CSV", id="btn-download", n_clicks=0, className="button button-primary"),
                html.Div(id="export-status", className="export-status", role="status"),
            ]),
        ]),
        html.Div(id="kpi-row", className="kpi-grid", **{"aria-label": "Indicadores do recorte"}),
        html.Nav(className="workspace-tools", **{"aria-label": "Escolha como trabalhar com os dados"}, children=[
            html.A([html.Span("01 / XLSX", className="tool-tag"), html.Strong("Excel"), html.Span("Base completa para suas análises"), html.Span("Ver planilha →", className="tool-action")], href="#excel-dados"),
            html.A([html.Span("02 / DASHBOARD", className="tool-tag"), html.Strong("Dashboard no Excel"), html.Span("Filtros, indicadores e gráficos nativos"), html.Span("Conhecer o dashboard →", className="tool-action")], href="#excel"),
            html.A([html.Span("03 / PYTHON", className="tool-tag"), html.Strong("Python + Excel"), html.Span("Caderno de análise e geração da planilha"), html.Span("Explorar o código →", className="tool-action")], href="#python-excel"),
        ]),
        html.Div(className="notice", children=[
            html.Span("i", className="notice-icon", **{"aria-hidden": "true"}),
            html.Div([
                html.Strong("Sobre esta análise. "),
                "Os dados são históricos e os rótulos vêm da base original. Associações não comprovam fraude, e não há avaliação de vagas atuais.",
            ]),
        ]),
        html.Nav(id="story-nav", className="story-nav", **{"aria-label": "Percurso da análise"}, children=[
            html.A([html.Span(number), label], href=f"#{target}", **{"data-story-target": target})
            for number, label, target in [
                ("01", "Recorte", "recorte"), ("02", "Panorama", "panorama"),
                ("03", "Percurso", "percurso"), ("04", "Anúncios", "caderno"),
            ]
        ]),
        html.Section(id="ponto-de-partida", tabIndex=-1, className="opening-chapter", children=[
            html.Div("01 / ANTES DE PROCURAR UM PADRÃO", className="eyebrow"),
            html.Div(className="opening-columns", children=[
                html.H2("O raro chama atenção.\nO contexto muda tudo."),
                html.Div([
                    html.P(f"Só {BASE_RATE:.2f}% dos anúncios desta base têm rótulo de fraude. Isso torna as contagens e os denominadores tão importantes quanto as cores de um gráfico."),
                    html.P("Vamos seguir três passos: atravessar as combinações de sinais, comparar a extensão dos textos e voltar aos anúncios reais. Não há pontuação de risco escondida neste percurso."),
                    html.A("Escolher uma pergunta ↓", href="#recorte", className="back-link"),
                ]),
            ]),
        ]),
        html.Section(id="recorte", tabIndex=-1, className="filter-panel panel", children=[
            html.Div(className="section-heading", children=[
                html.Div([html.Div("01 / EXPLORAR", className="eyebrow"), html.H2("Escolha seu recorte")]),
                html.P("Comece pela base completa ou escolha uma pergunta. O mesmo recorte acompanha toda a leitura.", className="section-note"),
            ]),
            html.Div(className="filter-grid filter-primary", children=[
                field("Buscar na vaga", dcc.Input(id="f-busca", type="text", placeholder="Cargo, localização ou texto…", debounce=True), "search-field"),
                field("Status", dropdown("f-status", [
                    {"label": "Todos os anúncios", "value": "Todas"},
                    {"label": "Reais", "value": "Real"},
                    {"label": "Fraudulentos", "value": "Fraudulenta"},
                ], "Todos os anúncios", multi=False, value="Todas")),
                field("País", dropdown("f-pais", OPTS["pais"], "Todos os países")),
                field("Setor", dropdown("f-setor", OPTS["industry_clean"], "Todos os setores")),
            ]),
            html.Details(className="advanced-filters", children=[
                html.Summary("Mais filtros"),
                html.Div(className="filter-grid filter-advanced", children=[
                    field("Contrato", dropdown("f-contrato", OPTS["employment_type_clean"], "Todos os contratos")),
                    field("Experiência", dropdown("f-exp", OPTS["experience_clean"], "Todos os níveis")),
                    field("Escolaridade", dropdown("f-edu", OPTS["education_clean"], "Todas as escolaridades")),
                    field("Logo da empresa", dropdown("f-logo", [
                        {"label": "Todos", "value": "Todos"}, {"label": "Com logo", "value": "Sim"}, {"label": "Sem logo", "value": "Não"},
                    ], "Todos", multi=False, value="Todos")),
                    field("Trabalho remoto", dropdown("f-remoto", [
                        {"label": "Todos", "value": "Todos"}, {"label": "Remoto", "value": "Sim"}, {"label": "Não remoto", "value": "Não"},
                    ], "Todos", multi=False, value="Todos")),
                    field("Tamanho da descrição (caracteres)", dcc.RangeSlider(
                        id="f-tam", min=0, max=MAX_DESC_LEN, step=100, value=[0, MAX_DESC_LEN],
                        marks={0: "0", MAX_DESC_LEN: f"{MAX_DESC_LEN:,}".replace(",", ".")},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ), "range-field"),
                ]),
            ]),
            html.Div(className="question-presets", children=[
                html.Div([html.Strong("Comece com uma pergunta"),
                          html.P("Cada atalho substitui os filtros atuais; depois, refine seu recorte.")]),
                html.Div(className="preset-buttons", children=[
                    html.Button("Como são as vagas sem logo?", id="preset-logo", n_clicks=0, className="question-button"),
                    html.Button("O que muda no trabalho remoto?", id="preset-remoto", n_clicks=0, className="question-button"),
                    html.Button("Quais anúncios receberam rótulo de fraude?", id="preset-fraude", n_clicks=0, className="question-button"),
                ]),
            ]),
            story_links("Seu recorte está pronto. Siga o fio.", [("Ler o panorama ↓", "panorama")]),
        ]),
        dcc.Loading(type="circle", children=html.Div([
            html.Div(id="panorama", tabIndex=-1, className="results-heading", children=[
                html.Div([html.Div("02 / DESCOBRIR", className="eyebrow"), html.H2("O que os dados mostram")]),
                html.Div(id="result-context", className="result-context", role="status"),
            ]),
            html.Aside(className="selection-context", **{"aria-label": "Filtros que conectam a análise"}, children=[
                html.Div(id="active-filters", role="status", **{"aria-live": "polite", "aria-atomic": "true"}),
                html.P("Este recorte conecta indicadores, percurso, textos, atlas, anúncios e CSV. Remover um filtro atualiza todos eles; navegar entre blocos não altera sua seleção."),
                html.Div(className="context-actions", children=[
                    html.A("Editar recorte ↑", href="#recorte"),
                    html.Button("Limpar todos os filtros", id="btn-reset-context", n_clicks=0, className="text-button"),
                ]),
            ]),
            html.Section(id="analysis-summary", className="analysis-summary", **{"aria-label": "Resumo do recorte", "aria-live": "polite"}),
            story_links("Do panorama às perguntas: por onde aprofundar?", [
                ("Comparar setores ↓", "setores"), ("Cruzar sinais →", "sinais"),
                ("Ver contratos →", "contratos"), ("Explorar países →", "paises"),
            ]),
            html.Section(id="percurso", tabIndex=-1, className="story-chapter flow-chapter", children=[
                html.Div(className="chapter-margin", children=[html.Span("I"), html.P("CRUZAR / NÃO CONCLUIR")]),
                html.Div(className="chapter-content", children=[
                    html.Div("03 / SEGUIR AS COMBINAÇÕES", className="eyebrow"),
                    html.H2("Uma pista nunca vem sozinha."),
                    html.P("Acompanhe os anúncios de logo → trabalho remoto → rótulo histórico. A largura de cada faixa é a quantidade de anúncios; nenhuma faixa representa uma causa.", className="section-note"),
                    html.P("As duas primeiras etapas contam combinações agregadas; o diagrama não permite rastrear um anúncio individual de ponta a ponta. Os valores exatos de cada ligação aparecem ao passar o cursor.", className="method-note"),
                    story_graph("g-percurso", 430),
                    html.Div(id="flow-reading", role="status", className="story-reading"),
                    html.Details(className="text-alternative", children=[html.Summary("Ler os números sem o gráfico"), html.Div(id="flow-table")]),
                ]),
            ]),
            html.Section(id="textos", tabIndex=-1, className="story-chapter", children=[
                html.Div(className="chapter-margin", children=[html.Span("II"), html.P("LER / ALÉM DO TAMANHO")]),
                html.Div(className="chapter-content", children=[
                    html.Div("04 / A FORMA DOS TEXTOS", className="eyebrow"),
                    html.H2("Um texto longo inspira confiança?"),
                    html.P("Compare as distribuições, não só uma média. Para cada tamanho no eixo horizontal, a curva mostra a porcentagem de anúncios com até esse número de caracteres. Cada rótulo tem seu próprio denominador.", className="section-note"),
                    story_graph("g-textos", 360),
                    html.Div(id="text-reading", role="status", className="story-reading"),
                    html.P("Curvas próximas sugerem comprimentos parecidos; curvas diferentes não tornam o tamanho um detector de fraude. A comparação é descritiva e não controla setor, idioma ou país.", className="method-note"),
                ]),
            ]),
            html.Section(id="caderno", tabIndex=-1, className="casebook", children=[
                html.Div("05 / VOLTAR AO CONCRETO", className="eyebrow"),
                html.H2("Não são só pontos. São anúncios."),
                html.P("Um registro de cada rótulo disponível no recorte, escolhido pelo menor ID — não pelo texto mais convincente. Não são pares equivalentes nem exemplos representativos.", className="section-note"),
                html.Div(id="casebook-records", className="casebook-grid"),
            ]),
            html.Details(className="atlas", children=[
                html.Summary([html.Span("APROFUNDAR / ATLAS ANALÍTICO"), "Abrir setores, sinais, contratos e países"]),
            html.Div(id="analises", tabIndex=-1, className="connections-intro", children=[
                html.Div("03 / CONECTAR", className="eyebrow"),
                html.H2("Um recorte, quatro perspectivas"),
                html.P("Cada visual responde a uma pergunta diferente sobre os mesmos anúncios. Clique em um setor ou país para aplicar esse filtro a toda a análise. As legendas dos gráficos alteram apenas a visualização local.", className="section-note"),
                html.A("↑ Voltar ao panorama", href="#panorama", className="back-link"),
            ]),
            html.Div(className="charts-grid", children=[
                graph_card("01  /  COMPARAÇÃO", "Onde vale aprofundar a análise?",
                           "Clique em um ponto para filtrar o setor (ou use o filtro acima). Tamanho = volume; linha = taxa do recorte. Os dois controles abaixo afetam só este gráfico.",
                           "g-setores", wide=True, controls=html.Div(className="chart-controls", children=[
                               field("Ordenar setores por", dropdown("sector-order", [
                                   {"label": "Maior volume", "value": "total"}, {"label": "Maior taxa de fraude", "value": "taxa"},
                               ], "Maior volume", multi=False, value="total")),
                               field("Amostra mínima por setor", dropdown("sector-min", [
                                   {"label": f"{n} anúncio" + ("s" if n != 1 else ""), "value": n} for n in [1, 30, 100, 500]
                               ], "30 anúncios", multi=False, value=30)),
                           ])),
                graph_card("02  /  MAPA DE CALOR", "Logo × trabalho remoto",
                           "Cor = taxa de fraude; n = anúncios no grupo. Células vazias não têm dados. Ausência de logo não comprova fraude.", "g-logo-fraude"),
                graph_card("03  /  COMPOSIÇÃO", "Qual o perfil dos contratos?",
                           "Participação de cada contrato no recorte completo. Passe sobre uma fatia para ver a contagem; a legenda permite isolar categorias.", "g-contrato-exp"),
                graph_card("04  /  GEOGRAFIA", "Países com mais anúncios", "Clique em uma barra para filtrar o país (ou use o filtro acima). Os rótulos são empilhados; a cobertura dos 10 maiores países aparece no resumo.", "g-paises", wide=True),
            ]),
            ]),
            html.Section(id="explorador", tabIndex=-1, className="panel records-panel", children=[
                html.Div(className="section-heading records-heading", children=[
                    html.Div([html.Div("04 / INVESTIGAR", className="eyebrow"), html.H2("Investigue os anúncios"), html.P("Os padrões trouxeram você até aqui. Selecione uma linha para ler o anúncio que compõe este recorte.", className="section-note")]),
                    html.Div("Filtros e ordenação da tabela não alteram gráficos ou CSV.", className="table-note"),
                ]),
                html.Div(className="table-navigation", children=[
                    html.Span("Mais colunas à direita. Deslize a tabela ou use as setas."),
                    html.Button("← Colunas", type="button", **{"data-table-scroll": "-1", "aria-label": "Ver colunas anteriores", "aria-controls": "tabela-vagas"}),
                    html.Button("Colunas →", type="button", **{"data-table-scroll": "1", "aria-label": "Ver próximas colunas", "aria-controls": "tabela-vagas"}),
                ]),
                dash_table.DataTable(
                    id="tabela-vagas",
                    columns=[
                        {"name": "ID", "id": "id_vaga", "type": "numeric"}, {"name": "Cargo", "id": "title"},
                        {"name": "Status", "id": "status_vaga"}, {"name": "País", "id": "pais"},
                        {"name": "Setor", "id": "industry_clean"}, {"name": "Contrato", "id": "employment_type_clean"},
                        {"name": "Experiência", "id": "experience_clean"}, {"name": "Salário", "id": "salary_range"},
                        {"name": "Logo", "id": "tem_logo"}, {"name": "Remoto", "id": "remoto"},
                        {"name": "Caracteres", "id": "tamanho_descricao", "type": "numeric"},
                    ],
                    page_size=10, sort_action="native", filter_action="native", row_selectable="single",
                    selected_rows=[], style_table={"overflowX": "auto"},
                    style_header={"backgroundColor": "#eae3d7", "color": "#68594f", "fontWeight": "700", "fontSize": "11px", "border": "0", "borderBottom": "1px solid #d6cdbf", "textTransform": "uppercase"},
                    style_data={"backgroundColor": "#f4efe5"},
                    style_cell={"textAlign": "left", "padding": "12px", "fontSize": "13px", "minWidth": "85px", "maxWidth": "230px", "overflow": "hidden", "textOverflow": "ellipsis", "border": "0", "borderBottom": "1px solid #ded6ca", "fontFamily": "Jost, Segoe UI, Arial, sans-serif", "color": "#28211e"},
                    style_data_conditional=[{"if": {"filter_query": '{status_vaga} = "Fraudulenta"', "column_id": "status_vaga"}, "color": "#ad4035", "fontWeight": "700"}],
                ),
                html.A("Ler registro selecionado ↓", href="#detalhe-vaga", className="back-link"),
                html.Div(id="detalhe-vaga", tabIndex=-1, className="record-detail"),
                story_links("A investigação pode continuar por outro caminho.", [
                    ("← Rever os visuais", "analises"), ("Mudar a pergunta ↑", "recorte"), ("Voltar ao início ↑", "visao-geral"),
                ]),
            ]),
        ])),
        html.Section(id="excel", tabIndex=-1, className="workbook-panel", children=[
            html.Div([
                html.Div("05 / LEVAR COM VOCÊ", className="eyebrow"),
                html.H2("A análise continua no Excel."),
                html.P("A mesma base, em uma planilha independente: seis filtros combinados, indicadores e quatro gráficos nativos. Sem macros e sem conexão à internet.", className="section-note"),
                html.A("↓ Baixar dashboard Excel", href=WORKBOOK_URL, className="button button-primary workbook-download"),
                html.A("Baixar somente os dados (.xlsx)", href=WORKBOOK_URL.replace("Jobs_Database.xlsx", "Jobs_Data.xlsx"), className="back-link data-download"),
                html.P("Arquivo completo da base histórica — não aplica os filtros desta página. Para levar somente seu recorte, use Exportar CSV no início.", className="workbook-scope"),
            ]),
            html.Ol(className="workbook-steps", children=[
                html.Li([html.Span("01"), html.Div([html.Strong("Escolha na aba Dashboard"), html.P("País, setor, contrato, status, logo e trabalho remoto atualizam os indicadores e gráficos juntos.")])]),
                html.Li([html.Span("02"), html.Div([html.Strong("Investigue a base completa"), html.P("Leia os textos e use os filtros da tabela. Eles são independentes das listas do Dashboard.")])]),
                html.Li([html.Span("03"), html.Div([html.Strong("Leve a interpretação junto"), html.P("A aba Leia-me explica taxas, recortes e limites. Abra no Microsoft Excel com cálculo automático.")])]),
            ]),
        ]),
        html.Section(id="excel-dados", tabIndex=-1, className="resource-panel", children=[
            html.Div([
                html.Div("EXCEL / BASE DE DADOS", className="eyebrow"),
                html.H2("A planilha, sem complicação."),
                html.P("Uma única aba com os 10.000 anúncios e todas as colunas. Ideal para consultar, organizar e criar suas próprias análises. Este arquivo não contém o dashboard nem fórmulas.", className="section-note"),
            ]),
            html.Div([
                html.A("↓ Baixar base Excel (.xlsx)", href=WORKBOOK_URL.replace("Jobs_Database.xlsx", "Jobs_Data.xlsx"), className="button button-primary resource-download"),
                html.P("Base completa da revisão publicada. Os filtros do site não são aplicados ao arquivo.", className="workbook-scope"),
            ]),
        ]),
        html.Section(id="python-excel", tabIndex=-1, className="resource-panel", children=[
            html.Div([
                html.Div("PYTHON + EXCEL / CÓDIGO ABERTO", className="eyebrow"),
                html.H2("Dos dados à planilha."),
                html.P("Veja os cálculos no caderno Python e o script que gera o dashboard Excel a partir da mesma base SQLite usada pelo app. O painel web é construído com Python, Dash e Plotly.", className="section-note"),
            ]),
            html.Div(className="source-links", children=[
                html.A("Abrir caderno Python (.ipynb) ↗", href=f"{SOURCE_URL}/Analise.ipynb", target="_blank", rel="noopener noreferrer"),
                html.A("Ver geração do Excel (.py) ↗", href=f"{SOURCE_URL}/scripts/build_workbook.py", target="_blank", rel="noopener noreferrer"),
                html.A("Ver código do dashboard web ↗", href=f"{SOURCE_URL}/app.py", target="_blank", rel="noopener noreferrer"),
                html.P("Requer execução local com as dependências do projeto. Alterar a planilha baixada não atualiza o site; não há sincronização automática.", className="workbook-scope"),
            ]),
        ]),
        html.Footer("Radar de vagas · Uma ferramenta de exploração, não um classificador de fraude.", className="footer"),
    ]),
])


def make_kpi_card(title: str, value: str, subtitle: str, accent: str) -> html.Div:
    return html.Div(className=f"kpi-card kpi-{accent}", children=[
        html.Div(title, className="kpi-label"),
        html.Div(value, className="kpi-value"),
        html.Div(subtitle, className="kpi-subtitle"),
    ])


@dash_app.callback(
    Output("f-status", "value"), Output("f-busca", "value"), Output("f-logo", "value"),
    Output("f-remoto", "value"), Output("f-pais", "value"), Output("f-setor", "value"),
    Output("f-contrato", "value"), Output("f-exp", "value"), Output("f-edu", "value"),
    Output("f-tam", "value"), Output("tabela-vagas", "filter_query"),
    Output("sector-order", "value"), Output("sector-min", "value"),
    Output("g-setores", "clickData"), Output("g-paises", "clickData"),
    Input("btn-reset", "n_clicks"), Input("btn-reset-context", "n_clicks"), prevent_initial_call=True,
)
def reset_filters(_n, _context_n=None):
    return "Todas", "", "Todos", "Todos", [], [], [], [], [], [0, MAX_DESC_LEN], "", "total", 30, None, None


PRESET_FILTERS = {
    "preset-logo": {"f-logo": "Não"},
    "preset-remoto": {"f-remoto": "Sim"},
    "preset-fraude": {"f-status": "Fraudulenta"},
}


def preset_values(preset_id):
    values = list(reset_filters(1))
    order = ["f-status", "f-busca", "f-logo", "f-remoto", "f-pais", "f-setor", "f-contrato", "f-exp", "f-edu"]
    for field_id, value in PRESET_FILTERS[preset_id].items():
        values[order.index(field_id)] = value
    return tuple(values)


@dash_app.callback(
    Output("f-status", "value", allow_duplicate=True), Output("f-busca", "value", allow_duplicate=True),
    Output("f-logo", "value", allow_duplicate=True), Output("f-remoto", "value", allow_duplicate=True),
    Output("f-pais", "value", allow_duplicate=True), Output("f-setor", "value", allow_duplicate=True),
    Output("f-contrato", "value", allow_duplicate=True), Output("f-exp", "value", allow_duplicate=True),
    Output("f-edu", "value", allow_duplicate=True), Output("f-tam", "value", allow_duplicate=True),
    Output("tabela-vagas", "filter_query", allow_duplicate=True), Output("sector-order", "value", allow_duplicate=True),
    Output("sector-min", "value", allow_duplicate=True), Output("g-setores", "clickData", allow_duplicate=True),
    Output("g-paises", "clickData", allow_duplicate=True),
    *[Input(preset, "n_clicks") for preset in PRESET_FILTERS], prevent_initial_call=True,
)
def explore_question(*_clicks):
    return preset_values(ctx.triggered_id)


def chart_filter_selection(chart_id, click_data):
    if not click_data or not click_data.get("points"):
        return no_update, no_update
    point = click_data["points"][0]
    if chart_id == "g-setores":
        value = point.get("y")
        if value in {option["value"] for option in OPTS["industry_clean"]}:
            return [value], no_update
    elif chart_id == "g-paises":
        value = point.get("x")
        if value in {option["value"] for option in OPTS["pais"]}:
            return no_update, [value]
    return no_update, no_update


@dash_app.callback(
    Output("f-setor", "value", allow_duplicate=True), Output("f-pais", "value", allow_duplicate=True),
    Input("g-setores", "clickData"), Input("g-paises", "clickData"), prevent_initial_call=True,
)
def filter_from_chart(sector_click, country_click):
    return chart_filter_selection(ctx.triggered_id, sector_click if ctx.triggered_id == "g-setores" else country_click)


FILTER_IDS = ["f-status", "f-pais", "f-setor", "f-contrato", "f-exp", "f-edu", "f-logo", "f-remoto", "f-busca", "f-tam"]
FILTER_LABELS = ["Status", "País", "Setor", "Contrato", "Experiência", "Escolaridade", "Logo", "Remoto", "Busca", "Descrição"]
FILTER_DEFAULTS = ["Todas", [], [], [], [], [], "Todos", "Todos", "", [0, MAX_DESC_LEN]]


def active_filter_labels(*values):
    chips = []
    for id, label, default, value in zip(FILTER_IDS, FILTER_LABELS, FILTER_DEFAULTS, values):
        if value is None or value == default or (id == "f-busca" and not value.strip()):
            continue
        if id == "f-tam":
            text = f"{format_count(value[0])}–{format_count(value[1])} caracteres"
        elif isinstance(value, list):
            text = ", ".join(str(item) for item in value)
        else:
            text = str(value)
        chips.append(html.Button([
            f"{label}: {text}", html.Span(" ×", **{"aria-hidden": "true"}),
        ], id={"type": "remove-filter", "key": id}, n_clicks=0, className="filter-chip",
            **{"aria-label": f"Remover filtro {label}: {text}"}))
    return [html.Strong("Recorte em foco"), html.Div(chips, className="filter-chips")] if chips else [
        html.Strong("Base completa"), html.Span(" · nenhum filtro aplicado"),
    ]


@dash_app.callback(
    Output("active-filters", "children"),
    *[Output(f"recorte-{chart_id}", "children") for chart_id in CHART_ANCHORS],
    *[Input(id, "value") for id in FILTER_IDS],
)
def describe_selection(*values):
    labels = active_filter_labels(*values)
    summary = ("Recorte em foco · " + " · ".join(chip.children[0] for chip in labels[1].children)
               if labels[0].children == "Recorte em foco" else "Base completa · nenhum filtro aplicado")
    return (labels, *([summary] * len(CHART_ANCHORS)))


def clear_filter_values(filter_id):
    values = [default if id == filter_id else no_update for id, default in zip(FILTER_IDS, FILTER_DEFAULTS)]
    return (*values, None if filter_id == "f-setor" else no_update, None if filter_id == "f-pais" else no_update)


@dash_app.callback(
    *[Output(id, "value", allow_duplicate=True) for id in FILTER_IDS],
    Output("g-setores", "clickData", allow_duplicate=True), Output("g-paises", "clickData", allow_duplicate=True),
    Input({"type": "remove-filter", "key": ALL}, "n_clicks"), prevent_initial_call=True,
)
def remove_filter(clicks):
    # Pattern inputs also change when chips mount/unmount; only a real button click removes a filter.
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or not any(
        item["id"] == triggered and item["value"] for item in ctx.inputs_list[0]
    ):
        return (no_update,) * 12
    return clear_filter_values(triggered["key"])


def chart_layout(fig, height=320):
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=12, r=20, t=15, b=35),
        font=dict(family="Jost, Segoe UI, Arial, sans-serif", color="#68594f", size=11),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(title=None, orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(bgcolor="#f4efe5", bordercolor="#b8ac9b", font_size=13),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#ded6ca", zeroline=False, automargin=True)
    return fig


def empty_chart(message="Nenhum resultado neste recorte"):
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(color="#68594f", size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return chart_layout(fig)


@dash_app.callback(
    Output("result-context", "children"), Output("kpi-row", "children"),
    Output("g-setores", "figure"), Output("g-logo-fraude", "figure"),
    Output("g-contrato-exp", "figure"), Output("g-paises", "figure"),
    Output("tabela-vagas", "data"), Output("tabela-vagas", "selected_rows"), Output("tabela-vagas", "page_current"),
    Output("analysis-summary", "children"),
    Input("f-status", "value"), Input("f-pais", "value"), Input("f-setor", "value"),
    Input("f-contrato", "value"), Input("f-exp", "value"), Input("f-edu", "value"),
    Input("f-logo", "value"), Input("f-remoto", "value"), Input("f-busca", "value"), Input("f-tam", "value"),
    Input("sector-order", "value"), Input("sector-min", "value"),
)
def update_dashboard(status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range, sector_order="total", sector_min=30):
    df = query_vagas(status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range)
    total = len(df)
    frauds = int(df["fraude_bin"].sum())
    rate = frauds / total * 100 if total else None
    no_logo = int((df["tem_logo"] == "Não").sum())
    context = f"{format_count(total)} de {format_count(OPTS['total'])} anúncios"
    if status and status != "Todas":
        context += " · Status filtrado: taxas refletem apenas os rótulos selecionados."
    kpis = [
        make_kpi_card("Anúncios no recorte", format_count(total), f"de {format_count(OPTS['total'])} na base", "blue"),
        make_kpi_card("Rotulados como fraude", format_count(frauds), "anúncios no recorte", "red"),
        make_kpi_card("Taxa de fraude", f"{rate:.1f}%" if rate is not None else "—",
                      "Calculada após o filtro de status" if status and status != "Todas" else f"Base completa: {BASE_RATE:.2f}%", "violet"),
        make_kpi_card("Sem logo", f"{no_logo / total * 100:.1f}%" if total else "—", f"{format_count(no_logo)} anúncios no recorte", "amber"),
    ]
    if not total:
        return context, kpis, empty_chart(), empty_chart(), empty_chart(), empty_chart(), [], [], 0, html.P("Nenhum anúncio encontrado. Altere a busca ou use Limpar filtros.")

    sectors = df.groupby("industry_clean", as_index=False).agg(total=("id_vaga", "size"), fraudes=("fraude_bin", "sum"))
    sectors["taxa"] = 100 * sectors["fraudes"] / sectors["total"]
    eligible = sectors[sectors["total"] >= sector_min]
    ranked = eligible.sort_values([sector_order, "industry_clean"], ascending=[False, True]).head(10)
    plotted = ranked.iloc[::-1]
    if plotted.empty:
        fig_sectors = empty_chart(f"Nenhum setor com pelo menos<br>{sector_min} anúncios.<br>Reduza a amostra mínima.")
    else:
        fig_sectors = px.scatter(
            plotted, x="taxa", y="industry_clean", size="total", size_max=28,
            custom_data=["fraudes", "total"], color_discrete_sequence=["#758361"],
            labels={"taxa": "Taxa de fraude", "industry_clean": ""},
        )
        fig_sectors.update_traces(cliponaxis=False, marker=dict(opacity=.85, line=dict(width=1, color="white")),
                                 hovertemplate="<b>%{y}</b><br>Taxa: %{x:.1f}%<br>Fraudes: %{customdata[0]} de %{customdata[1]} anúncios<extra></extra>")
        chart_layout(fig_sectors, 390)
        fig_sectors.add_vline(x=rate, line_dash="dot", line_color="#c4513f")
        fig_sectors.update_xaxes(showgrid=True, gridcolor="#ded6ca", ticksuffix="%",
                                 range=[0, max(float(plotted["taxa"].max()), rate, 5) * 1.15])
        fig_sectors.update_yaxes(showgrid=False, ticklabelstandoff=18, categoryorder="array", categoryarray=plotted["industry_clean"].tolist(),
                                 tickmode="array", tickvals=plotted["industry_clean"].tolist(),
                                 ticktext=[name if len(name) <= 19 else name[:18] + "…" for name in plotted["industry_clean"]])

    groups = df.groupby(["tem_logo", "remoto"], as_index=False).agg(total=("id_vaga", "size"), fraudes=("fraude_bin", "sum"))
    lookup = {(row.tem_logo, row.remoto): row for row in groups.itertuples()}
    z, text, custom = [], [], []
    for remote in ["Não", "Sim"]:
        z_row, text_row, custom_row = [], [], []
        for logo_value in ["Sim", "Não"]:
            group = lookup.get((logo_value, remote))
            if group is None:
                z_row.append(None)
                text_row.append("Sem dados")
                custom_row.append([0, 0])
            else:
                cell_rate = 100 * group.fraudes / group.total
                z_row.append(cell_rate)
                text_row.append(f"{cell_rate:.1f}%<br>n={format_count(group.total)}")
                custom_row.append([group.fraudes, group.total])
        z.append(z_row)
        text.append(text_row)
        custom.append(custom_row)
    fig_logo = go.Figure(go.Heatmap(
        z=z, x=["Com logo", "Sem logo"], y=["Não remoto", "Remoto"], customdata=custom,
        text=text, texttemplate="%{text}", textfont=dict(size=12), hoverongaps=False,
        zmin=0, zmax=100, colorscale=[[0, "#eee7dc"], [.3, "#e2a48c"], [1, "#a3362c"]],
        colorbar=dict(title="%", thickness=10, len=.7), xgap=5, ygap=5,
        hovertemplate="%{x} · %{y}<br>Taxa: %{z:.1f}%<br>Fraudes: %{customdata[0]} de %{customdata[1]} anúncios<extra></extra>",
    ))
    chart_layout(fig_logo, 390)
    fig_logo.update_yaxes(showgrid=False, autorange="reversed")
    fig_logo.update_layout(margin=dict(l=10, r=10, t=20, b=35))

    colors = {"Real": "#758361", "Fraudulenta": "#ce5845"}
    contracts = df.groupby("employment_type_clean", as_index=False).size().sort_values(["size", "employment_type_clean"], ascending=[False, True])
    fig_contracts = go.Figure(go.Pie(
        labels=contracts["employment_type_clean"], values=contracts["size"], hole=.64, sort=False,
        marker=dict(colors=["#758361", "#c0c7a8", "#a49ab3", "#d6b16d", "#8eacb0", "#ce8975", "#b7ad9e"]),
        textinfo="percent", textposition="inside", insidetextorientation="horizontal",
        hovertemplate="<b>%{label}</b><br>%{value} anúncios · %{percent}<extra></extra>",
    ))
    chart_layout(fig_contracts, 330)
    fig_contracts.update_layout(legend=dict(orientation="h", yanchor="top", y=-.08, x=0, font_size=10),
                                margin=dict(l=5, r=5, t=5, b=70), uniformtext_minsize=10, uniformtext_mode="hide")
    fig_contracts.add_annotation(text=f"<b>{format_count(total)}</b><br>anúncios", x=.5, y=.5,
                                 showarrow=False, font=dict(size=15, color="#28211e"))

    top_countries = df["pais"].value_counts().head(10).index
    countries = df[df["pais"].isin(top_countries)].groupby(["pais", "status_vaga"], as_index=False).size()
    fig_countries = px.bar(countries, x="pais", y="size", color="status_vaga", barmode="stack",
                           labels={"pais": "", "size": "Anúncios", "status_vaga": ""}, color_discrete_map=colors)
    chart_layout(fig_countries, 330)
    fig_countries.update_xaxes(categoryorder="total descending")
    fig_countries.update_yaxes(rangemode="tozero")

    country_counts = df["pais"].value_counts()
    top_country = country_counts.index[0]
    country_share = 100 * country_counts.iloc[0] / total
    coverage = 100 * country_counts.head(10).sum() / total
    comparison = ("O filtro de status está ativo: as taxas refletem somente os rótulos selecionados."
                  if status and status != "Todas" else
                  f"Diferença para a base completa: {rate - BASE_RATE:+.1f} pontos percentuais. Não indica causalidade.")
    summary = [
        html.Div([html.Div("LEITURA DO RECORTE", className="eyebrow"), html.H3(f"{rate:.1f}% rotulados como fraude"), html.P(comparison)]),
        html.Div([html.Div("CONCENTRAÇÃO", className="eyebrow"), html.H3(f"{top_country} · {country_share:.1f}% dos anúncios"),
                  html.P(f"Os 10 maiores países cobrem {coverage:.1f}% do recorte. País não informado permanece como categoria da base.")]),
        html.Div([html.Div("COMO EXPLORAR", className="eyebrow"), html.H3("Compare antes de concluir"),
                  html.P(f"{len(eligible)} setores atendem à amostra mínima de {sector_min} anúncios; o gráfico mostra até 10. Use os filtros de país e setor para investigar e a tabela para ler os registros.")]),
    ]
    records = df[TABLE_COLS].copy()
    records["id"] = records["id_vaga"]
    return context, kpis, fig_sectors, fig_logo, fig_contracts, fig_countries, records.to_dict("records"), [], 0, summary


@dash_app.callback(
    Output("detalhe-vaga", "children"),
    Input("tabela-vagas", "derived_virtual_selected_row_ids"),
)
def mostrar_detalhe_vaga(selected_ids):
    if not selected_ids:
        return html.Div([html.Strong("Selecione um anúncio"), html.P("Use o botão ao lado de uma linha para abrir os detalhes.")], className="detail-empty")
    with closing(get_db_connection()) as conn:
        row = pd.read_sql_query("SELECT * FROM vagas WHERE id_vaga = ?", conn, params=[selected_ids[0]])
    if row.empty:
        return html.Div("Registro não encontrado.", className="detail-empty")
    r = row.iloc[0].fillna("")
    fraud = r["status_vaga"] == "Fraudulenta"
    return html.Div([
        html.Div(className="detail-heading", children=[
            html.Div([html.Div("REGISTRO SELECIONADO", className="eyebrow"), html.H3(f"#{r['id_vaga']} · {r['title']}")]),
            html.Span(r["status_vaga"], className=f"status-pill {'status-fraud' if fraud else 'status-real'}"),
        ]),
        html.P(f"{r['location'] or 'Localização não informada'}  ·  {r['industry_clean']}  ·  {r['employment_type_clean']}  ·  {r['experience_clean']}  ·  Salário: {r['salary_range'] or 'Não informado'}", className="detail-meta"),
        html.Div(className="detail-grid", children=[
            html.Div([html.H4("Descrição"), html.P(r["description"] or "Não informada.")]),
            html.Div([
                html.H4("Requisitos"), html.P(r["requirements"] or "Não informados."),
                html.H4("Empresa"), html.P(r["company_profile"] or "Não informada."),
                html.H4("Benefícios"), html.P(r["benefits"] or "Não informados."),
            ]),
        ]),
    ])


def flow_figure(df):
    if df.empty:
        return empty_chart(), [], "Nenhum anúncio neste recorte. Limpe ou altere os filtros."
    nodes = ["Com logo", "Sem logo", "Não remoto", "Remoto", "Real", "Fraudulenta"]
    sources, targets, counts = [], [], []
    rows = []
    for left, right, left_map, right_map in [
        ("tem_logo", "remoto", {"Sim": 0, "Não": 1}, {"Não": 2, "Sim": 3}),
        ("remoto", "status_vaga", {"Não": 2, "Sim": 3}, {"Real": 4, "Fraudulenta": 5}),
    ]:
        for (a, b), count in df.groupby([left, right]).size().items():
            source, target = left_map[a], right_map[b]
            sources.append(source)
            targets.append(target)
            counts.append(int(count))
            rows.append(html.Tr([html.Td(nodes[source]), html.Td(nodes[target]), html.Td(format_count(int(count)))]))
    chart = go.Figure(go.Sankey(
        arrangement="snap", valueformat=",d", valuesuffix=" anúncios",
        node=dict(label=nodes, pad=24, thickness=14, color=["#758361", "#b5aa99", "#94849c", "#c49a65", "#758361", "#ad4035"],
                  line=dict(color="#f4efe5", width=1)),
        link=dict(source=sources, target=targets, value=counts,
                  color=["rgba(173,64,53,.38)" if target == 5 else "rgba(117,131,97,.25)" for target in targets],
                  hovertemplate="%{source.label} → %{target.label}<br>%{value:,d} anúncios<extra></extra>"),
    ))
    chart_layout(chart, 430)
    chart.update_layout(margin=dict(l=10, r=12, t=24, b=18), font_size=12)
    table = html.Table([html.Caption("Ligações agregadas no recorte"),
                        html.Thead(html.Tr([html.Th("De"), html.Th("Para"), html.Th("Anúncios")])), html.Tbody(rows)])
    return chart, table, f"{format_count(len(df))} anúncios em cada etapa. As duas transições contam a mesma população: não some as faixas de etapas diferentes."


def text_distribution(df):
    if df.empty:
        return empty_chart(), "Não há textos para comparar neste recorte."
    fig = go.Figure()
    readings = []
    for label, color in [("Real", "#65734f"), ("Fraudulenta", "#ad4035")]:
        values = df.loc[df.status_vaga == label, "tamanho_descricao"].sort_values()
        if values.empty:
            readings.append(f"{label}: sem anúncios no recorte.")
            continue
        frequencies = values.value_counts().sort_index()
        cumulative = 100 * frequencies.cumsum() / len(values)
        x = [0, *frequencies.index.tolist()]
        y = [0, *cumulative.tolist()]
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=f"{label} · n={format_count(len(values))}",
                                 line=dict(color=color, width=2.5, shape="hv", dash="solid" if label == "Real" else "dash"),
                                 hovertemplate=f"{label}<br>Até %{{x:,d}} caracteres: %{{y:.1f}}%<extra></extra>"))
        readings.append(f"{label}: mediana de {format_count(round(float(values.median())))} caracteres, n={format_count(len(values))}.")
    chart_layout(fig, 360)
    fig.update_xaxes(title="Caracteres na descrição", rangemode="tozero", showgrid=True, gridcolor="#ded6ca")
    fig.update_yaxes(title="Anúncios com até esse tamanho", range=[0, 102], ticksuffix="%")
    fig.update_layout(margin=dict(l=8, r=12, t=48, b=42), legend=dict(y=1.08))
    return fig, " ".join(readings)


def casebook(df):
    if df.empty:
        return html.P("Nenhum anúncio neste recorte. Tente outra pergunta.")
    ids = [int(group.id_vaga.min()) for _, group in df.groupby("status_vaga", sort=True)]
    with closing(get_db_connection()) as conn:
        records = pd.read_sql_query(f"SELECT * FROM vagas WHERE id_vaga IN ({','.join('?' for _ in ids)}) ORDER BY status_vaga DESC", conn, params=ids)
    cards = []
    for r in records.fillna("").to_dict("records"):
        cards.append(html.Article(className="case-card", children=[
            html.Div([html.Span(f"ARQUIVO / {r['id_vaga']:05d}", className="eyebrow"),
                      html.Span(r["status_vaga"], className="status-pill " + ("status-fraud" if r["fraude_bin"] else "status-real"))], className="case-label"),
            html.H3(r["title"]),
            html.P(f"{r['pais']} · {r['industry_clean']} · {r['employment_type_clean']}", className="detail-meta"),
            html.Dl([html.Dt("Logo"), html.Dd(r["tem_logo"]), html.Dt("Remoto"), html.Dd(r["remoto"]),
                     html.Dt("Caracteres"), html.Dd(format_count(r["tamanho_descricao"]))]),
            html.P(r["description"][:360] + ("…" if len(r["description"]) > 360 else ""), className="case-excerpt"),
            html.Details(children=[html.Summary(f"Ler o anúncio completo #{r['id_vaga']}"),
                                   *[html.Div([html.H4(label), html.P(r[key] or "Não informado.")])
                                     for key, label in [("description", "Descrição"), ("requirements", "Requisitos"),
                                                        ("company_profile", "Empresa"), ("benefits", "Benefícios")]]]),
        ]))
    return cards


@dash_app.callback(
    Output("g-percurso", "figure"), Output("flow-table", "children"), Output("flow-reading", "children"),
    Output("g-textos", "figure"), Output("text-reading", "children"), Output("casebook-records", "children"),
    *[Input(id, "value") for id in FILTER_IDS],
)
def update_story(*filters):
    df = query_vagas(*filters)
    flow, table, reading = flow_figure(df)
    distribution, explanation = text_distribution(df)
    return flow, table, reading, distribution, explanation, casebook(df)


EXPORT_PAGE_SIZE = 100


@server.post("/api/export")
def export_page():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, "Solicitação de exportação inválida.")
    filters = body.get("filters")
    offset = body.get("offset")
    if (
        not isinstance(filters, list) or len(filters) != 10
        or not isinstance(offset, int) or isinstance(offset, bool) or offset < 0
        or any(value is not None and not isinstance(value, str) for value in (filters[0], filters[6], filters[7], filters[8]))
        or any(value is not None and (not isinstance(value, list) or any(not isinstance(item, str) for item in value))
               for value in filters[1:6])
        or not isinstance(filters[9], list) or len(filters[9]) != 2
        or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in filters[9])
    ):
        abort(400, "Filtros de exportação inválidos.")
    df = query_vagas(*filters, include_details=True, limit=EXPORT_PAGE_SIZE + 1, offset=offset)
    response = Response(df.iloc[:EXPORT_PAGE_SIZE].to_csv(index=False, header=offset == 0), mimetype="text/csv")
    response.headers["X-Export-Has-More"] = "1" if len(df) > EXPORT_PAGE_SIZE else "0"
    return response


dash_app.clientside_callback(
    ClientsideFunction(namespace="dashboard", function_name="exportCsv"),
    Output("export-status", "children"), Input("btn-download", "n_clicks"),
    State("f-status", "value"), State("f-pais", "value"), State("f-setor", "value"),
    State("f-contrato", "value"), State("f-exp", "value"), State("f-edu", "value"),
    State("f-logo", "value"), State("f-remoto", "value"), State("f-busca", "value"),
    State("f-tam", "value"), prevent_initial_call=True,
)


if __name__ == "__main__":
    dash_app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))
