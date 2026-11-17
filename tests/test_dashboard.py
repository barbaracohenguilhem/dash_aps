import csv
import io
import sqlite3
import unittest

import app


def filters(**overrides):
    values = {
        "status": "Todas", "paises": [], "setores": [], "contratos": [], "exps": [], "edus": [],
        "logo": "Todos", "remoto": "Todos", "busca": "", "tam_range": [0, app.MAX_DESC_LEN],
    }
    values.update(overrides)
    return tuple(values.values())


class DashboardTest(unittest.TestCase):
    def test_layout_contains_callback_targets_and_navigation_destinations(self):
        def components(node):
            yield node
            children = getattr(node, "children", [])
            if not isinstance(children, (list, tuple)):
                children = [children]
            for child in children:
                yield from components(child)

        nodes = list(components(app.dash_app.layout))
        ids = [node.id for node in nodes if getattr(node, "id", None)]
        self.assertEqual(len(ids), len(set(ids)))
        for callback in app.dash_app.callback_map.values():
            outputs = callback["output"]
            if not isinstance(outputs, list):
                outputs = [outputs]
            for output in outputs:
                self.assertIn(output.component_id, ids)
        for node in nodes:
            href = getattr(node, "href", "")
            if href.startswith("#"):
                self.assertIn(href[1:], ids)
        self.assertIs(app.server, app.dash_app.server)
        self.assertIs(app.app, app.server)
        client = app.server.test_client()
        for path in ("/", "/_dash-layout", "/_dash-dependencies", "/assets/dashboard.css"):
            with client.get(path) as response:
                self.assertEqual(response.status_code, 200, path)

    def test_all_records_are_available_and_selection_has_stable_ids(self):
        context, _, _, _, _, _, records, selection, page = app.update_dashboard(*filters())
        self.assertEqual(len(records), app.OPTS["total"])
        self.assertEqual(len({record["id"] for record in records}), len(records))
        self.assertEqual(records[-1]["id"], records[-1]["id_vaga"])
        self.assertIn("10.000", context)
        self.assertEqual(selection, [])
        self.assertEqual(page, 0)

    def test_rates_and_denominators_match_database(self):
        _, kpis, sectors, logo, _, _, records, _, _ = app.update_dashboard(*filters(paises=["US"]))
        with sqlite3.connect(app.DB_PATH) as conn:
            total, frauds = conn.execute(
                "SELECT COUNT(*), SUM(fraude_bin) FROM vagas WHERE pais = ?", ("US",)
            ).fetchone()
            sector_total, sector_frauds = conn.execute(
                "SELECT COUNT(*), SUM(fraude_bin) FROM vagas WHERE pais = ? AND industry_clean = ?",
                ("US", "Oil & Energy"),
            ).fetchone()
        self.assertEqual(len(records), total)
        self.assertEqual(kpis[1].children[1].children, app.format_count(frauds))
        sector = sectors.data[0]
        index = list(sector.y).index("Oil & Energy")
        self.assertAlmostEqual(sector.x[index], 100 * sector_frauds / sector_total)
        self.assertEqual(list(sector.customdata[index]), [sector_frauds, sector_total])
        self.assertTrue(all(len(item) == 2 for trace in logo.data for item in trace.customdata))

    def test_empty_and_status_filtered_results_are_clear(self):
        context, kpis, *rest = app.update_dashboard(*filters(busca="no-such-job-xyz-831"))
        self.assertTrue(context.startswith("0 de"))
        self.assertEqual(kpis[2].children[1].children, "—")
        self.assertEqual(rest[-3], [])
        context, kpis, *_ = app.update_dashboard(*filters(status="Fraudulenta"))
        self.assertIn("Status filtrado", context)
        self.assertEqual(kpis[2].children[1].children, "100.0%")
        self.assertIn("após o filtro", kpis[2].children[2].children)

    def test_details_export_and_reset(self):
        detail = app.mostrar_detalhe_vaga([2])
        self.assertIn("#2", detail.children[0].children[0].children[1].children)
        self.assertIn("Selecione", app.mostrar_detalhe_vaga([]).children[0].children)
        args = filters(paises=["NZ"])
        expected = app.query_vagas(*args, include_details=True)
        client = app.server.test_client()
        parts = []
        offset = 0
        while True:
            response = client.post("/api/export", json={"filters": args, "offset": offset})
            self.assertEqual(response.status_code, 200)
            parts.append(response.get_data(as_text=True))
            if response.headers["X-Export-Has-More"] == "0":
                break
            offset += app.EXPORT_PAGE_SIZE
        self.assertGreater(offset, 0)
        rows = list(csv.DictReader(io.StringIO("".join(parts))))
        self.assertEqual(len(rows), len(expected))
        self.assertEqual([int(row["id_vaga"]) for row in rows], expected["id_vaga"].tolist())
        self.assertIn("description", rows[0])
        self.assertIn("company_profile", rows[0])
        self.assertEqual(client.post("/api/export", json={"filters": [], "offset": -1}).status_code, 400)
        empty = client.post("/api/export", json={"filters": filters(busca="no-such-job-xyz-831"), "offset": 0})
        self.assertEqual(empty.headers["X-Export-Has-More"], "0")
        self.assertEqual(list(csv.DictReader(io.StringIO(empty.get_data(as_text=True)))), [])
        self.assertEqual(app.reset_filters(1)[-1], "")


if __name__ == "__main__":
    unittest.main()
