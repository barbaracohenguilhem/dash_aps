import csv
import io
import json
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
        for path in ("/", "/_dash-layout", "/_dash-dependencies", "/assets/dashboard.css",
                     "/assets/accessibility.js", "/assets/story.js", "/assets/field-notes.svg", "/assets/fonts/jost-latin-wght-normal.woff2"):
            with client.get(path) as response:
                self.assertEqual(response.status_code, 200, path)

    def test_guided_questions_replace_previous_filters_and_keep_reset_semantics(self):
        for preset, field_id, value in [("preset-logo", "f-logo", "Não"),
                                         ("preset-remoto", "f-remoto", "Sim"),
                                         ("preset-fraude", "f-status", "Fraudulenta")]:
            result = app.preset_values(preset)
            reset = list(app.reset_filters(1))
            position = {"f-status": 0, "f-logo": 2, "f-remoto": 3}[field_id]
            self.assertEqual(result[position], value)
            reset[position] = value
            self.assertEqual(result, tuple(reset))
        self.assertIn("/Jobs_Database.xlsx?raw=true", app.WORKBOOK_URL)
        self.assertTrue(app.WORKBOOK_URL.startswith("https://github.com/barbaracohenguilhem/dash_aps/blob/"))

    def test_workspace_links_distinguish_data_dashboard_and_python(self):
        layout = app.server.test_client().get("/_dash-layout").get_json()

        def walk(node):
            if isinstance(node, dict):
                yield node
                yield from walk(node.get("props", {}).get("children", []))
            elif isinstance(node, list):
                for child in node:
                    yield from walk(child)

        nodes = list(walk(layout))
        props = [node["props"] for node in nodes]
        sidebar = next(item for item in props if item.get("className") == "topbar-nav")
        destinations = [item["props"].get("href") for item in sidebar["children"]]
        for target in ("#excel-dados", "#excel", "#python-excel", "#recorte"):
            self.assertIn(target, destinations)
        links = [item["href"] for item in props if "href" in item]
        self.assertIn(app.WORKBOOK_URL, links)
        self.assertIn(app.WORKBOOK_URL.replace("Jobs_Database.xlsx", "Jobs_Data.xlsx"), links)
        for path in ("Analise.ipynb", "scripts/build_workbook.py", "app.py"):
            self.assertIn(f"{app.SOURCE_URL}/{path}", links)
        main = next(item for item in props if item.get("className") == "main-content")
        order = [child["props"].get("id") for child in main["children"]]
        self.assertLess(order.index("kpi-row"), order.index("recorte"))

    def test_excel_is_presented_before_web_exploration(self):
        children = app.dash_app.layout.children[1].children
        ids = [getattr(child, "id", None) for child in children]
        self.assertLess(ids.index("excel"), ids.index("kpi-row"))
        self.assertLess(ids.index("como-analisar"), ids.index("recorte"))
        self.assertEqual(len([value for value in ids if value == "excel"]), 1)

    def test_document_declares_brazilian_portuguese(self):
        with app.server.test_client().get("/") as response:
            self.assertIn('<html lang="pt-BR">', response.get_data(as_text=True))

    def test_active_filter_chips_cover_every_dimension_and_remove_only_one(self):
        default = filters()
        self.assertIn("Base completa", app.active_filter_labels(*default)[0].children)
        values = filters(status="Fraudulenta", paises=["US"], setores=["Oil & Energy"],
                         contratos=["Full-time"], exps=["Entry level"], edus=["Bachelor's Degree"],
                         logo="Não", remoto="Sim", busca="engineer", tam_range=[100, 2000])
        descriptions = app.describe_selection(*values)
        self.assertEqual(len(descriptions), 5)
        self.assertTrue(all("País: US" in text and "Busca: engineer" in text for text in descriptions[1:]))
        chips = app.active_filter_labels(*values)[1].children
        self.assertEqual(len(chips), 10)
        self.assertEqual({chip.id["key"] for chip in chips}, set(app.FILTER_IDS))
        for chip in chips:
            cleared = app.clear_filter_values(chip.id["key"])
            for i, id in enumerate(app.FILTER_IDS):
                if id == chip.id["key"]:
                    self.assertEqual(cleared[i], app.FILTER_DEFAULTS[i])
                else:
                    self.assertIs(cleared[i], app.no_update)
        self.assertIsNone(app.clear_filter_values("f-setor")[-2])
        self.assertIsNone(app.clear_filter_values("f-pais")[-1])
        self.assertEqual(app.reset_filters(0, 1), app.reset_filters(1))

    def test_remove_filter_http_callback_ignores_mounts_and_keeps_other_filters(self):
        key, callback = next((key, callback) for key, callback in app.dash_app.callback_map.items()
                             if callback.get("callback") and callback["callback"].__name__ == "remove_filter")
        chip = {"type": "remove-filter", "key": "f-pais"}
        outputs = [{"id": out.component_id, "property": out.component_property} for out in callback["output"]]
        client = app.server.test_client()
        for clicks in (0, 1):
            response = client.post("/_dash-update-component", json={
                "output": key, "outputs": outputs,
                "inputs": [[{"id": chip, "property": "n_clicks", "value": clicks}]],
                "state": [], "changedPropIds": [json.dumps(chip, separators=(",", ":"), sort_keys=True) + ".n_clicks"],
            })
            if clicks:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["response"], {"f-pais": {"value": []}, "g-paises": {"clickData": None}})
            else:
                self.assertIn(response.status_code, (200, 204))
                if response.status_code == 200:
                    self.assertEqual(response.json["response"], {})

    def test_chart_connections_have_context_and_preserve_filters(self):
        for chart, (label, links) in app.CHART_CONNECTIONS.items():
            card = app.graph_card("test", "Title", "Description", chart)
            self.assertEqual(card.id, app.CHART_ANCHORS[chart])
            bridge = card.children[-1]
            self.assertEqual(bridge.children[0].children, label)
            self.assertEqual([link.href for link in bridge.children[1:]], [f"#{target}" for _, target in links])
            self.assertTrue(all(link.href.startswith("#") for link in bridge.children[1:]))

    def test_all_records_are_available_and_selection_has_stable_ids(self):
        context, _, _, _, _, _, records, selection, page, summary = app.update_dashboard(*filters())
        self.assertEqual(len(records), app.OPTS["total"])
        self.assertEqual(len({record["id"] for record in records}), len(records))
        self.assertEqual(records[-1]["id"], records[-1]["id_vaga"])
        self.assertIn("10.000", context)
        self.assertEqual(selection, [])
        self.assertEqual(page, 0)

    def test_rates_and_denominators_match_database(self):
        _, kpis, sectors, logo, _, _, records, _, _, _ = app.update_dashboard(*filters(paises=["US"]))
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
        self.assertTrue(all(len(item) == 2 for row in logo.data[0].customdata for item in row))

    def test_empty_and_status_filtered_results_are_clear(self):
        context, kpis, *rest = app.update_dashboard(*filters(busca="no-such-job-xyz-831"))
        self.assertTrue(context.startswith("0 de"))
        self.assertEqual(kpis[2].children[1].children, "—")
        self.assertEqual(rest[-4], [])
        context, kpis, *_ = app.update_dashboard(*filters(status="Fraudulenta"))
        self.assertIn("Status filtrado", context)
        self.assertEqual(kpis[2].children[1].children, "100.0%")
        self.assertIn("após o filtro", kpis[2].children[2].children)

    def test_chart_types_and_heatmap_denominators(self):
        result = app.update_dashboard(*filters())
        _, _, sectors, heatmap, donut, countries, records, _, _, summary = result
        self.assertEqual([chart.data[0].type for chart in (sectors, heatmap, donut, countries)],
                         ["scatter", "heatmap", "pie", "bar"])
        self.assertAlmostEqual(sum(donut.data[0].values), len(records))
        self.assertEqual(donut.data[0].hole, .64)
        self.assertEqual(heatmap.data[0].zmin, 0)
        self.assertEqual(heatmap.data[0].zmax, 100)
        with sqlite3.connect(app.DB_PATH) as conn:
            for i, remote in enumerate(["Não", "Sim"]):
                for j, logo in enumerate(["Sim", "Não"]):
                    total, frauds = conn.execute(
                        "SELECT COUNT(*), SUM(fraude_bin) FROM vagas WHERE tem_logo = ? AND remoto = ?",
                        (logo, remote),
                    ).fetchone()
                    self.assertEqual(list(heatmap.data[0].customdata[i][j]), [frauds, total])
                    self.assertAlmostEqual(heatmap.data[0].z[i][j], 100 * frauds / total)
        self.assertEqual(len(summary), 3)

    def test_sector_ranking_minimum_and_other_charts_are_independent(self):
        result = app.update_dashboard(*filters(), sector_order="taxa", sector_min=100)
        _, _, sectors, _, donut, _, records, _, _, _ = result
        self.assertLessEqual(len(sectors.data[0].x), 10)
        self.assertEqual(sectors.layout.xaxis.range[0], 0)
        self.assertFalse(sectors.data[0].cliponaxis)
        self.assertEqual(list(sectors.data[0].x), sorted(sectors.data[0].x))
        self.assertTrue(all(row[1] >= 100 for row in sectors.data[0].customdata))
        self.assertEqual(len(records), app.OPTS["total"])
        self.assertEqual(sum(donut.data[0].values), app.OPTS["total"])
        empty = app.update_dashboard(*filters(busca="Marketing Intern"), sector_min=500)
        self.assertTrue(empty[6])
        self.assertFalse(empty[2].data)
        self.assertIn("Reduza", empty[2].layout.annotations[0].text)

    def test_filtered_heatmap_marks_missing_groups_without_zero_rate(self):
        result = app.update_dashboard(*filters(logo="Sim", remoto="Sim"))
        heatmap = result[3].data[0]
        self.assertIsNone(heatmap.z[0][0])
        self.assertIsNone(heatmap.z[0][1])
        self.assertIsNone(heatmap.z[1][1])
        self.assertGreater(heatmap.customdata[1][0][1], 0)
        self.assertFalse(heatmap.hoverongaps)
        status_result = app.update_dashboard(*filters(status="Fraudulenta"))
        self.assertTrue(all(value == 100 for row in status_result[3].data[0].z for value in row if value is not None))
        self.assertIn("status está ativo", status_result[-1][0].children[2].children)

    def test_chart_click_filters_and_reset(self):
        sector, country = app.chart_filter_selection("g-setores", {"points": [{"y": "Oil & Energy"}]})
        self.assertEqual(sector, ["Oil & Energy"])
        self.assertIs(country, app.no_update)
        result = app.update_dashboard(*filters(setores=sector))
        self.assertTrue(result[6])
        self.assertTrue(all(row["industry_clean"] == "Oil & Energy" for row in result[6]))
        sector, country = app.chart_filter_selection("g-paises", {"points": [{"x": "NZ"}]})
        self.assertIs(sector, app.no_update)
        self.assertEqual(country, ["NZ"])
        for payload in (None, {"points": []}, {"points": [{"x": "not-a-country"}]}):
            self.assertEqual(app.chart_filter_selection("g-paises", payload), (app.no_update, app.no_update))
        self.assertEqual(app.reset_filters(1)[-2:], (None, None))

    def test_chart_click_http_callback_applies_only_triggered_dimension(self):
        key = next(key for key, callback in app.dash_app.callback_map.items()
                   if callback.get("callback") and callback["callback"].__name__ == "filter_from_chart")
        client = app.server.test_client()
        for chart, payload, expected in (
            ("g-setores", {"points": [{"y": "Oil & Energy"}]}, {"f-setor": {"value": ["Oil & Energy"]}}),
            ("g-paises", {"points": [{"x": "NZ"}]}, {"f-pais": {"value": ["NZ"]}}),
        ):
            response = client.post("/_dash-update-component", json={
                "output": key, "outputs": [{"id": "f-setor", "property": "value"}, {"id": "f-pais", "property": "value"}],
                "inputs": [{"id": name, "property": "clickData", "value": payload if name == chart else None}
                           for name in ["g-setores", "g-paises"]],
                "state": [], "changedPropIds": [f"{chart}.clickData"],
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["response"], expected)

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
        self.assertEqual(app.reset_filters(1)[-5:], ("", "total", 30, None, None))


if __name__ == "__main__":
    unittest.main()
