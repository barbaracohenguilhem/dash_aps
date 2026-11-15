#!/usr/bin/env python3
"""Explorador dos rótulos de fraude da base de anúncios de emprego."""

import os
import sqlite3
from contextlib import closing
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ClientsideFunction, Dash, Input, Output, State, dash_table, dcc, html
from flask import Response, abort, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
app = server = dash_app.server


def field(label, component, extra_class=""):
    return html.Div([html.Label(label, htmlFor=component.id), component], className=f"field {extra_class}")


def dropdown(id, options, placeholder, multi=True, value=None):
    return dcc.Dropdown(id=id, options=options, value=value, multi=multi, clearable=multi, placeholder=placeholder)


def graph_card(eyebrow, title, description, graph_id, wide=False):
    return html.Section(
        [
            html.Div(eyebrow, className="eyebrow"),
            html.H3(title),
            html.P(description, className="card-description"),
            dcc.Graph(
                id=graph_id, config={"displayModeBar": False, "responsive": True},
                style={"height": "390px" if graph_id in ("g-setores", "g-logo-fraude") else "330px"},
            ),
        ],
        className=f"panel chart-card{' chart-wide' if wide else ''}",
    )


dash_app.layout = html.Div(className="app-shell", children=[
    html.Header(className="topbar", children=[
        html.Div(className="brand", children=[
            html.Div("R", className="brand-mark", **{"aria-hidden": "true"}),
            html.Div([html.Div("RADAR DE VAGAS", className="brand-name"), html.Div("Pesquisa de anúncios de emprego", className="brand-subtitle")]),
        ]),
        html.Div(className="topbar-right", children=[
            html.Span("BASE HISTÓRICA", className="data-badge"),
            html.Span("Análise exploratória", className="topbar-note"),
        ]),
    ]),
    html.Main(className="main-content", children=[
        html.Div(className="page-intro", children=[
            html.Div([
                html.Div("VISÃO GERAL  /  ANÚNCIOS", className="eyebrow"),
                html.H1("Entenda os padrões da base."),
                html.P("Explore os anúncios e compare os rótulos de fraude em cada recorte.", className="intro-copy"),
            ]),
            html.Div(className="intro-actions", children=[
                html.Button("Limpar filtros", id="btn-reset", n_clicks=0, className="button button-secondary"),
                html.Button("↓  Exportar CSV", id="btn-download", n_clicks=0, className="button button-primary"),
                html.Div(id="export-status", className="export-status", role="status"),
            ]),
        ]),
        html.Div(className="notice", children=[
            html.Span("i", className="notice-icon", **{"aria-hidden": "true"}),
            html.Div([
                html.Strong("Sobre esta análise. "),
                "Os dados são históricos e os rótulos vêm da base original. Associações não comprovam fraude, e não há avaliação de vagas atuais.",
            ]),
        ]),
        html.Section(className="filter-panel panel", children=[
            html.Div(className="section-heading", children=[
                html.Div([html.Div("EXPLORAR", className="eyebrow"), html.H2("Escolha seu recorte")]),
                html.P("Os indicadores e gráficos acompanham os filtros abaixo.", className="section-note"),
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
        ]),
        dcc.Loading(type="circle", children=html.Div([
            html.Div(className="results-heading", children=[
                html.Div([html.Div("SEU RECORTE", className="eyebrow"), html.H2("O que os dados mostram")]),
                html.Div(id="result-context", className="result-context", role="status"),
            ]),
            html.Div(id="kpi-row", className="kpi-grid"),
            html.Div(className="charts-grid", children=[
                graph_card("01  /  SETORES", "Como a taxa varia por setor?", "Taxa de fraude nos dez maiores setores por volume. O número entre parênteses é o total de anúncios.", "g-setores", wide=True),
                graph_card("02  /  CARACTERÍSTICAS", "Logo e modalidade", "Taxa de fraude e tamanho da amostra em cada grupo. Ausência de logo não é prova de fraude.", "g-logo-fraude"),
                graph_card("03  /  CONTRATOS", "Distribuição por contrato", "Quantidade de anúncios por tipo de contrato e rótulo.", "g-contrato-exp"),
                graph_card("04  /  GEOGRAFIA", "Países com mais anúncios", "Dez maiores grupos do recorte, com contagem de rótulos.", "g-paises", wide=True),
            ]),
            html.Section(className="panel records-panel", children=[
                html.Div(className="section-heading records-heading", children=[
                    html.Div([html.Div("EXPLORADOR", className="eyebrow"), html.H2("Investigue os anúncios"), html.P("Selecione uma linha para ler o registro completo.", className="section-note")]),
                    html.Div("Filtros e ordenação da tabela não alteram gráficos ou CSV.", className="table-note"),
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
                    style_header={"backgroundColor": "#f5f7fa", "color": "#566478", "fontWeight": "700", "fontSize": "11px", "border": "0", "borderBottom": "1px solid #e3e9f0", "textTransform": "uppercase"},
                    style_cell={"textAlign": "left", "padding": "12px", "fontSize": "13px", "minWidth": "85px", "maxWidth": "230px", "overflow": "hidden", "textOverflow": "ellipsis", "border": "0", "borderBottom": "1px solid #edf1f5", "fontFamily": "Segoe UI, Arial, sans-serif", "color": "#334155"},
                    style_data_conditional=[{"if": {"filter_query": '{status_vaga} = "Fraudulenta"', "column_id": "status_vaga"}, "color": "#b33c4a", "fontWeight": "700"}],
                ),
                html.Div(id="detalhe-vaga", className="record-detail"),
            ]),
        ])),
        html.Footer("Radar de vagas · Uma ferramenta de exploração, não um classificador de fraude.", className="footer"),
    ]),
])


def format_count(value: int) -> str:
    return f"{value:,}".replace(",", ".")


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
    Input("btn-reset", "n_clicks"), prevent_initial_call=True,
)
def reset_filters(_n):
    return "Todas", "", "Todos", "Todos", [], [], [], [], [], [0, MAX_DESC_LEN], ""


def chart_layout(fig, height=320):
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=12, r=20, t=15, b=35),
        font=dict(family="Arial, sans-serif", color="#64748b", size=11),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(title=None, orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#edf1f5", zeroline=False, automargin=True)
    return fig


def empty_chart():
    fig = go.Figure()
    fig.add_annotation(text="Nenhum resultado neste recorte", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(color="#7c8a9b", size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return chart_layout(fig)


@dash_app.callback(
    Output("result-context", "children"), Output("kpi-row", "children"),
    Output("g-setores", "figure"), Output("g-logo-fraude", "figure"),
    Output("g-contrato-exp", "figure"), Output("g-paises", "figure"),
    Output("tabela-vagas", "data"), Output("tabela-vagas", "selected_rows"), Output("tabela-vagas", "page_current"),
    Input("f-status", "value"), Input("f-pais", "value"), Input("f-setor", "value"),
    Input("f-contrato", "value"), Input("f-exp", "value"), Input("f-edu", "value"),
    Input("f-logo", "value"), Input("f-remoto", "value"), Input("f-busca", "value"), Input("f-tam", "value"),
)
def update_dashboard(status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range):
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
        return context, kpis, empty_chart(), empty_chart(), empty_chart(), empty_chart(), [], [], 0

    top = df["industry_clean"].value_counts().head(10).index
    sectors = df[df["industry_clean"].isin(top)].groupby("industry_clean", as_index=False).agg(total=("id_vaga", "size"), fraudes=("fraude_bin", "sum"))
    sectors["taxa"] = 100 * sectors["fraudes"] / sectors["total"]
    sectors = sectors.sort_values("total", ascending=True)
    sectors["label"] = sectors.apply(lambda row: f"{row['taxa']:.1f}%  (n={format_count(int(row['total']))})", axis=1)
    fig_sectors = px.bar(sectors, x="taxa", y="industry_clean", orientation="h", text="label",
                         custom_data=["fraudes", "total"],
                         labels={"taxa": "Taxa de fraude", "industry_clean": ""}, color_discrete_sequence=["#5774d8"])
    fig_sectors.update_traces(textposition="outside", cliponaxis=False, hovertemplate="<b>%{y}</b><br>Taxa: %{x:.1f}%<br>Fraudes: %{customdata[0]} de %{customdata[1]} anúncios<extra></extra>")
    chart_layout(fig_sectors, 390)
    fig_sectors.update_xaxes(showgrid=True, gridcolor="#edf1f5", range=[0, max(sectors["taxa"].max() * 1.7, 5)], ticksuffix="%")
    fig_sectors.update_yaxes(showgrid=False, categoryorder="array", categoryarray=sectors["industry_clean"].tolist(),
                             tickmode="array", tickvals=sectors["industry_clean"].tolist(),
                             ticktext=[name if len(name) <= 19 else name[:18] + "…" for name in sectors["industry_clean"]])

    groups = df.groupby(["tem_logo", "remoto"], as_index=False).agg(total=("id_vaga", "size"), fraudes=("fraude_bin", "sum"))
    groups["taxa"] = 100 * groups["fraudes"] / groups["total"]
    groups["logo"] = groups["tem_logo"].map({"Sim": "Com logo", "Não": "Sem logo"}).fillna(groups["tem_logo"])
    groups["modalidade"] = groups["remoto"].map({"Sim": "Remoto", "Não": "Não remoto"}).fillna(groups["remoto"])
    groups["amostra"] = groups["total"].map(lambda total: f"n={format_count(int(total))}")
    fig_logo = px.bar(groups, x="logo", y="taxa", color="modalidade", barmode="group",
                      text="amostra", custom_data=["fraudes", "total"], labels={"logo": "", "taxa": "Taxa de fraude (%)"},
                      color_discrete_map={"Não remoto": "#5774d8", "Remoto": "#54b8aa"})
    fig_logo.update_traces(textposition="outside", textfont_size=10, cliponaxis=False,
                           hovertemplate="<b>%{fullData.name}</b><br>Taxa: %{y:.1f}%<br>Fraudes: %{customdata[0]} de %{customdata[1]} anúncios<extra></extra>")
    chart_layout(fig_logo, 390)
    fig_logo.update_yaxes(range=[0, max(groups["taxa"].max() * 1.25, 5)], ticksuffix="%")

    colors = {"Real": "#5774d8", "Fraudulenta": "#e9828c"}
    contracts = df.groupby(["employment_type_clean", "status_vaga"], as_index=False).size()
    fig_contracts = px.bar(contracts, x="employment_type_clean", y="size", color="status_vaga", barmode="stack",
                           labels={"employment_type_clean": "", "size": "Anúncios", "status_vaga": ""},
                           color_discrete_map=colors)
    chart_layout(fig_contracts, 330)
    fig_contracts.update_xaxes(categoryorder="total descending")
    fig_contracts.update_yaxes(rangemode="tozero")

    top_countries = df["pais"].value_counts().head(10).index
    countries = df[df["pais"].isin(top_countries)].groupby(["pais", "status_vaga"], as_index=False).size()
    fig_countries = px.bar(countries, x="pais", y="size", color="status_vaga", barmode="stack",
                           labels={"pais": "", "size": "Anúncios", "status_vaga": ""}, color_discrete_map=colors)
    chart_layout(fig_countries, 330)
    fig_countries.update_xaxes(categoryorder="total descending")
    fig_countries.update_yaxes(rangemode="tozero")

    records = df[TABLE_COLS].copy()
    records["id"] = records["id_vaga"]
    return context, kpis, fig_sectors, fig_logo, fig_contracts, fig_countries, records.to_dict("records"), [], 0


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
