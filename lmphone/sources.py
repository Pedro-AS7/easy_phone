"""Lê do aparelho (via adb) os dados pessoais conhecidos e os cadastra no cofre.

Uso: python -m lmphone.sources
"""

import json
import re
import subprocess

from .masking import EMAIL, Masker, Vault

VAULT_PATH = "data/vault.json"
STOPLIST_PATH = "data/stoplist.txt"


def adb(*args):
    return subprocess.run(["adb", "shell", *args], capture_output=True, text=True, timeout=60).stdout


def query(uri, column):
    out = adb("content", "query", "--uri", uri, "--projection", column)
    return [m.group(1).strip() for m in re.finditer(rf"^Row: \d+ {column}=(.*)$", out, re.M) if m.group(1) != "NULL"]


def apps():
    """Apps instalados, como o Portal os lista: [{"label": nome, "packageName": pacote, ...}]. Com LMPHONE_DEVICE=app,
    pelo app do lm_phone (só com o serviço dele ligado, como o do Portal)."""
    from .access import USE_APP
    if USE_APP:
        from .device import AppDevice
        return AppDevice().request("/apps")  # o _unwrap do Device já tira o "result"
    out = adb("content", "query", "--uri", "content://com.mobilerun.portal/packages")
    try:
        return json.loads(out[out.index("result=") + 7:])["result"]
    except (ValueError, KeyError):
        return []


def app_words():
    """Palavras dos nomes dos apps instalados: um contato "Gmail" não deve mascarar o app."""
    return [word for app in apps() for word in re.findall(r"[^\W\d_]+", app.get("label", ""))]


def load_stoplist():
    try:
        with open(STOPLIST_PATH, encoding="utf-8") as f:
            return f.read().split()
    except FileNotFoundError:
        return []


def collect(masker):
    """Cadastra contas, perfil e contatos. Devolve a contagem por origem."""
    counts = {}

    def count(key):
        counts[key] = counts.get(key, 0) + 1

    accounts = set(re.findall(r"Account \{name=(.*?), type=([^}]+)\}", adb("dumpsys", "account")))
    for name, kind in accounts:
        if re.fullmatch(EMAIL, name):
            masker.vault.add("email", name.lower())
            count("contas: e-mail")
        elif len(re.sub(r"\D", "", name)) >= 8 and not re.search(r"[^\W\d_]", name):
            masker.add_phone(name)
            count("contas: número")
        elif " " in name:
            masker.add_name(name)
            count("contas: nome")
        elif name.casefold() not in kind.casefold():  # ex.: conta "WhatsApp" do com.whatsapp
            masker.add_literal(name)
            count("contas: nome de usuário")

    for name in query("content://com.android.contacts/profile", "display_name"):
        masker.add_name(name)
        count("perfil do dono")
    for name in query("content://com.android.contacts/contacts", "display_name"):
        if re.fullmatch(EMAIL, name):
            masker.vault.add("email", name.lower())
        else:
            masker.add_name(name)
        count("contatos: nome")
    for number in query("content://com.android.contacts/data/phones", "data1"):
        masker.add_phone(number)
        count("contatos: telefone")
    for email in query("content://com.android.contacts/data/emails", "data1"):
        masker.vault.add("email", email.lower())
        count("contatos: e-mail")
    return counts


def main():
    vault = Vault(VAULT_PATH)
    counts = collect(Masker(vault, load_stoplist() + app_words()))
    vault.save()
    for key, n in sorted(counts.items()):
        print(f"{n:5d}  {key}")
    print("no cofre:", ", ".join(f"{len(v)} {k}" for k, v in vault.reals.items()))


if __name__ == "__main__":
    from lmphone import bridge
    bridge.choose()  # cabo ou depuração sem fio (com os dois, o adb sem escolha recusaria)
    main()
