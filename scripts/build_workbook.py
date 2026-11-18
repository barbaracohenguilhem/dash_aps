#!/usr/bin/env python3
"""Build the offline Excel dashboard from the same read-only database as Dash.

No macros, external connections or dynamic-array functions. Formula caches contain
real default-selection results, so file previews don't show artificial zeroes.
"""
from contextlib import closing
from pathlib import Path
import argparse
import sqlite3

import pandas as pd
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

ROOT = Path(__file__).resolve().parents[1]
EXPORT_COLUMNS = [
    "id_vaga", "title", "status_vaga", "fraude_bin", "pais", "location",
    "industry_clean", "employment_type_clean", "experience_clean", "education_clean",
    "function_clean", "department", "salary_range", "tem_logo", "remoto", "tem_perguntas",
    "tamanho_descricao", "company_profile", "description", "requirements", "benefits",
]
HEADERS = [
    "ID", "Cargo", "Status", "Flag fraude", "País", "Localização", "Setor", "Contrato",
    "Experiência", "Escolaridade", "Função", "Departamento", "Salário", "Logo", "Remoto",
    "Perguntas", "Caracteres", "Empresa", "Descrição", "Requisitos", "Benefícios",
]
# Cell positions are part of the workbook's documented interface.
FILTERS = [("País", "pais", "B6"), ("Setor", "industry_clean", "F6"),
           ("Contrato", "employment_type_clean", "J6"), ("Status", "status_vaga", "B9"),
           ("Logo", "tem_logo", "F9"), ("Remoto", "remoto", "J9")]
ALL = "Todos"


def matching_rows(df, selection=None):
    """Python oracle for formula caches and regression tests (exact equality)."""
    result = df
    for column, value in (selection or {}).items():
        if value != ALL:
            result = result[result[column] == value]
    return result


def count_formula(last_row, extra=None, frauds=False):
    # SUMPRODUCT equality handles literal *, ? and ~ without wildcard criteria.
    factors = []
    for _, column, cell in FILTERS:
        letter = xl_col_to_name(EXPORT_COLUMNS.index(column))
        reference = f"Dashboard!${cell[0]}${cell[1:]}"
        values = f"'Base_Interativa_Vagas'!${letter}$5:${letter}${last_row}"
        factors.append(f'((({values}={reference})+({reference}="{ALL}"))>0)')
    if extra:
        column, reference = extra
        letter = xl_col_to_name(EXPORT_COLUMNS.index(column))
        factors.append(f"('Base_Interativa_Vagas'!${letter}$5:${letter}${last_row}={reference})")
    if frauds:
        factors.append(f"'Base_Interativa_Vagas'!$D$5:$D${last_row}")
    return "=SUMPRODUCT(" + "*".join(factors) + ")"


