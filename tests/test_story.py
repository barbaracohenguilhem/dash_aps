"""Narrative charts must reconcile to source data, not just render successfully."""
import sqlite3
import unittest

import app
from test_dashboard import filters


class StoryTest(unittest.TestCase):
    def test_flow_conserves_population_in_both_transitions_and_each_middle_node(self):
        for selection in [{}, {"logo": "Não"}, {"paises": ["US"], "remoto": "Sim"}, {"status": "Fraudulenta"}]:
            with self.subTest(selection=selection):
                df = app.query_vagas(*filters(**selection))
                chart, table, reading, *_ = app.update_story(*filters(**selection))
                links = chart.data[0].link
                first = sum(v for s, v in zip(links.source, links.value) if s in (0, 1))
                second = sum(v for s, v in zip(links.source, links.value) if s in (2, 3))
                self.assertEqual(first, len(df))
                self.assertEqual(second, len(df))
                for middle in (2, 3):
                    incoming = sum(v for t, v in zip(links.target, links.value) if t == middle)
                    outgoing = sum(v for s, v in zip(links.source, links.value) if s == middle)
                    self.assertEqual(incoming, outgoing)
                self.assertEqual(sum(v for t, v in zip(links.target, links.value) if t == 5), int(df.fraude_bin.sum()))
                self.assertIn(app.format_count(len(df)), reading)
                self.assertEqual(len(table.children[-1].children), len(links.value))

    def test_text_ecdfs_reach_100_and_match_exact_medians(self):
        df = app.query_vagas(*filters())
        _, _, _, fig, reading, _ = app.update_story(*filters())
        for trace in fig.data:
            label = trace.name.split(" · ")[0]
            values = df.loc[df.status_vaga == label, "tamanho_descricao"]
            self.assertEqual(trace.y[-1], 100)
            self.assertEqual(trace.y[0], 0)
            self.assertEqual(list(trace.x), sorted(trace.x))
            self.assertEqual(list(trace.y), sorted(trace.y))
            self.assertIn(app.format_count(round(float(values.median()))), reading)
            for x, y in zip(trace.x[1:], trace.y[1:]):
                self.assertAlmostEqual(y, 100 * (values <= x).sum() / len(values))
        filtered = app.update_story(*filters(status="Fraudulenta"))
        self.assertEqual(len(filtered[3].data), 1)
        self.assertIn("Real: sem anúncios", filtered[4])

    def test_casebook_uses_first_id_per_available_label_with_unmodified_text(self):
        for selection in [{}, {"status": "Fraudulenta"}, {"paises": ["NZ"]}]:
            df = app.query_vagas(*filters(**selection))
            cards = app.casebook(df)
            ids = sorted(int(group.id_vaga.min()) for _, group in df.groupby("status_vaga"))
            self.assertEqual(len(cards), len(ids))
            with sqlite3.connect(app.DB_PATH) as conn:
                for card in cards:
                    ident = int(card.children[0].children[0].children.split("/")[1])
                    self.assertIn(ident, ids)
                    title, description = conn.execute("SELECT title, description FROM vagas WHERE id_vaga=?", (ident,)).fetchone()
                    self.assertEqual(card.children[1].children, title)
                    self.assertEqual(card.children[-1].children[1].children[1].children, description or "Não informado.")

    def test_empty_story_has_no_fabricated_visuals_or_records(self):
        flow, table, reading, texts, explanation, cards = app.update_story(*filters(busca="absent-xyz-9761"))
        self.assertFalse(flow.data)
        self.assertFalse(texts.data)
        self.assertEqual(table, [])
        self.assertIn("Nenhum", cards.children)
        self.assertIn("Nenhum", reading)
        self.assertIn("Não há", explanation)

    def test_story_http_callback_renders_all_six_outputs(self):
        key, callback = next((key, callback) for key, callback in app.dash_app.callback_map.items()
                             if callback.get("callback") and callback["callback"].__name__ == "update_story")
        response = app.server.test_client().post("/_dash-update-component", json={
            "output": key,
            "outputs": [{"id": out.component_id, "property": out.component_property} for out in callback["output"]],
            "inputs": [{"id": name, "property": "value", "value": value} for name, value in zip(app.FILTER_IDS, filters())],
            "state": [], "changedPropIds": ["f-status.value"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json["response"]), {"g-percurso", "flow-table", "flow-reading", "g-textos", "text-reading", "casebook-records"})
