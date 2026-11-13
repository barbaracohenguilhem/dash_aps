#!/usr/bin/env python3
"""Aplicação Web Interativa em Python Dash (compatível com Vercel Serverless WSGI e execução local)."""

import os
import sqlite3
from urllib.parse import quote
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "jobs_database.db")


def get_db_connection() -> sqlite3.Connection:
    """Abre conexão somente-leitura compatível com o filesystem serverless da Vercel."""
    return sqlite3.connect(f"file:{quote(DB_PATH)}?mode=ro", uri=True)


def get_filter_options() -> dict:
    conn = get_db_connection()
    opts = {}
    for col in ["pais", "industry_clean", "employment_type_clean", "experience_clean", "education_clean"]:
        df_opt = pd.read_sql_query(
            f"SELECT {col} AS val, COUNT(*) AS qtd FROM vagas GROUP BY {col} ORDER BY qtd DESC",
            conn,
        )
        opts[col] = [
            {"label": f"{r['val']} ({r['qtd']})", "value": r["val"]}
            for _, r in df_opt.iterrows()
            if r["val"]
        ]
    max_len = conn.execute("SELECT MAX(tamanho_descricao) FROM vagas").fetchone()[0] or 15000
    conn.close()
    opts["max_len"] = int(max_len)
    return opts


def query_vagas(
    status: str,
    paises: list | None,
    setores: list | None,
    contratos: list | None,
    experiencias: list | None,
    escolaridades: list | None,
    tem_logo: str,
    remoto: str,
    busca: str | None,
    tam_range: list | None,
) -> pd.DataFrame:
    clauses = ["1=1"]
    params: list = []

    if status and status != "Todas":
        clauses.append("status_vaga = ?")
        params.append(status)

    def add_in_clause(col_name: str, values: list | None) -> None:
        if values:
            placeholders = ",".join("?" for _ in values)
            clauses.append(f"{col_name} IN ({placeholders})")
            params.extend(values)

    add_in_clause("pais", paises)
    add_in_clause("industry_clean", setores)
    add_in_clause("employment_type_clean", contratos)
    add_in_clause("experience_clean", experiencias)
    add_in_clause("education_clean", escolaridades)

    if tem_logo and tem_logo != "Todos":
        clauses.append("tem_logo = ?")
        params.append(tem_logo)

    if remoto and remoto != "Todos":
        clauses.append("remoto = ?")
        params.append(remoto)

    if tam_range and len(tam_range) == 2:
        clauses.append("tamanho_descricao BETWEEN ? AND ?")
        params.extend([int(tam_range[0]), int(tam_range[1])])

    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        clauses.append(
            "(title LIKE ? OR description LIKE ? OR requirements LIKE ? OR company_profile LIKE ? OR location LIKE ?)"
        )
        params.extend([termo, termo, termo, termo, termo])

    sql = f"""
        SELECT id_vaga, title, status_vaga, fraude_bin, pais, location,
               industry_clean, employment_type_clean, experience_clean,
               education_clean, salary_range, tem_logo, remoto, tem_perguntas,
               tamanho_descricao, company_profile, description, requirements, benefits
        FROM vagas
        WHERE {' AND '.join(clauses)}
        ORDER BY id_vaga ASC
    """
    conn = get_db_connection()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


OPTS = get_filter_options()
MAX_DESC_LEN = OPTS["max_len"]

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
                ),
            ],
        ),

        html.Div(id="detalhe-vaga", className="panel detail-panel", style=CARD_STYLE),
    ],
)


def make_kpi_card(titulo: str, valor: str, subtitulo: str, cor_borda: str) -> html.Div:
    return html.Div(
        className="kpi-card",
        style={
            **CARD_STYLE,
            "borderLeft": f"5px solid {cor_borda}",
            "padding": "18px 20px",
        },
        children=[
            html.Div(titulo, className="kpi-title"),
            html.Div(valor, className="kpi-value"),
            html.Div(subtitulo, className="kpi-caption"),
        ],
    )


