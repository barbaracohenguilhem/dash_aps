#!/usr/bin/env python3
"""Gera o banco SQLite (data/jobs_database.db) e a planilha Excel interativa (Jobs_Database.xlsx)."""

import os
import sqlite3
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    csv_path = os.path.join(ROOT_DIR, "data", "jobs_cleaned.csv")
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    # Enriquecer colunas auxiliares para filtros interativos
    df.insert(0, "id_vaga", range(1, len(df) + 1))
    df["pais"] = df["location"].apply(lambda x: x.split(",")[0].strip() if x.strip() else "Não Informado").replace("", "Não Informado")
    df["employment_type_clean"] = df["employment_type"].replace("", "Não Informado")
    df["experience_clean"] = df["required_experience"].replace("", "Não Informado")
    df["education_clean"] = df["required_education"].replace("", "Não Informado")
    df["industry_clean"] = df["industry"].replace("", "Não Informado")
    df["function_clean"] = df["function"].replace("", "Não Informado")
    df["fraude_bin"] = (df["fraudulent"] == "t").astype(int)
    df["status_vaga"] = df["fraudulent"].map({"t": "Fraudulenta", "f": "Real"}).fillna("Real")
    df["tem_logo"] = df["has_company_logo"].map({"t": "Sim", "f": "Não"}).fillna("Não")
    df["remoto"] = df["telecommuting"].map({"t": "Sim", "f": "Não"}).fillna("Não")
    df["tem_perguntas"] = df["has_questions"].map({"t": "Sim", "f": "Não"}).fillna("Não")
    df["tamanho_descricao"] = df["description"].str.len()

    # 1. Atualizar banco SQLite (data/jobs_database.db) com índices rápidos para o Dash
    db_path = os.path.join(ROOT_DIR, "data", "jobs_database.db")
    conn = sqlite3.connect(db_path)
    df.to_sql("vagas", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vagas_status ON vagas(status_vaga)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vagas_pais ON vagas(pais)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vagas_ind ON vagas(industry_clean)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vagas_emp ON vagas(employment_type_clean)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vagas_exp ON vagas(experience_clean)")
    conn.commit()
    conn.close()
    print(f"[OK] SQLite atualizado: {db_path} ({len(df)} registros).")

    # 2. Criar Workbook Excel com Painel Dinâmico + Base Filtrável (SUBTOTAL ao vivo)
    wb = Workbook()

    header_fill = PatternFill("solid", fgColor="0F172A")
    sub_fill = PatternFill("solid", fgColor="1E293B")
    kpi_fill = PatternFill("solid", fgColor="EFF6FF")
    zebra_fill = PatternFill("solid", fgColor="F8FAFC")
    fraud_fill = PatternFill("solid", fgColor="FEF2F2")

    title_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    reg_font = Font(name="Calibri", size=11, color="1E293B")

    thin = Side(border_style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # --- ABA 1: Base_Interativa_Vagas (com barra SUBTOTAL que muda ao filtrar + AutoFiltro) ---
    ws_db = wb.active
    ws_db.title = "Base_Interativa_Vagas"
    ws_db.freeze_panes = "A5"

    export_cols = [
        "id_vaga", "title", "status_vaga", "fraude_bin", "pais", "location",
        "industry_clean", "employment_type_clean", "experience_clean", "education_clean",
        "function_clean", "department", "salary_range", "tem_logo", "remoto",
        "tem_perguntas", "tamanho_descricao", "company_profile", "description",
        "requirements", "benefits",
    ]
    nice_headers = [
        "ID", "Cargo (Title)", "Status", "Flag_Fraude", "País", "Localização",
        "Indústria / Setor", "Tipo Contrato", "Experiência", "Escolaridade",
        "Função", "Departamento", "Faixa Salarial", "Tem Logo?", "Remoto?",
        "Tem Perguntas?", "Tam. Descrição", "Perfil da Empresa", "Descrição Limpa",
        "Requisitos Limpos", "Benefícios Limpos",
    ]

    last_row = len(df) + 4  # cabeçalho na linha 4, dados de 5 até 10004

    # Barra superior interativa nas linhas 1-2 que recalcula sozinha quando o usuário filtra qualquer coluna no Excel!
    ws_db.merge_cells("A1:D1")
    ws_db["A1"] = "FILTRO INTERATIVO AO VIVO (use as setas na linha 4 para filtrar):"
    ws_db["A1"].font = header_font
    ws_db["A1"].fill = header_fill
    ws_db["A1"].alignment = Alignment(horizontal="left", vertical="center")

    ws_db["E1"] = "Vagas Visíveis:"
    ws_db["F1"] = f"=SUBTOTAL(103, A5:A{last_row})"
    ws_db["G1"] = "Fraudulentas no Filtro:"
    ws_db["H1"] = f"=SUBTOTAL(109, D5:D{last_row})"
    ws_db["I1"] = "Taxa Fraude Filtro:"
    ws_db["J1"] = "=IF(F1>0, H1/F1, 0)"
    ws_db["J1"].number_format = "0.00%"
    ws_db["K1"] = "Média Tam. Descrição:"
    ws_db["L1"] = f"=SUBTOTAL(101, Q5:Q{last_row})"
    ws_db["L1"].number_format = "#,##0"

    for col_let in ["E", "F", "G", "H", "I", "J", "K", "L"]:
        cell = ws_db[f"{col_let}1"]
        cell.fill = kpi_fill if col_let in ["F", "H", "J", "L"] else sub_fill
        cell.font = bold_font if col_let in ["F", "H", "J", "L"] else header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_db.row_dimensions[1].height = 26
    ws_db.row_dimensions[4].height = 24

    # Escrever cabeçalhos na linha 4
    for c_idx, h_name in enumerate(nice_headers, start=1):
        ws_db.cell(row=4, column=c_idx, value=h_name)

    # Escrever as 10.000 linhas a partir da linha 5
    for r_offset, row_tuple in enumerate(df[export_cols].itertuples(index=False, name=None), start=5):
        for c_idx, val in enumerate(row_tuple, start=1):
            ws_db.cell(row=r_offset, column=c_idx, value=val)

    last_col_letter = get_column_letter(len(nice_headers))
    tab = Table(displayName="TabelaVagasInterativa", ref=f"A4:{last_col_letter}{last_row}")
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws_db.add_table(tab)

    col_widths = [8, 34, 14, 13, 12, 22, 26, 18, 18, 22, 20, 16, 16, 12, 12, 15, 16, 42, 55, 45, 40]
    for idx, w in enumerate(col_widths, start=1):
        ws_db.column_dimensions[get_column_letter(idx)].width = w

    # --- ABA 2: Resumo_Dashboard (com Tabelas + Gráficos Nativos do Excel) ---
    ws_kpi = wb.create_sheet(title="Resumo_Dashboard")
    ws_kpi.merge_cells("A1:E1")
    ws_kpi["A1"] = "PAINEL RESUMO — VAGAS REAIS VS FRAUDULENTAS (PARTES 1 A 5)"
    ws_kpi["A1"].font = title_font
    ws_kpi["A1"].fill = header_fill
    ws_kpi["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws_kpi.row_dimensions[1].height = 30

    total = len(df)
    total_fraude = int(df["fraude_bin"].sum())
    total_real = total - total_fraude

    ws_kpi["A3"] = "Status da Vaga"
    ws_kpi["B3"] = "Quantidade"
    ws_kpi["A3"].fill = ws_kpi["B3"].fill = sub_fill
    ws_kpi["A3"].font = ws_kpi["B3"].font = header_font
    ws_kpi["A4"] = "Real"
    ws_kpi["B4"] = total_real
    ws_kpi["A5"] = "Fraudulenta"
    ws_kpi["B5"] = total_fraude
    for r in (3, 4, 5):
        ws_kpi[f"A{r}"].border = ws_kpi[f"B{r}"].border = border
    ws_kpi["A5"].fill = ws_kpi["B5"].fill = fraud_fill

    # Top 10 Setores
    ind_df = (
        df.groupby("industry_clean", as_index=False)
        .agg(Total=("id_vaga", "count"), Fraudulentas=("fraude_bin", "sum"))
        .sort_values("Total", ascending=False)
        .head(10)
    )
    ind_df["Taxa_%"] = (ind_df["Fraudulentas"] / ind_df["Total"] * 100).round(2)

    start_r = 8
    for col_i, h_text in enumerate(["Top 10 Setores", "Total Vagas", "Fraudulentas", "Taxa Fraude (%)"], start=1):
        cell = ws_kpi.cell(row=start_r, column=col_i, value=h_text)
        cell.fill = sub_fill
        cell.font = header_font
        cell.border = border

    for offset, rdata in enumerate(ind_df.itertuples(index=False), start=1):
        r = start_r + offset
        for col_i, val in enumerate([rdata.industry_clean, int(rdata.Total), int(rdata.Fraudulentas), float(rdata._3)], start=1):
            cell = ws_kpi.cell(row=r, column=col_i, value=val)
            cell.font = reg_font
            cell.border = border
            if offset % 2 == 0:
                cell.fill = zebra_fill

    # Tipo de Contrato
    emp_df = (
        df.groupby("employment_type_clean", as_index=False)
        .agg(Total=("id_vaga", "count"), Fraudulentas=("fraude_bin", "sum"))
        .sort_values("Total", ascending=False)
    )
    emp_df["Taxa_%"] = (emp_df["Fraudulentas"] / emp_df["Total"] * 100).round(2)

    start_r2 = 21
    for col_i, h_text in enumerate(["Tipo de Contrato", "Total Vagas", "Fraudulentas", "Taxa Fraude (%)"], start=1):
        cell = ws_kpi.cell(row=start_r2, column=col_i, value=h_text)
        cell.fill = sub_fill
        cell.font = header_font
        cell.border = border

    for offset, rdata in enumerate(emp_df.itertuples(index=False), start=1):
        r = start_r2 + offset
        for col_i, val in enumerate([rdata.employment_type_clean, int(rdata.Total), int(rdata.Fraudulentas), float(rdata._3)], start=1):
            cell = ws_kpi.cell(row=r, column=col_i, value=val)
            cell.font = reg_font
            cell.border = border
            if offset % 2 == 0:
                cell.fill = zebra_fill

    # Gráfico de Pizza Nativo (Reais vs Fraudulentas)
    pie = PieChart()
    pie.title = "Proporção Vagas Reais vs Fraudulentas"
    labels = Reference(ws_kpi, min_col=1, min_row=4, max_row=5)
    data = Reference(ws_kpi, min_col=2, min_row=3, max_row=5)
    pie.add_data(data, titles_from_data=True)
    pie.set_categories(labels)
    pie.height = 10
    pie.width = 14
    ws_kpi.add_chart(pie, "F3")

    # Gráfico de Barras Nativo (Top 10 Setores)
    bar = BarChart()
    bar.type = "col"
    bar.style = 10
    bar.title = "Top 10 Setores (Total vs Fraudulentas)"
    bar.y_axis.title = "Vagas"
    data_bar = Reference(ws_kpi, min_col=2, min_row=8, max_col=3, max_row=18)
    cats_bar = Reference(ws_kpi, min_col=1, min_row=9, max_row=18)
    bar.add_data(data_bar, titles_from_data=True)
    bar.set_categories(cats_bar)
    bar.height = 12
    bar.width = 18
    ws_kpi.add_chart(bar, "F20")

    ws_kpi.column_dimensions["A"].width = 38
    ws_kpi.column_dimensions["B"].width = 16
    ws_kpi.column_dimensions["C"].width = 16
    ws_kpi.column_dimensions["D"].width = 18

    xlsx_out = os.path.join(ROOT_DIR, "Jobs_Database.xlsx")
    wb.save(xlsx_out)
    print(f"[OK] {xlsx_out} gerado com filtros e gráficos!")


if __name__ == "__main__":
    main()
