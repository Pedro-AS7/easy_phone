import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from lmphone import treino


class TreinoTest(unittest.TestCase):
    def test_status_counts_without_showing_content(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(treino, "DIR", os.path.join(folder, "real")):
            treino.record("s1", "pedido", texto="Mande uma mensagem para Joana Prado", gemma=None)
            for text in ("Joana Prado", "Configurações", "Joana Prado"):
                treino.record("s1", "trecho", app="com.example.chat", texto=text)
            treino.record("s1", "escolha", app="com.example.chat", passo={"acao": "tap", "alvo": ["Ajustes"]},
                          rotulos=["Configurações"], escolhido="Configurações", por="IA local", efeito="conferido")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                treino.status()
        text = out.getvalue()
        self.assertIn("1 tarefas · 1 pedidos · 3 trechos (2 distintos) · 1 escolhas", text)
        self.assertIn("3  com.example.chat", text)
        self.assertIn("IA local (conferido 1)", text)
        for private in ("Joana", "Configurações", "Ajustes", "Mande"):
            self.assertNotIn(private, text)

    @unittest.skipIf(os.name == "nt", "o Windows não tem os bits de modo do Unix")
    def test_files_are_private(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(treino, "DIR", os.path.join(folder, "real")):
            treino.record("s1", "trecho", app=None, texto="x")
            (name,) = os.listdir(treino.DIR)
            self.assertEqual(os.stat(os.path.join(treino.DIR, name)).st_mode & 0o777, 0o600)