@dash_app.callback(
    Output("f-status", "value"),
    Output("f-busca", "value"),
    Output("f-logo", "value"),
    Output("f-remoto", "value"),
    Output("f-pais", "value"),
    Output("f-setor", "value"),
    Output("f-contrato", "value"),
    Output("f-exp", "value"),
    Output("f-edu", "value"),
    Output("f-tam", "value"),
    Input("btn-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_n: int):
    return "Todas", "", "Todos", "Todos", [], [], [], [], [], [0, MAX_DESC_LEN]


@dash_app.callback(
    Output("kpi-row", "children"),
    Output("g-setores", "figure"),
    Output("g-logo-fraude", "figure"),
    Output("g-contrato-exp", "figure"),
    Output("g-paises", "figure"),
    Output("tabela-vagas", "data"),
    Output("tabela-vagas", "selected_rows"),
    Input("f-status", "value"),
    Input("f-pais", "value"),
    Input("f-setor", "value"),
    Input("f-contrato", "value"),
    Input("f-exp", "value"),
    Input("f-edu", "value"),
    Input("f-logo", "value"),
    Input("f-remoto", "value"),
    Input("f-busca", "value"),
    Input("f-tam", "value"),
)
def update_dashboard(status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range):
    df = query_vagas(status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range)

    total = len(df)
    fraudes = int(df["fraude_bin"].sum()) if total else 0
    reais = total - fraudes
    taxa = (fraudes / total * 100) if total else 0.0
    sem_logo_pct = ((df["tem_logo"] == "Não").mean() * 100) if total else 0.0

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
    )

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

    # Limitar envio inicial da tabela a colunas leves + manter id_vaga para buscar detalhe completo no SQLite
    table_cols = [
        "id_vaga", "title", "status_vaga", "pais", "industry_clean",
        "employment_type_clean", "experience_clean", "salary_range",
        "tem_logo", "remoto", "tamanho_descricao",
    ]
    records = df[table_cols].head(2000).to_dict("records")
    return kpis, fig_setores, fig_logo, fig_emp, fig_paises, records, [0] if records else []


@dash_app.callback(
    Output("detalhe-vaga", "children"),
    Input("tabela-vagas", "derived_virtual_data"),
    Input("tabela-vagas", "derived_virtual_selected_rows"),
)
def mostrar_detalhe_vaga(rows, selected_rows):
    if not rows:
        return html.Div("Nenhuma vaga selecionada.", style={"color": "#64748B"})

    idx = selected_rows[0] if selected_rows and selected_rows[0] < len(rows) else 0
    vaga_id = rows[idx]["id_vaga"]

    conn = get_db_connection()
    df_row = pd.read_sql_query("SELECT * FROM vagas WHERE id_vaga = ?", conn, params=[vaga_id])
    conn.close()
    if df_row.empty:
        return html.Div("Registro não encontrado.")

    r = df_row.iloc[0]
    is_fraud = r["status_vaga"] == "Fraudulenta"
    badge_bg = "#FEE2E2" if is_fraud else "#DCFCE7"
    badge_fg = "#991B1B" if is_fraud else "#166534"

    return html.Div([
        html.Div(
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "12px"},
            children=[
                html.H3(
                    f"#{r['id_vaga']} — {r['title']}",
                    style={"margin": "0", "fontSize": "18px", "color": "#0F172A"},
                ),
                html.Span(
                    r["status_vaga"].upper(),
                    style={
                        "backgroundColor": badge_bg,
                        "color": badge_fg,
                        "padding": "5px 12px",
                        "borderRadius": "999px",
                        "fontWeight": "700",
                        "fontSize": "12px",
                    },
                ),
            ],
        ),
        html.Div(
            f"Localização: {r['location'] or 'Não informada'}  •  Setor: {r['industry_clean']}  •  "
            f"Contrato: {r['employment_type_clean']}  •  Experiência: {r['experience_clean']}  •  "
            f"Faixa Salarial: {r['salary_range'] or 'Não informada'}",
            style={"fontSize": "13px", "color": "#475569", "marginBottom": "14px"},
        ),
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(300px, 1fr))", "gap": "14px"},
            children=[
                html.Div([
                    html.Strong("Descrição da Vaga (Limpa):", style={"fontSize": "13px", "color": "#1E293B"}),
                    html.P(r["description"] or "Sem descrição.", style={"fontSize": "13px", "lineHeight": "1.55", "color": "#334155"}),
                ]),
                html.Div([
                    html.Strong("Requisitos:", style={"fontSize": "13px", "color": "#1E293B"}),
                    html.P(r["requirements"] or "Não informado.", style={"fontSize": "13px", "lineHeight": "1.55", "color": "#334155"}),
                    html.Strong("Perfil da Empresa & Benefícios:", style={"fontSize": "13px", "color": "#1E293B"}),
                    html.P(
                        f"{r['company_profile'] or ''}  {('• Benefícios: ' + r['benefits']) if r['benefits'] else ''}".strip() or "Não informado.",
                        style={"fontSize": "13px", "lineHeight": "1.55", "color": "#334155"},
                    ),
                ]),
            ],
        ),
    ])


@dash_app.callback(
    Output("download-dataframe-csv", "data"),
    Input("btn-download", "n_clicks"),
    State("f-status", "value"),
    State("f-pais", "value"),
    State("f-setor", "value"),
    State("f-contrato", "value"),
    State("f-exp", "value"),
    State("f-edu", "value"),
    State("f-logo", "value"),
    State("f-remoto", "value"),
    State("f-busca", "value"),
    State("f-tam", "value"),
    prevent_initial_call=True,
)
def exportar_csv(_n, status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range):
    df = query_vagas(status, paises, setores, contratos, exps, edus, logo, remoto, busca, tam_range)
    return dcc.send_data_frame(df.to_csv, "vagas_filtradas.csv", index=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    dash_app.run(debug=False, host="0.0.0.0", port=port)

