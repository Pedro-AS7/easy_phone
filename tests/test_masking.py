import json
import os
import tempfile
import unittest

from lmphone.masking import Masker, Session, Vault, passwords


class MaskingTest(unittest.TestCase):
    def setUp(self):
        self.m = Masker(Vault())
        self.m.add_name("Gabriel Ferreira de Souza")
        self.m.add_name("Casa")
        self.m.add_literal("gabriel.fps")
        self.m.add_phone("+55 (61) 99876-5432")

    def roundtrip(self, text):
        masked = self.m.mask(text)
        self.assertEqual(self.m.unmask(masked), text)
        return masked

    def test_names(self):
        masked = self.roundtrip("Conversa com Gabriel Ferreira e com GABRIEL.")
        self.assertNotIn("Gabriel", masked)
        self.assertNotIn("Ferreira", masked)
        self.assertNotIn("GABRIEL", masked)
        self.assertEqual(masked, self.m.mask("Conversa com Gabriel Ferreira e com GABRIEL."))

    def test_stoplist_and_lowercase_untouched(self):
        self.m.add_name("Bruno Mercado Livre")
        text = "Vá para Casa de carro; livre em minúsculas fica."
        self.assertEqual(self.m.mask(text), text)

    def test_email_handle_cpf_card(self):
        masked = self.roundtrip(
            "gabriel@empresa.com.br, @gabriel.fps, CPF 123.456.789-09, cartão 4111 1111 1111 1111"
        )
        for secret in ("gabriel@empresa", "gabriel.fps", "123.456.789-09", "4111 1111 1111 1111"):
            self.assertNotIn(secret, masked)
        self.assertIn("@exemplo.com", masked)

    def test_phone_formats_share_one_fake(self):
        a = self.roundtrip("Ligue para +55 (61) 99876-5432")
        b = self.roundtrip("Ligue para 61998765432")
        c = self.roundtrip("Ligue para 99876-5432")
        self.assertNotIn("5432", a)
        digits = lambda s: "".join(ch for ch in s if ch.isdigit())[-8:]
        self.assertEqual(digits(a), digits(b))
        self.assertEqual(digits(a), digits(c))

    def test_ui_tree_numbers_untouched(self):
        text = '5. Button: "Navigate up" - (0,117,169,297)\n12 × 7 = 84; R$ 1.234,56; 2026-10-11 21:33'
        self.assertEqual(self.m.mask(text), text)

    def test_unmask_typed_text(self):
        masked = self.m.mask("Mande oi para Gabriel")
        fake = masked.rsplit(" ", 1)[1]
        self.assertEqual(self.m.unmask(f'<parameter name="text">Oi, {fake}!</parameter>'),
                         '<parameter name="text">Oi, Gabriel!</parameter>')

    def test_walk(self):
        body = {"messages": [{"role": "user", "content": [{"type": "text", "text": "Sou Gabriel"}]}], "n": 1}
        masked = self.m.walk(body, self.m.mask)
        self.assertNotIn("Gabriel", str(masked))
        self.assertEqual(self.m.walk(masked, self.m.unmask), body)

    def test_fakes_change_between_sessions(self):
        text = "Ligue para +55 (61) 99876-5432"
        other = Masker(self.m.vault, session=Session(self.m.vault))
        self.assertNotEqual(self.m.mask(text), other.mask(text))
        self.assertEqual(other.unmask(other.mask(text)), text)

    def test_vault_file_has_no_fakes_nor_screen_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Vault(os.path.join(tmp, "vault.json"))
            m = Masker(vault)
            m.add_name("Gabriel Ferreira")
            masked = m.mask("Gabriel falou com visto.na.tela@exemplo.org, CPF 123.456.789-09")
            vault.save()
            with open(vault.path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved, {"name": ["ferreira", "gabriel"], "email": [], "literal": [], "phone": []})
            self.assertEqual(Vault(vault.path).reals["name"], {"gabriel", "ferreira"})
            self.assertNotIn(masked.split()[0].casefold(), json.dumps(saved))


if __name__ == "__main__":
    unittest.main()


class PasswordTest(unittest.TestCase):
    def test_password_said_in_the_request(self):
        self.assertEqual(passwords("Coloca o wifi na rede Teste 2g, a senha é abc12345"), ["abc12345"])
        self.assertEqual(passwords("a senha do wifi eh minhasenha123."), ["minhasenha123"])
        self.assertEqual(passwords("password: Xy9z"), ["Xy9z"])

    def test_no_password_when_only_the_word(self):
        self.assertEqual(passwords("troca a senha do wifi"), [])
        self.assertEqual(passwords("qual a senha do wifi?"), [])

    def test_masked_out_and_back(self):
        m = Masker(Vault())
        for value in passwords("a senha é abc12345"):
            m.session.protect_literal(value)
        sent = m.mask("Connect with the password abc12345")
        self.assertNotIn("abc12345", sent)
        self.assertEqual(m.unmask(sent), "Connect with the password abc12345")
