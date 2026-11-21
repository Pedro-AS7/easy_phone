import json
import os
import unittest

from tools.app import cerebro


class ExportTest(unittest.TestCase):
    """O cérebro em Kotlin lê os prompts, as listas e as expressões regulares do Python pelo cerebro.json: ele tem de
    estar igual ao que o Python exporta agora."""

    def test_export_is_fresh(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), cerebro.OUT), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved, cerebro.build(), "cerebro.json velho: rode .venv/Scripts/python.exe -m tools.app.cerebro exportar")

    def test_no_environment(self):
        text = json.dumps(cerebro.build())
        key = os.environ.get("OPENROUTER_API_KEY")
        if key:
            self.assertNotIn(key, text)
        self.assertNotIn("API_KEY", text)


if __name__ == "__main__":
    unittest.main()
