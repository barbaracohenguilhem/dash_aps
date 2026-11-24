"""Add a transparent, editable analysis worksheet to the existing workbook."""


def add_analysis_sheet(book, df):
    sheet = book.add_worksheet("Passo_a_passo")
    sheet.hide_gridlines(2)
    sheet.freeze_panes(5, 1)
    sheet.set_column("A:A", 4)
    sheet.set_column("B:B", 43)
    sheet.set_column("C:C", 21)
    sheet.set_column("D:D", 90)
    title = book.add_format({"font_size": 22, "bold": True, "font_color": "#28211E"})
    head = book.add_format({"bold": True, "bg_color": "#EAE3D7", "text_wrap": True})
    text = book.add_format({"text_wrap": True, "valign": "top", "font_color": "#68594F"})
    number = book.add_format({"num_format": "#,##0", "bg_color": "#F4EFE5"})
    percent = book.add_format({"num_format": "0.00%", "bg_color": "#F4EFE5"})
    editable = book.add_format({"bg_color": "#FFF2CC", "border": 1, "text_wrap": True, "valign": "top"})
    sheet.merge_range("B2:D2", "Da pergunta à conclusão: refaça os cálculos", title)
    sheet.merge_range("B3:D4", "Material gerado com assistência de IA, não evidência de execução manual. As fórmulas abaixo usam a base completa e são independentes dos filtros do Dashboard. Abra com cálculo automático. Campos amarelos ficam para sua análise; não são respostas prontas.", text)
    sheet.write_row("B6", ["Etapa / pergunta", "Resultado calculado", "Como conferir e interpretar"], head)
    last = len(df) + 4
    ranges = {"id": f"'Base_Interativa_Vagas'!$A$5:$A${last}",
              "fraud": f"'Base_Interativa_Vagas'!$D$5:$D${last}",
              "logo": f"'Base_Interativa_Vagas'!$N$5:$N${last}",
              "remote": f"'Base_Interativa_Vagas'!$O$5:$O${last}"}
    total, fraud = len(df), int(df.fraude_bin.sum())
    selected = df[(df.tem_logo == "Não") & (df.remoto == "Sim")]
    count, labels = len(selected), int(selected.fraude_bin.sum())
    rows = [
        (7, "1 / Quantos anúncios entram na conta?", f'=COUNTA({ranges["id"]})', total, False,
         "Conte os IDs da coluna A. Unidade = linha/anúncio da base histórica, não pessoa nem anúncio único comprovado."),
        (8, "Quantos têm rótulo de fraude?", f'=SUM({ranges["fraud"]})', fraud, False,
         "A coluna D contém 0 ou 1. Sua soma conta rótulos de fraude, não previsões do aplicativo."),
        (9, "Qual é a taxa na base?", '=IFERROR(C8/C7,0)', fraud / total if total else 0, True,
         "Taxa = rótulos ÷ anúncios. Se o denominador for zero, a fórmula usa 0; interprete como sem observações."),
        (12, "2 / Sem logo E remoto: quantos anúncios?", f'=COUNTIFS({ranges["logo"]},"Não",{ranges["remote"]},"Sim")', count, False,
         "Combine as duas condições com E. No Dashboard, deixe os demais filtros em Todos, selecione Logo = Não e Remoto = Sim."),
        (13, "Quantos rótulos nesse recorte?", f'=SUMIFS({ranges["fraud"]},{ranges["logo"]},"Não",{ranges["remote"]},"Sim")', labels, False,
         "Use as mesmas condições no numerador e no denominador. Não filtre pelo Status para tentar estimar risco."),
        (14, "Qual é a taxa desse recorte?", '=IFERROR(C13/C12,0)', labels / count if count else 0, True,
         "O denominador é C12, não a base completa. Um grupo pequeno pode ter uma taxa alta sem concentrar a maioria dos casos."),
        (15, "Diferença para a base (p.p.)", '=(C14-C9)*100', 100 * ((labels / count if count else 0) - (fraud / total if total else 0)), False,
         "Subtraia as proporções e multiplique por 100. Diferença em pontos percentuais, não crescimento relativo nem causalidade."),
    ]
    decimals = book.add_format({"num_format": "0.00", "bg_color": "#F4EFE5"})
    for row, label, formula, cache, is_percent, explanation in rows:
        sheet.write(f"B{row}", label, text)
        sheet.write_formula(f"C{row}", formula, percent if is_percent else decimals if row == 15 else number, cache)
        sheet.write(f"D{row}", explanation, text)
        sheet.set_row(row - 1, 44)
    for row, prompt in [(18, "3 / Minha leitura: cite numerador, denominador e taxa."),
                        (22, "Qual explicação alternativa existe? O que estes dados NÃO permitem concluir?"),
                        (26, "Escolha outro recorte, anote os filtros e refaça a comparação.")]:
        sheet.merge_range(row - 1, 1, row - 1, 3, prompt, head)
        sheet.merge_range(row, 1, row + 2, 3, "", editable)
    sheet.write_url("B31", "internal:'Dashboard'!B6", string="Abrir filtros do Dashboard →")
    sheet.write_url("D31", "internal:'Base_Interativa_Vagas'!A4", string="Conferir as linhas da base →")
    sheet.merge_range("B33:D35", "Para refazer à mão: duplique esta aba, selecione C7:C15 e apague o conteúdo. Digite as fórmulas na barra de fórmulas (não cole como valores) e compare com a aba original. Nomes no arquivo: COUNTA, SUM, COUNTIFS, SUMIFS, IFERROR; no Excel pt-BR: CONT.VALORES, SOMA, CONT.SES, SOMASES, SEERRO. Ajuste o separador conforme seu Excel. Só relate como manual aquilo que você realmente executou.", text)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 2)
    sheet.print_area("B2:D35")
    return sheet
