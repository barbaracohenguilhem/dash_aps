"""Validate the deliverable and recalculate its actual formulas on small fixtures.

formulas is a Python calculation engine, not Microsoft Excel. Native Excel UI
verification remains a manual check; cached values alone are not calculation tests.
"""
from pathlib import Path
import sqlite3
import tempfile
import unittest

import formulas
import openpyxl
import pandas as pd

from scripts.build_workbook import FILTERS, ROOT, build_workbook, matching_rows


class WorkbookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.directory.name)
        cls.database = cls.folder / "fixture.db"
        with sqlite3.connect(ROOT / "data/jobs_database.db") as conn:
            template = pd.read_sql_query("SELECT * FROM vagas LIMIT 1", conn).iloc[0].to_dict()
        records = []
        for i, (country, sector, contract, logo, remote, fraud) in enumerate([
            ("US", "Tech", "Full-time", "Sim", "Não", 0),
            ("US", "Tech", "Full-time", "Não", "Sim", 1),
            ("GB", "Tech", "Part-time", "Não", "Sim", 0),
            ("US", "Oil & Energy", "Part-time", "Não", "Não", 1),
            ("GB", "Tech*?~", "Full-time", "Sim", "Não", 1),
            ("GB", "Tech*?~", "Part-time", "Não", "Sim", 0),
        ], start=1):
            records.append({**template, "id_vaga": i, "pais": country, "industry_clean": sector,
                            "employment_type_clean": contract, "tem_logo": logo, "remoto": remote,
                            "fraude_bin": fraud, "status_vaga": "Fraudulenta" if fraud else "Real",
                            "description": "=HYPERLINK(\"https://example.invalid\",\"literal data\")"})
        cls.df = pd.DataFrame(records)
        with sqlite3.connect(cls.database) as conn:
            cls.df.to_sql("vagas", conn, index=False, if_exists="replace")
        cls.file = build_workbook(cls.folder / "fixture.xlsx", cls.database)
        cls.model = formulas.ExcelModel().loads(str(cls.file)).finish()
        cls.prefix = "'[fixture.xlsx]DASHBOARD'!"

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_actual_formulas_recalculate_filters_combinations_and_empty_state(self):
        for selection in [{}, {"pais": "US"}, {"status_vaga": "Fraudulenta"},
                          {"industry_clean": "Tech*?~"}, {"tem_logo": "Não", "remoto": "Sim"},
                          {"pais": "US", "industry_clean": "Oil & Energy", "remoto": "Sim"},
                          {"pais": "US", "industry_clean": "Tech", "employment_type_clean": "Full-time",
                           "status_vaga": "Fraudulenta", "tem_logo": "Não", "remoto": "Sim"}]:
            with self.subTest(selection=selection):
                inputs = {self.prefix + cell: [[selection.get(column, "Todos")]] for _, column, cell in FILTERS}
                solution = self.model.calculate(inputs=inputs)
                expected = matching_rows(self.df, selection)
                count, fraud = len(expected), int(expected.fraude_bin.sum())
                for cell, value in [("B15", count), ("F15", fraud), ("J15", fraud / count if count else 0)]:
                    actual = solution[self.prefix + cell].value[0, 0]
                    self.assertAlmostEqual(float(actual), value, msg=str((selection, cell, actual)))
                cursor = 3
                for column in ["status_vaga", "industry_clean", "employment_type_clean", "pais"]:
                    values = self.df.groupby(column).size().sort_values(ascending=False, kind="stable").index
                    for value in values:
                        group = expected[expected[column] == value]
                        for letter, amount in [("B", len(group)), ("C", int(group.fraude_bin.sum()))]:
                            key = f"'[fixture.xlsx]ANALISES'!{letter}{cursor+1}"
                            self.assertEqual(float(solution[key].value[0, 0]), amount, (selection, key))
                        cursor += 1
                    cursor += 3

    def test_fixture_cache_matches_selection_and_text_is_not_a_formula(self):
        file = build_workbook(self.folder / "filtered.xlsx", self.database, {"pais": "US"})
        wb = openpyxl.load_workbook(file, data_only=True)
        self.assertEqual(wb["Dashboard"]["B15"].value, 3)
        self.assertEqual(wb["Dashboard"]["F15"].value, 2)
        wb.close()
        wb = openpyxl.load_workbook(file, data_only=False)
        self.assertEqual(wb["Base_Interativa_Vagas"]["S5"].data_type, "s")
        self.assertEqual(len(wb["Dashboard"]._charts), 4)
        self.assertEqual(len(wb["Dashboard"].data_validations.dataValidation), 6)
        wb.close()

    def test_delivered_workbook_matches_canonical_database_and_has_no_external_links(self):
        path = ROOT / "Jobs_Database.xlsx"
        with sqlite3.connect(ROOT / "data/jobs_database.db") as conn:
            total, fraud = conn.execute("SELECT COUNT(*), SUM(fraude_bin) FROM vagas").fetchone()
            ids = [r[0] for r in conn.execute("SELECT id_vaga FROM vagas ORDER BY id_vaga")]
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        self.assertEqual(wb["Dashboard"]["B15"].value, total)
        self.assertEqual(wb["Dashboard"]["F15"].value, fraud)
        self.assertAlmostEqual(wb["Dashboard"]["J15"].value, fraud / total)
        self.assertEqual([r[0] for r in wb["Base_Interativa_Vagas"].iter_rows(min_row=5, max_col=1, values_only=True)], ids)
        self.assertEqual(wb["Listas"].sheet_state, "hidden")
        self.assertEqual(wb.active.title, "Passo_a_passo")
        wb.close()
        from zipfile import ZipFile
        with ZipFile(path) as archive:
            self.assertFalse(any("externalLinks/" in n or n.endswith("vbaProject.bin") for n in archive.namelist()))

    def test_data_only_workbook_has_all_columns_and_no_formulas(self):
        wb = openpyxl.load_workbook(ROOT / "Jobs_Data.xlsx", read_only=True, data_only=False)
        self.assertEqual(wb.sheetnames, ["Dados"])
        sheet = wb["Dados"]
        rows = sheet.iter_rows()
        headers = [cell.value for cell in next(rows)]
        with sqlite3.connect(ROOT / "data/jobs_database.db") as conn:
            expected_headers = [row[1] for row in conn.execute("PRAGMA table_info(vagas)")]
            expected = conn.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
        self.assertEqual(headers, expected_headers)
        count = 0
        for row in rows:
            count += 1
            self.assertTrue(all(cell.data_type != "f" for cell in row))
        self.assertEqual(count, expected)
        wb.close()

    def test_step_by_step_formulas_recalculate_and_ignore_dashboard_filters(self):
        solution = self.model.calculate(inputs={self.prefix + "B6": [["US"]]})
        prefix = "'[fixture.xlsx]PASSO_A_PASSO'!"
        selected = self.df[(self.df.tem_logo == "Não") & (self.df.remoto == "Sim")]
        n, fraud = len(selected), int(selected.fraude_bin.sum())
        total, all_fraud = len(self.df), int(self.df.fraude_bin.sum())
        for cell, value in [("C7", total), ("C8", all_fraud), ("C9", all_fraud / total),
                            ("C12", n), ("C13", fraud), ("C14", fraud / n),
                            ("C15", 100 * (fraud / n - all_fraud / total))]:
            self.assertAlmostEqual(float(solution[prefix + cell].value[0, 0]), value)

    def test_delivered_step_by_step_caches_and_interpretation_spaces(self):
        wb = openpyxl.load_workbook(ROOT / "Jobs_Database.xlsx", read_only=True, data_only=True)
        sheet = wb["Passo_a_passo"]
        for cell, value in [("C7", 10000), ("C8", 453), ("C9", .0453),
                            ("C12", 120), ("C13", 26), ("C14", 26/120),
                            ("C15", 100 * (26/120 - 453/10000))]:
            self.assertAlmostEqual(sheet[cell].value, value)
        for cell in ["B19", "B23", "B27"]:
            self.assertIsNone(sheet[cell].value, "Personal interpretation must remain blank")
        wb.close()

    def test_invalid_filter_does_not_silently_create_a_misleading_workbook(self):
        with self.assertRaises(ValueError):
            build_workbook(self.folder / "invalid.xlsx", self.database, {"pais": "not-a-country"})
