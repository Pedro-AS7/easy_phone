"""As regras de `lmphone/masking.py` que valem sem a IA local (2026-11-12): senhas, documentos, logradouros, nomes pela
forma do texto, falsos que não se confundem com palavras reais. Casos fictícios em tests/regras_cases.py."""

import re
import unittest

from lmphone import masking, nomes
from lmphone.masking import Masker, Session, Vault, passwords

from tests import regras_cases
from tests.base import mascaramento as base


def masker():
    m = Masker(Vault())
    for name in regras_cases.CONTATOS:
        m.add_name(name)
    return m


class RulesTest(unittest.TestCase):
    def test_cases(self):
        for case in regras_cases.CASOS:
            with self.subTest(case["entrada"]):
                m, text = masker(), case["entrada"]
                found = passwords(text)
                if case["senhas"] is not None:
                    self.assertEqual(found, case["senhas"])
                for password in found:
                    m.session.protect_literal(password)
                masked = m.mask(text)
                for value in case["mascarar"]:
                    self.assertNotIn(value.casefold(), masked.casefold())
                for value in case["manter"]:
                    self.assertIn(value.casefold(), masked.casefold())
                self.assertEqual(m.unmask(masked), text)

    def test_fakes_are_ascii_and_not_real_names(self):
        fakes = {(p + s).casefold() for p in masking._PREFIXES for s in masking._SUFFIXES}
        self.assertTrue(all(f.isascii() for f in fakes))
        session = Session(Vault())
        for i in range(200):
            self.assertNotIn(session.get("name", f"real{i}"), nomes.FIRST_NAMES | nomes.SURNAMES)

    def test_a_fake_is_never_a_word_already_seen(self):
        m = masker()
        # Todas as combinações com 14 dos 15 sufixos já apareceram num texto: o falso novo só pode ter o que sobrou.
        m.mask(" ".join(p + s for p in masking._PREFIXES for s in masking._SUFFIXES[1:]))
        self.assertTrue(m.session.get("name", "paula").endswith(masking._SUFFIXES[0]))

    def test_a_real_word_equal_to_a_fake_gets_its_own_fake(self):
        m = Masker(Vault())
        m.add_name("Paula")
        m.session.forward["name"]["paula"] = "alberto"
        m.session.reverse["name"]["alberto"] = "paula"
        first, second, _ = m.mask("Paula • Alberto • Enviar").split(" • ")
        self.assertEqual(first, "Alberto")
        self.assertNotEqual(second, "Alberto")
        self.assertEqual(m.unmask(f"toque em {second}"), "toque em Alberto")
        self.assertEqual(m.unmask("toque em Alberto"), "toque em Paula")

    def test_released_name_is_not_learned_by_rule(self):
        m = masker()
        m.session.release("Padaria Gisele")
        self.assertEqual(m.mask("Qual o horário da Padaria Gisele?"), "Qual o horário da Padaria Gisele?")

    def test_fixed_instructions_skip_the_name_rules(self):
        self.assertEqual(masker().mask("Example: message Gisele", learn=False), "Example: message Gisele")

    def test_common_word_pointed_by_the_model_only_counts_capitalized(self):
        m = Masker(Vault())
        m.session.protect_name("Rosa")
        masked = m.mask("Rosa pediu a tinta rosa")
        self.assertNotIn("Rosa", masked)
        self.assertIn("rosa", masked)
        m.session.protect_name("manda pra rosa")
        self.assertNotIn("rosa", m.mask("a rosa chegou"))

    def test_short_number_is_not_a_literal(self):
        m = Masker(Vault())
        m.session.protect_literal("190")
        m.session.protect_literal("1080")
        screen = '3. TextView: "Sala 190, código 1080" - (0,100,1080,190)'
        masked = m.mask(screen)
        self.assertIn("(0,100,1080,190)", masked)
        self.assertIn("Sala 190", masked)
        self.assertNotIn("código 1080", masked)
        self.assertEqual(m.unmask(masked), screen)

    def test_frozen_set_with_rules_only(self):
        """O conjunto congelado só com as regras e o cofre, sem modelo nenhum, não pode piorar. Em 2026-11-12: 169 de
        187 pessoas, 23 de 38 usuários, 402 de 403 a manter, 20 de 20 e-mails, telefones e documentos (antes das regras
        de nome: 83 pessoas e 9 usuários)."""
        word, total = re.compile(r"[^\W\d_]+"), {"pessoa": 0, "usuario": 0, "outro": 0, "manter": 0}
        for case in base.CASOS:
            m = Masker(Vault())
            for name in base.CONTATOS:
                m.add_name(name)
            for email in base.EMAILS:
                m.vault.add("email", email.lower())
            for phone in base.TELEFONES:
                m.add_phone(phone)
            text = case.get("entrada") or " • ".join(case["trechos"])
            sent = m.mask(text)
            self.assertEqual(m.unmask(sent), text, case["id"])
            for name in case["pessoas"]:
                total["pessoa"] += not [t for t in word.findall(name)
                                        if len(t) >= 3 and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", sent, re.I)]
            total["usuario"] += sum(u.lstrip("@").casefold() not in sent.casefold() for u in case["usuarios"])
            total["outro"] += sum(v.casefold() not in sent.casefold() for v in case["outros"])
            total["manter"] += sum(v.casefold() in sent.casefold() for v in case["manter"])
        self.assertGreaterEqual(total["pessoa"], 169)
        self.assertGreaterEqual(total["usuario"], 23)
        self.assertEqual(total["outro"], 20)
        self.assertGreaterEqual(total["manter"], 402)


if __name__ == "__main__":
    unittest.main()