def build_workbook(output=ROOT / "Jobs_Database.xlsx", database=ROOT / "data/jobs_database.db", selection=None):
    with closing(sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True)) as conn:
        df = pd.read_sql_query(f"SELECT {', '.join(EXPORT_COLUMNS)} FROM vagas ORDER BY id_vaga", conn).fillna("")
    if df.empty:
        raise ValueError("A base não pode estar vazia")
    selection = selection or {}
    for _, column, _ in FILTERS:
        value = selection.get(column, ALL)
        if value != ALL and value not in set(df[column]):
            raise ValueError(f"Filtro inválido: {column}={value}")
    chosen = matching_rows(df, selection)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with xlsxwriter.Workbook(output, {"strings_to_formulas": False, "strings_to_urls": False}) as book:
        book.set_properties({"title": "Radar de vagas — Dashboard interativo", "comments": "Dados históricos; não classifica vagas atuais."})
        book.set_calc_mode("auto")
        dash = book.add_worksheet("Dashboard")
        base = book.add_worksheet("Base_Interativa_Vagas")
        summary = book.add_worksheet("Analises")
        guide = book.add_worksheet("Leia-me")
        lists = book.add_worksheet("Listas")
        lists.hide()
        paper, ink, muted, accent, moss = "#F4EFE5", "#28211E", "#68594F", "#AD4035", "#758361"
        def fmt(**values):
            return book.add_format({"font_name": "Calibri", "font_color": ink, "bg_color": paper, **values})
        title = fmt(font_size=28, bold=True)
        eyebrow = fmt(font_size=10, font_color=accent, bold=True)
        note = fmt(font_size=11, font_color=muted, text_wrap=True, valign="top")
        label = fmt(font_size=10, bold=True, font_color=muted)
        select = fmt(font_size=12, bold=True, bg_color="#FFFFFF", border=1, border_color="#D6CDBF", valign="vcenter")
        integer = fmt(font_size=30, bold=True, num_format="#,##0")
        percent = fmt(font_size=30, bold=True, num_format="0.0%", font_color=accent)
        table_head = fmt(bold=True, bg_color="#EAE3D7", bottom=1, border_color="#D6CDBF")
        for sheet in (dash, summary, guide):
            sheet.hide_gridlines(2)
            sheet.set_tab_color(accent if sheet == dash else moss)
            sheet.set_column("A:A", 3)
            sheet.set_column("B:M", 12)
            for row in range(58 if sheet == dash else 18):
                sheet.set_row(row, 22, fmt())
        dash.set_landscape()
        dash.fit_to_pages(1, 1)
        dash.print_area("A1:M55")
        dash.freeze_panes(10, 0)
        dash.merge_range("B2:M2", "RADAR DE VAGAS / EXCEL", eyebrow)
        dash.merge_range("B3:M4", "Um recorte. Novas perspectivas.", title)
        for index, (name, column, cell) in enumerate(FILTERS):
            row = int(cell[1:]) - 1
            col = ord(cell[0]) - ord("A")
            dash.write(row - 1, col, name.upper(), label)
            values = [ALL] + sorted(str(v) for v in df[column].unique())
            lists.write_column(0, index, values)
            book.define_name(f"Filtro{index}", f"=Listas!${xl_col_to_name(index)}$1:${xl_col_to_name(index)}${len(values)}")
            dash.merge_range(row, col, row, col + 2, selection.get(column, ALL), select)
            dash.set_row(row, 30, fmt())
            dash.data_validation(cell, {"validate": "list", "source": f"=Filtro{index}", "error_type": "stop",
                                        "error_title": "Escolha um valor da lista", "error_message": "Use a seta da célula para selecionar.",
                                        "input_title": name, "input_message": "Todos remove este filtro.", "ignore_blank": False})
        dash.merge_range("B11:M12", "Escolha nas seis listas brancas. Indicadores, tabelas de análise e gráficos respondem juntos. Para recomeçar, selecione Todos em cada lista.", note)
        n, frauds = len(chosen), int(chosen.fraude_bin.sum())
        for region, text, cell, formula, cache, style in [
            ("B14:D14", "ANÚNCIOS NO RECORTE", "B15:D16", count_formula(len(df) + 4), n, integer),
            ("F14:H14", "RÓTULOS DE FRAUDE", "F15:H16", count_formula(len(df) + 4, frauds=True), frauds, integer),
            ("J14:L14", "TAXA NO RECORTE", "J15:L16", "=IFERROR(F15/B15,0)", frauds / n if n else 0, percent),
        ]:
            dash.merge_range(region, text, label)
            dash.merge_range(cell, "", style)
            dash.write_formula(cell.split(":")[0], formula, style, cache)
        dash.merge_range("B18:M19", "Taxa = rótulos de fraude ÷ anúncios no recorte. Sem anúncios, a taxa exibida é 0%. Filtrar Status para Fraudulenta produz 100%; não é uma previsão de risco.", note)
        base.hide_gridlines(2)
        base.freeze_panes(4, 2)
        base.set_column("A:A", 8)
        base.set_column("B:B", 40)
        base.set_column("C:Q", 22)
        base.set_column("R:U", 55)
        base.set_row(0, 30)
        base.write("A1", "Filtre a tabela abaixo; os subtotais desta aba acompanham as linhas visíveis.", label)
        base.write_formula("B2", f"=SUBTOTAL(103,A5:A{len(df)+4})", None, len(df))
        base.write("A2", "Visíveis", label)
        base.write_formula("D2", f"=SUBTOTAL(109,D5:D{len(df)+4})", None, int(df.fraude_bin.sum()))
        base.write("C2", "Fraudulentas", label)
        base.write("F2", "Filtros da base e do Dashboard são independentes.", note)
        base.add_table(3, 0, len(df) + 3, len(EXPORT_COLUMNS) - 1, {
            "name": "TabelaVagasInterativa", "style": "Table Style Medium 4",
            "columns": [{"header": h} for h in HEADERS], "data": df.values.tolist(),
        })
        # Every category is calculated. The sector chart intentionally uses the
        # ten largest sectors in the FULL base, not a misleading filtered ranking.
        summary.set_column("A:A", 44)
        summary.set_column("B:D", 18)
        summary.freeze_panes(3, 1)
        locations = {}
        cursor = 3
        for name, column in [("Status", "status_vaga"), ("Setores", "industry_clean"),
                             ("Contratos", "employment_type_clean"), ("Países", "pais")]:
            summary.write_row(cursor - 1, 0, [name, "Anúncios", "Fraudulentas", "Taxa"], table_head)
            values = df.groupby(column).size().sort_values(ascending=False, kind="stable").index.tolist()
            start = cursor
            for value in values:
                group = chosen[chosen[column] == value]
                count, fraud = len(group), int(group.fraude_bin.sum())
                row = cursor + 1
                summary.write(cursor, 0, value)
                extra = (column, f"$A{row}")
                summary.write_formula(cursor, 1, count_formula(len(df)+4, extra), None, count)
                summary.write_formula(cursor, 2, count_formula(len(df)+4, extra, True), None, fraud)
                summary.write_formula(cursor, 3, f"=IFERROR(C{row}/B{row},0)", book.add_format({"num_format": "0.0%"}), fraud/count if count else 0)
                cursor += 1
            locations[name] = (start, cursor - 1)
            cursor += 3
        def chart(kind, section, anchor, chart_title, limit=None):
            start, end = locations[section]
            if limit:
                end = min(end, start + limit - 1)
            obj = book.add_chart({"type": kind})
            obj.add_series({"name": "Anúncios", "categories": ["Analises", start, 0, end, 0],
                            "values": ["Analises", start, 1, end, 1],
                            "fill": {"color": moss}, "border": {"none": True},
                            **({"points": [{"fill": {"color": moss}}, {"fill": {"color": accent}}]} if kind == "doughnut" else {})})
            obj.set_title({"name": chart_title, "name_font": {"size": 12, "color": ink}})
            obj.set_chartarea({"fill": {"color": paper}, "border": {"none": True}})
            obj.set_plotarea({"fill": {"color": paper}, "border": {"none": True}})
            obj.set_legend({"position": "bottom", "font": {"size": 10}} if kind == "doughnut" else {"none": True})
            obj.set_size({"width": 460, "height": 280})
            if kind != "doughnut":
                obj.set_x_axis({"num_font": {"size": 9}})
                obj.set_y_axis({"num_font": {"size": 9}})
            dash.insert_chart(anchor, obj)
        chart("doughnut", "Status", "B21", "Composição do recorte")
        chart("column", "Contratos", "H21", "Contratos no recorte")
        chart("bar", "Setores", "B35", "Recorte nos 10 maiores setores da base", 10)
        chart("column", "Países", "H35", "Recorte nos 10 maiores países da base", 10)
        dash.merge_range("B49:M51", "Os gráficos de setor e país mantêm as dez maiores categorias da base completa para facilitar comparações. O recorte pode ter outras categorias: consulte a aba Analises para ver TODAS. Valores zero indicam ausência no recorte, não ausência na base.", note)
        dash.write_url("B53", "internal:'Base_Interativa_Vagas'!A1", string="Explorar os anúncios →")
        dash.write_url("H53", "internal:'Leia-me'!B2", string="Como usar e interpretar →")
        guide.merge_range("B2:M3", "Três formas de explorar a mesma base", title)
        instructions = [
            "1 / Dashboard: selecione País, Setor, Contrato, Status, Logo e Remoto. Todos remove o filtro. As seis condições são combinadas (E).",
            "2 / Base_Interativa_Vagas: tabela completa com textos, filtros nativos e subtotais das linhas visíveis. Seus filtros NÃO alteram o Dashboard, e vice-versa.",
            "3 / Analises: contagens e taxas de TODAS as categorias; responde às seis listas do Dashboard. Os gráficos mostram apenas as dez maiores categorias históricas de setor e país.",
            "Rótulos históricos, não previsões. Associação não prova fraude. A taxa usa o recorte como denominador; com Status selecionado, reflete apenas esse rótulo.",
            "Use Microsoft Excel com cálculo automático. Arquivo .xlsx sem macros e sem conexões externas. Outros visualizadores podem mostrar apenas os valores salvos; não se alega equivalência entre aplicativos.",
            "Os valores salvos correspondem à seleção inicial. Alterações nas listas recalculam no Excel; nenhum acesso à internet é necessário. Não há segmentações de Tabela Dinâmica ou macros.",
            "A base foi preservada do projeto original. Não inclua dados pessoais ou confidenciais em um repositório público. Atualizações da base exigem reconstruir a planilha com scripts/build_workbook.py.",
        ]
        for index, text in enumerate(instructions):
            row = 5 + index * 3
            guide.merge_range(row, 1, row + 1, 12, text, note)
        dash.activate()
        dash.set_first_sheet()
    return output


def build_data_workbook(output=ROOT / "Jobs_Data.xlsx", database=ROOT / "data/jobs_database.db"):
    """A separate, data-only Excel deliverable with no charts or formulas."""
    with closing(sqlite3.connect(f"file:{Path(database).resolve()}?mode=ro", uri=True)) as conn:
        df = pd.read_sql_query("SELECT * FROM vagas ORDER BY id_vaga", conn).fillna("")
    with xlsxwriter.Workbook(output, {"strings_to_formulas": False, "strings_to_urls": False}) as book:
        sheet = book.add_worksheet("Dados")
        sheet.freeze_panes(1, 2)
        sheet.set_column(0, len(df.columns) - 1, 22)
        sheet.set_column(1, 1, 42)
        sheet.add_table(0, 0, len(df), len(df.columns) - 1, {
            "name": "DadosVagas", "style": "Table Style Medium 4",
            "columns": [{"header": h} for h in df.columns], "data": df.values.tolist(),
        })
    return Path(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "Jobs_Database.xlsx")
    parser.add_argument("--data-output", type=Path, default=ROOT / "Jobs_Data.xlsx")
    args = parser.parse_args()
    print(build_workbook(args.output))
    print(build_data_workbook(args.data_output))
