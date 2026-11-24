"""Execute code in order instead of trusting saved notebook output."""
import contextlib
import io
import json
from pathlib import Path


def test_notebook_examples_and_outputs_are_reproducible(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    notebook = json.loads((root / "Analise.ipynb").read_text())
    namespace = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec("".join(cell["source"]), namespace)
        saved = "".join("".join(item.get("text", [])) for item in cell["outputs"] if item["output_type"] == "stream")
        assert output.getvalue() == saved
