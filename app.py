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

dash_app = Dash(__name__, title="Job Postings Fraud Analytics — Database")
app = dash_app.server
server = dash_app.server

CARD_STYLE = {
    "backgroundColor": "#FFFFFF",
    "borderRadius": "18px",
    "padding": "20px 22px",
    "boxShadow": "0 12px 30px rgba(15, 23, 42, 0.045)",
    "border": "1px solid #E7EBF3",
}

LABEL_STYLE = {
    "fontSize": "11px",
    "fontWeight": "600",
    "color": "#64718A",
    "marginBottom": "7px",
    "display": "block",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
}

dash_app.layout = html.Div(
    className="app-shell",
    style={
        "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "minHeight": "100vh",
        "color": "#0F172A",
    },
    children=[
        html.Div(
            className="hero",
            style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "flexWrap": "wrap",
                "gap": "20px",
                "marginBottom": "22px",
            },
            children=[
                html.Div(
                    className="hero-copy",
                    children=[
                        html.Div("PAINEL DE ANÁLISE", className="hero-eyebrow"),
                        html.H2(
                            "Job Posting Fraud Analytics",
                            className="hero-title",
                        ),
                        html.P(
                            "Explore 10.000 anúncios de emprego e investigue sinais de fraude.",
                            className="hero-subtitle",
                        ),
                    ],
                ),
                html.Div(
                    className="hero-actions",
                    style={"display": "flex", "gap": "10px"},
                    children=[
                        html.Button(
                            "Limpar Filtros",
                            id="btn-reset",
                            n_clicks=0,
                            className="button button-secondary",
                            style={
                                "backgroundColor": "#334155",
                                "color": "#FFFFFF",
                                "border": "1px solid #475569",
                                "borderRadius": "8px",
                                "padding": "9px 16px",
                                "cursor": "pointer",
                                "fontWeight": "600",
                            },
                        ),
                        html.Button(
                            "Baixar CSV Filtrado",
                            id="btn-download",
                            n_clicks=0,
                            className="button button-primary",
                            style={
                                "backgroundColor": "#2563EB",
                                "color": "#FFFFFF",
                                "border": "none",
                                "borderRadius": "8px",
                                "padding": "9px 16px",
                                "cursor": "pointer",
                                "fontWeight": "600",
                            },
                        ),
                        dcc.Download(id="download-dataframe-csv"),
                    ],
                ),
            ],
        ),

        html.Div(
            className="panel filter-panel",
            style={**CARD_STYLE, "marginBottom": "20px"},
            children=[
                html.Div(
                    className="section-heading",
                    children=[
                        html.Div("REFINE A BUSCA", className="section-eyebrow"),
                        html.H3("Filtros interativos", className="section-title"),
                    ],
                ),
                html.Div(
                    className="filter-grid",
                    style={
                        "display": "grid",
                        "gridTemplateColumns": "repeat(auto-fit, minmax(210px, 1fr))",
                        "gap": "18px 16px",
                    },
                    children=[
                        html.Div([
                            html.Label("Status da Vaga", style=LABEL_STYLE),
                            dcc.RadioItems(
                                id="f-status",
                                options=[
                                    {"label": " Todas", "value": "Todas"},
                                    {"label": " Reais", "value": "Real"},
                                    {"label": " Fraudulentas", "value": "Fraudulenta"},
                                ],
                                value="Todas",
                                inline=True,
                                className="status-control",
                                labelStyle={"marginRight": "12px", "fontSize": "13px", "cursor": "pointer"},
                            ),
                        ]),
                        html.Div([
                            html.Label("Busca por Palavra-Chave (Cargo / Texto)", style=LABEL_STYLE),
                            dcc.Input(
                                id="f-busca",
                                type="text",
                                placeholder="Ex.: Engineer, Data, Work from home...",
                                debounce=True,
                                className="search-input",
                                style={
                                    "width": "100%",
                                    "padding": "9px 12px",
                                    "borderRadius": "9px",
                                    "border": "1px solid #DCE2ED",
                                    "boxSizing": "border-box",
                                },
                            ),
                        ]),
                        html.Div([
                            html.Label("Logo da Empresa", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-logo",
                                options=[
                                    {"label": "Todos (Com e Sem Logo)", "value": "Todos"},
                                    {"label": "Com Logo (Sim)", "value": "Sim"},
                                    {"label": "Sem Logo (Não)", "value": "Não"},
                                ],
                                value="Todos",
                                clearable=False,
                            ),
                        ]),
                        html.Div([
                            html.Label("Trabalho Remoto", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-remoto",
                                options=[
                                    {"label": "Todos (Presencial e Remoto)", "value": "Todos"},
                                    {"label": "Remoto (Sim)", "value": "Sim"},
                                    {"label": "Presencial (Não)", "value": "Não"},
                                ],
                                value="Todos",
                                clearable=False,
                            ),
                        ]),
                        html.Div([
                            html.Label("País", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-pais",
                                options=OPTS["pais"],
                                multi=True,
                                placeholder="Todos os países...",
                            ),
                        ]),
                        html.Div([
                            html.Label("Indústria / Setor", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-setor",
                                options=OPTS["industry_clean"],
                                multi=True,
                                placeholder="Todos os setores...",
                            ),
                        ]),
                        html.Div([
                            html.Label("Tipo de Contrato", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-contrato",
                                options=OPTS["employment_type_clean"],
                                multi=True,
                                placeholder="Full-time, Part-time, Contract...",
                            ),
                        ]),
                        html.Div([
                            html.Label("Nível de Experiência", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-exp",
                                options=OPTS["experience_clean"],
                                multi=True,
                                placeholder="Entry level, Mid-Senior...",
                            ),
                        ]),
                        html.Div([
                            html.Label("Escolaridade Exigida", style=LABEL_STYLE),
                            dcc.Dropdown(
                                id="f-edu",
                                options=OPTS["education_clean"],
                                multi=True,
                                placeholder="Bachelor's, High School...",
                            ),
                        ]),
                        html.Div(
                            className="range-field",
                            style={"gridColumn": "span 2"},
                            children=[
                                html.Label("Tamanho do Texto da Descrição (caracteres)", style=LABEL_STYLE),
                                dcc.RangeSlider(
                                    id="f-tam",
                                    min=0,
                                    max=MAX_DESC_LEN,
                                    step=100,
                                    value=[0, MAX_DESC_LEN],
                                    marks={
                                        0: "0",
                                        2500: "2.5k",
                                        5000: "5k",
                                        10000: "10k",
                                        MAX_DESC_LEN: f"{MAX_DESC_LEN}",
                                    },
                                    tooltip={"placement": "bottom", "always_visible": False},
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        html.Div(
            id="kpi-row",
            className="kpi-grid",
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))",
                "gap": "14px",
                "marginBottom": "20px",
            },
        ),

        html.Div(
            className="chart-grid",
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(360px, 1fr))",
                "gap": "16px",
                "marginBottom": "20px",
            },
            children=[
                html.Div(
                    className="panel chart-panel",
                    style=CARD_STYLE,
                    children=[dcc.Graph(id="g-setores", config={"displayModeBar": False})],
                ),
                html.Div(
                    className="panel chart-panel",
                    style=CARD_STYLE,
                    children=[dcc.Graph(id="g-logo-fraude", config={"displayModeBar": False})],
                ),
                html.Div(
                    className="panel chart-panel",
                    style=CARD_STYLE,
                    children=[dcc.Graph(id="g-contrato-exp", config={"displayModeBar": False})],
                ),
                html.Div(
                    className="panel chart-panel",
                    style=CARD_STYLE,
                    children=[dcc.Graph(id="g-paises", config={"displayModeBar": False})],
                ),
            ],
        ),

        html.Div(
            className="panel table-panel",
            style={**CARD_STYLE, "marginBottom": "20px"},
            children=[
                html.Div(
                    className="table-heading",
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "10px"},
                    children=[
                        html.H3(
                            "Anúncios de emprego",
                            className="section-title",
                        ),
                        html.Span(
                            "Selecione uma linha para ver os detalhes. Use os cabeçalhos para filtrar.",
                            className="table-hint",
                        ),
                    ],
                ),
                dash_table.DataTable(
                    id="tabela-vagas",
                    columns=[
                        {"name": "ID", "id": "id_vaga", "type": "numeric"},
                        {"name": "Cargo", "id": "title"},
                        {"name": "Status", "id": "status_vaga"},
                        {"name": "País", "id": "pais"},
                        {"name": "Setor", "id": "industry_clean"},
                        {"name": "Contrato", "id": "employment_type_clean"},
                        {"name": "Experiência", "id": "experience_clean"},
                        {"name": "Salário", "id": "salary_range"},
                        {"name": "Logo?", "id": "tem_logo"},
                        {"name": "Remoto?", "id": "remoto"},
                        {"name": "Tam. Texto", "id": "tamanho_descricao", "type": "numeric"},
                    ],
                    page_size=12,
                    sort_action="native",
                    filter_action="native",
                    row_selectable="single",
                    selected_rows=[0],
                    style_table={"overflowX": "auto"},
                    style_header={
                        "backgroundColor": "#F6F8FC",
                        "color": "#526079",
                        "fontWeight": "600",
                        "fontSize": "11px",
                        "border": "1px solid #E7EBF3",
                        "textTransform": "uppercase",
                    },
                    style_cell={
                        "textAlign": "left",
                        "padding": "11px 12px",
                        "fontSize": "12px",
                        "maxWidth": "260px",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                        "border": "1px solid #EDF0F5",
                        "color": "#34415B",
                    },
                    style_data_conditional=[
                        {
                            "if": {"filter_query": '{status_vaga} = "Fraudulenta"'},
                            "backgroundColor": "#FFF1F2",
                            "color": "#BE123C",
                            "fontWeight": "600",
                        },
                        {
                            "if": {"row_index": "odd", "filter_query": '{status_vaga} != "Fraudulenta"'},
                            "backgroundColor": "#FAFBFD",
                        },
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


    kpis = [
        make_kpi_card("Vagas Filtradas", f"{total:,}".replace(",", "."), "de 10.000 registros na base", "#2563EB"),
        make_kpi_card("Vagas Reais", f"{reais:,}".replace(",", "."), f"{(100 - taxa):.1f}% do filtro atual", "#10B981"),
        make_kpi_card("Vagas Fraudulentas", f"{fraudes:,}".replace(",", "."), "detectadas no recorte", "#EF4444"),
        make_kpi_card("Taxa de Fraude", f"{taxa:.2f}%", "média global = 4.53%", "#F59E0B"),
        make_kpi_card("Sem Logo de Empresa", f"{sem_logo_pct:.1f}%", "fator clássico de alerta", "#8B5CF6"),
    ]

    empty_layout = dict(
        template="plotly_white",
        margin=dict(l=24, r=22, t=50, b=34),
        height=340,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", size=11, color="#71809A"),
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

    if total == 0:
        empty_fig = go.Figure().update_layout(
            title="Nenhuma vaga encontrada para este filtro",
            title_font=dict(size=14, color="#25314C"),
            **empty_layout,
        )
        return kpis, empty_fig, empty_fig, empty_fig, empty_fig, [], []

    # Gráfico 1: Top 10 Setores (Real vs Fraudulenta)
    top_ind = df["industry_clean"].value_counts().head(10).index.tolist()
    df_ind = (
        df[df["industry_clean"].isin(top_ind)]
        .groupby(["industry_clean", "status_vaga"], as_index=False)
        .size()
    )
    fig_setores = px.bar(
        df_ind,
        x="size",
        y="industry_clean",
        color="status_vaga",
        orientation="h",
        barmode="stack",
        color_discrete_map={"Real": "#3B82F6", "Fraudulenta": "#EF4444"},
        labels={"size": "Quantidade de Vagas", "industry_clean": "Setor", "status_vaga": "Status"},
        title="Top 10 Setores / Indústrias no Filtro",
    )
    fig_setores.update_layout(
        **empty_layout,
        title_font=dict(size=14, color="#25314C"),
        title_x=0.02,
        yaxis={"categoryorder": "total ascending", "showgrid": False},
        legend_title_text="",
    )

    # Gráfico 2: Taxa de Fraude (%) Com Logo vs Sem Logo + Remoto
    grp_logo = (
        df.groupby(["tem_logo", "remoto"], as_index=False)
        .agg(Total=("id_vaga", "count"), Fraudes=("fraude_bin", "sum"))
    )
    grp_logo["Taxa_Fraude"] = (grp_logo["Fraudes"] / grp_logo["Total"] * 100).round(2)
    grp_logo["Grupo"] = grp_logo["tem_logo"].map({"Sim": "Com Logo", "Não": "Sem Logo"})
    grp_logo["Modalidade"] = grp_logo["remoto"].map({"Sim": "Remoto", "Não": "Presencial"})

    fig_logo = px.bar(
        grp_logo,
        x="Grupo",
        y="Taxa_Fraude",
        color="Modalidade",
        barmode="group",
        text="Taxa_Fraude",
        color_discrete_map={"Presencial": "#0EA5E9", "Remoto": "#F97316"},
        labels={"Taxa_Fraude": "Taxa de Fraude (%)", "Grupo": "Presença de Logo da Empresa"},
        title="Taxa de Fraude (%) — Logo da Empresa × Trabalho Remoto",
    )
    fig_logo.update_traces(texttemplate="%{text:.1f}%", textposition="outside", marker_line_width=0)
    fig_logo.update_layout(
        **empty_layout,
        title_font=dict(size=14, color="#25314C"),
        title_x=0.02,
        yaxis_range=[0, max(grp_logo["Taxa_Fraude"].max() * 1.25, 5)],
        yaxis={"gridcolor": "#EEF1F6"},
        legend_title_text="",
    )

    # Gráfico 3: Tipo de Contrato vs Experiência
    df_emp = (
        df.groupby(["employment_type_clean", "status_vaga"], as_index=False)
        .size()
    )
    fig_emp = px.bar(
        df_emp,
        x="employment_type_clean",
        y="size",
        color="status_vaga",
        barmode="group",
        color_discrete_map={"Real": "#10B981", "Fraudulenta": "#EF4444"},
        labels={"employment_type_clean": "Tipo de Contrato", "size": "Vagas", "status_vaga": "Status"},
        title="Distribuição por Tipo de Contrato",
    )
    fig_emp.update_layout(
        **empty_layout,
        title_font=dict(size=14, color="#25314C"),
        title_x=0.02,
        xaxis={"categoryorder": "total descending", "showgrid": False},
        yaxis={"gridcolor": "#EEF1F6"},
        legend_title_text="",
    )

    # Gráfico 4: Top 10 Países no Filtro
    top_paises = df["pais"].value_counts().head(10).index.tolist()
    df_pais = (
        df[df["pais"].isin(top_paises)]
        .groupby(["pais", "status_vaga"], as_index=False)
        .size()
    )
    fig_paises = px.bar(
        df_pais,
        x="pais",
        y="size",
        color="status_vaga",
        barmode="stack",
        color_discrete_map={"Real": "#6366F1", "Fraudulenta": "#EF4444"},
        labels={"pais": "País", "size": "Vagas", "status_vaga": "Status"},
        title="Top 10 Países no Recorte Atual",
    )
    fig_paises.update_layout(
        **empty_layout,
        title_font=dict(size=14, color="#25314C"),
        title_x=0.02,
        xaxis={"categoryorder": "total descending", "showgrid": False},
        yaxis={"gridcolor": "#EEF1F6"},
        legend_title_text="",
    )

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
