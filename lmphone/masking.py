"""Pseudonimização reversível: troca dados pessoais por dados falsos e consistentes.

O cofre (Vault) guarda em arquivo só os valores reais a proteger. Os valores falsos
são sorteados a cada tarefa e ficam na Session, em memória. O Masker aplica as trocas
num texto em uma única passada (para nunca mascarar duas vezes o mesmo trecho) e
desfaz as trocas na resposta do provedor.
"""

import json
import os
import random
import re
import threading
import unicodedata

from .nomes import AMBIGUOUS, FIRST_NAMES, SURNAMES

EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
CARD = r"(?<![\w-])(?:\d{4}[ -]){3}\d{4}(?![\w-])"
CPF = r"(?<![\w.])\d{3}\.\d{3}\.\d{3}-\d{2}(?!\w)"
HANDLE = r"(?<![\w@.])@[A-Za-z0-9_.]{2,30}(?<![.])"
# Com DDD (10 ou 11 dígitos, com ou sem +55) ou no formato 99999-9999.
PHONE = (
    r"(?<![\w,.(/+-])(?:"
    r"(?:\+?55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}[ -]?\d{4}"
    r"|9?\d{4}-\d{4}"
    r")(?![\w,/-]|\.\d)"
)

# Documentos e códigos que as regras acima não pegam (o maskai mostrou que saíam reais no pedido falado e na página de
# resultados da pesquisa; na tela comum, `executor.redact` já troca os dígitos por "#").
CNPJ = r"(?<![\w.])\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\w)"
CEP = r"(?<![\w.-])\d{5}-\d{3}(?![\w-])"
# Sem pontuação, só valem com os dígitos verificadores certos (`valid`): um número qualquer de 11, 14 ou 16 dígitos fica.
CARD16 = r"(?<![\w-])\d{16}(?![\w-])"
CPF11 = r"(?<![\w.,-])\d{11}(?![\w-]|[.,]\d)"
CNPJ14 = r"(?<![\w.,-])\d{14}(?![\w-]|[.,]\d)"
# Placa no padrão Mercosul em qualquer lugar; a antiga ("ABC-1234" tem a forma de "ISO-9001") e os números de RG, CNH,
# conta e CEP sem hífen só depois do rótulo. O falso tem a mesma forma (`Session._new_fake`, tipo "code").
PLATE = r"(?<![\w-])[A-Z]{3}\d[A-Z]\d{2}(?![\w-])"
_LABELS = ("rg", "cnh", "cep", "conta", "placa")
_AFTER_LABEL = (" ", ": ", " é ", " nº ", " n° ", " no ", " número ", " numero ")
LABELED = ("(?i:(?:" + "|".join(f"(?<=\\b{label}{sep})" for label in _LABELS for sep in _AFTER_LABEL) + ")"
           r"(?:[a-z]{3}-?\d[a-z\d]\d{2}|\d[\d.\-/]{2,18}[\dx])(?![\w-]))")
_PLATE_SHAPE = re.compile(r"(?i)[a-z]{3}-?\d[a-z\d]\d{2}")
MIN_CODE_DIGITS = 5  # um número curto depois do rótulo ("conta 2024") não identifica ninguém e casaria com outros números

# Logradouro: o nome da rua vira nome da sessão (`Masker.learn`).
STREET = re.compile(r"(?<![\w.])(?i:rua|r\.|avenida|av\.?|alameda|travessa|estrada|rodovia)[ \t]+")
_STREET_WORD = re.compile(r"((?:d[aeo]s?|e)[ \t]+)?([^\W_]+)[ \t]?", re.I)
_STREET_NUMBER = re.compile(r",?[ \t]*(?:n[ºo°.]?[ \t]*)?\d{2,}")
MAX_STREET_WORDS = 4

# Senha dita no pedido ("a senha é fps141731", "password: x", "troca a senha do wifi pra abc12345"). Nenhuma outra regra
# a pega, e ela iria ao provedor no texto da tarefa. Até 2026-11-12 a regra pegava a primeira palavra depois de "senha"
# ("troca a senha do wifi pra abc12345" dava "pra", e "pra" virava literal da sessão): agora o valor vem depois de
# "é", ":" ou "=" (qualquer palavra que não seja de `_NOT_PASSWORD`), ou depois de "pra"/"para" ou logo depois de
# "senha", e nesses dois casos só se tiver cara de senha (`_shaped`).
_PASSWORD_WORD = r"\b(?:senha|password|passcode|passwd)\b"
_PASSWORD_VALUE = r"[\"']?([^\s\"',;]+)"
PASSWORD_IS = re.compile(rf"(?i){_PASSWORD_WORD}[^\n.!?;]{{0,40}}?(?:\s(?:é|eh|is)\s|\s*[:=])\s*{_PASSWORD_VALUE}")
PASSWORD_TO = re.compile(rf"(?i){_PASSWORD_WORD}[^\n.!?;]{{0,40}}?\s(?:pra|para|to)\s+{_PASSWORD_VALUE}")
PASSWORD_NEXT = re.compile(rf"(?i){_PASSWORD_WORD}\s+{_PASSWORD_VALUE}")

_NOT_PASSWORD = set("""
da do de das dos wifi wi-fi rede é eh is nova new atual antiga velha old current
a o um uma the an esta essa aquela este esse aquele minha meu sua seu my your
que qual quais como onde quando porque what which
muito muita bem mais menos tão tao too very not não nao sem com para pra por
mesma mesmo same igual diferente outra outro other
fraca forte weak strong fácil facil difícil dificil easy hard simples segura insegura curta longa grande pequena
errada certa incorreta correta inválida invalida válida valida wrong right correct invalid valid
obrigatória obrigatoria required opcional secreta pessoal padrão padrao default temporária temporaria
aquilo isso isto algo nada tudo
""".split())


def _shaped(value):
    """Tem cara de senha: um dígito, um símbolo ou maiúsculas no meio ("Kz81!x", "abc12345", "aBcD")."""
    return (any(c.isdigit() for c in value) or any(not c.isalnum() for c in value)
            or (value != value.lower() and value != value.upper() and value != value.capitalize()))


def passwords(text):
    """As senhas ditas em `text`, sem a pontuação que fecha a frase ("troca a senha do wifi" não tem senha)."""
    found = []
    for pattern, needs_shape in ((PASSWORD_IS, False), (PASSWORD_TO, True), (PASSWORD_NEXT, True)):
        for value in pattern.findall(text):
            value = value.rstrip(".!?\"'):=")
            if len(value) < 3 or value.casefold() in _NOT_PASSWORD or value in found:
                continue
            if needs_shape and not _shaped(value):
                continue
            found.append(value)
    return found


def plain(text):
    """Sem acentos e em minúsculas: a forma das listas de `nomes.py`."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def _check_digits(digits, weights):
    total = sum(int(d) * w for d, w in zip(digits, weights)) % 11
    return 0 if total < 2 else 11 - total


def valid(kind, digits):
    """Os dígitos verificadores de um CPF, de um CNPJ ou de um cartão escritos sem pontuação."""
    if len(set(digits)) == 1:
        return False
    if kind == "cpf11":
        return (_check_digits(digits[:9], range(10, 1, -1)) == int(digits[9])
                and _check_digits(digits[:10], range(11, 1, -1)) == int(digits[10]))
    if kind == "cnpj14":
        first, second = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        return (_check_digits(digits[:12], first) == int(digits[12])
                and _check_digits(digits[:13], second) == int(digits[13]))
    total = 0  # Luhn
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


# O grupo da expressão -> o tipo que vai para as contagens e para a sessão.
GROUP_KIND = {"card16": "card", "cpf11": "cpf", "cnpj14": "cnpj"}

# Palavras que aparecem em nomes de contatos mas não identificam ninguém.
STOPLIST = """
de da do das dos van von del della
casa trabalho mae mãe pai amor vo vó vô tio tia primo prima irmao irmão irma irmã
filho filha esposa esposo marido namorada namorado sogra sogro
banco loja mercado farmacia farmácia pizzaria restaurante padaria uber taxi táxi
dentista medico médico medica médica doutor doutora prof professor professora
escola academia portaria condominio condomínio sindico síndico oficina suporte
atendimento emergencia emergência policia polícia bombeiros samu correios
vivo claro tim net nubank itau itaú bradesco santander caixa inter
google samsung whatsapp instagram facebook microsoft apple android meet duo
novo nova grupo familia família cliente fornecedor entrega delivery
home work mom dad office the and you
dr dra sr sra secretaria barbearia odontologia clinica clínica salao salão mecanica mecânica
advocacia contabilidade imobiliaria imobiliária lanchonete hamburgueria veterinaria veterinária
hospital universidade faculdade colegio colégio igreja consultorio consultório laboratorio
laboratório posto hotel pousada studio estudio estúdio
""".split()

_PREFIXES = "Al Bel Cas Dor Ev Flor Gil Hel Ir Jov Lind Mar Nor Od Per Quir Ros Sev Tar Val Zen Arn Bert Clod Dem".split()
# Sem acento: o provedor nem sempre devolve o acento igual ("Rosalia", "Ros\\u00e1lia" dentro de um JSON), e aí o falso
# não voltava ao real.
_SUFFIXES = "ano iro ilde ino alia omar enio ilda oval esio undo erto icia olfo ania".split()
_WORD = re.compile(r"[^\W\d_]+")
_CONNECTIVES = {"de", "da", "do", "das", "dos", "e"}
MAX_SURNAMES = 4  # palavras que continuam um nome depois do prenome


def _keep_case(source, replacement):
    if source.isupper() and len(source) > 1:
        return replacement.upper()
    if source.islower():
        return replacement.lower()
    return replacement


def _swap_digits(text, new_digits):
    """Troca os dígitos de `text` pelos de `new_digits`, da direita para a esquerda."""
    out, pending = [], list(new_digits)
    for ch in reversed(text):
        out.append(pending.pop() if ch.isdigit() and pending else ch)
    return "".join(reversed(out))


class Vault:
    """O que proteger: valores reais conhecidos, por tipo, num arquivo JSON (modo 600).

    Não guarda valores falsos: esses nascem e morrem com cada Session.
    """

    KINDS = ("name", "email", "literal", "phone")

    def __init__(self, path=None):
        self.path = path
        self.lock = threading.RLock()
        self.reals = {kind: set() for kind in self.KINDS}
        self.version = 0
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for kind, values in json.load(f).items():
                    self.reals[kind] = set(values)

    def add(self, kind, real):
        with self.lock:
            if real not in self.reals[kind]:
                self.reals[kind].add(real)
                self.version += 1

    def save(self):
        if not self.path:
            return
        with self.lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({k: sorted(v) for k, v in self.reals.items()}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)


class Session:
    """Pares real <-> falso de uma única tarefa. Vive só na memória."""

    KINDS = Vault.KINDS + ("digits", "handle", "code")

    def __init__(self, vault):
        self.vault = vault
        self.lock = threading.RLock()
        self.forward = {kind: {} for kind in self.KINDS}
        self.reverse = {kind: {} for kind in self.KINDS}
        self.version = 0
        # Decisões da IA local, válidas só nesta tarefa.
        self.extra_names = set()  # nomes fora do cofre a mascarar, em qualquer caixa
        self.cap_names = set()  # nomes que só valem capitalizados: os que também são palavra comum ("Rosa", "Costa")
        self.words = set()  # palavras dos textos já mascarados: um falso novo nunca é igual a uma delas
        self.extra_literals = set()  # nomes de usuário vistos na tela
        self.released = set()  # nomes do cofre que precisam sair reais (pesquisa)
        self.seen = set()  # trechos de tela que a IA local já julgou

    def protect_name(self, span, stop=(), keep_released=False):
        with self.lock:
            for token in re.findall(r"[^\W\d_]+", span):
                if keep_released and token.casefold() in self.released:
                    continue
                if len(token) >= 3 and token.casefold() not in stop:
                    # Uma palavra comum que também é nome ("Rosa") só vale capitalizada, a menos que tenha sido
                    # apontada em minúsculas ("manda pra rosa").
                    names = self.cap_names if plain(token) in AMBIGUOUS and not token.islower() else self.extra_names
                    names.add(token.casefold())
                    self.released.discard(token.casefold())
            self.version += 1

    def protect_literal(self, span):
        with self.lock:
            value = span.strip().lstrip("@").casefold()
            # Só números, com menos de 4 dígitos: casaria com qualquer outro número do texto (uma coordenada da tela).
            short = not any(c.isalpha() for c in value) and sum(c.isdigit() for c in value) < 4
            if len(span.strip()) >= 3 and not short:
                self.extra_literals.add(value)
                self.version += 1

    def release(self, span):
        with self.lock:
            for token in re.findall(r"[^\W\d_]+", span):
                if token.casefold() not in self.extra_names:
                    self.released.add(token.casefold())
            self.version += 1

    def get(self, kind, real):
        """Devolve o falso de `real` nesta tarefa, criando um novo par se ainda não existir."""
        with self.lock:
            fake = self.forward[kind].get(real)
            if fake is None:
                fake = self._new_fake(kind, real)
                self.forward[kind][real] = fake
                self.reverse[kind][fake] = real
                self.version += 1
            return fake

    def real(self, kind, fake):
        return self.reverse[kind].get(fake)

    def _new_fake(self, kind, real):
        taken, known = self.reverse[kind], self.vault.reals.get(kind, ())
        for _ in range(10000):
            if kind == "name":
                fake = (random.choice(_PREFIXES) + random.choice(_SUFFIXES)).casefold()
                if len(taken) > 300:
                    fake += random.choice(_SUFFIXES)
            elif kind == "email":
                fake = f"contato{random.randint(1000, 999999)}@exemplo.com"
            elif kind == "literal":
                fake = f"usuario{random.randint(1000, 999999)}"
            elif kind == "handle":
                fake = f"@usuario{random.randint(1000, 999999)}"
            elif kind == "code":  # a mesma forma: letra por letra, dígito por dígito
                fake = "".join(random.choice("0123456789") if c.isdigit() else
                               random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") if c.isalpha() else c for c in real)
            else:  # digits, phone: mesma quantidade de dígitos
                fake = "".join(random.choice("0123456789") for _ in real)
            # Um falso igual a uma palavra já vista (um "Alberto" de verdade na tela) voltaria como o real de outro.
            if kind == "name" and (fake in self.words or fake in FIRST_NAMES or fake in SURNAMES):
                continue
            if fake not in taken and fake not in known and fake != real:
                return fake
        raise RuntimeError(f"sem valores falsos livres para o tipo {kind}")


class Masker:
    def __init__(self, vault, stoplist=(), session=None):
        self.vault = vault
        self.session = session or Session(vault)
        self.stop = {w.casefold() for w in STOPLIST} | {w.casefold() for w in stoplist}
        self._built = None
        self._known = None

    # --- cadastro de dados conhecidos (vindos do aparelho) ---

    def add_name(self, full_name):
        for token in re.findall(r"[^\W\d_]+", full_name):
            if len(token) >= 3 and token.casefold() not in self.stop:
                self.vault.add("name", token.casefold())

    def add_literal(self, value):
        value = value.strip()
        if len(value) >= 4 and value.casefold() not in self.stop:
            self.vault.add("literal", value.casefold())

    def knows(self, span):
        """Algum pedaço de `span` está no cofre?"""
        tokens = {t.casefold() for t in re.findall(r"[^\W\d_]+", span)}
        return bool(tokens & self.vault.reals["name"]) or span.casefold() in self.vault.reals["literal"]

    def add_phone(self, number):
        digits = re.sub(r"\D", "", number)
        if len(digits) >= 8:
            self.vault.add("phone", digits[-8:])

    # --- nomes e logradouros por regra (valem sem a IA local) ---

    def _vault_plain(self):
        """Os nomes do cofre sem acento: "Livia" no texto é a "Lívia" dos contatos."""
        if not self._known or self._known[0] != self.vault.version:
            self._known = (self.vault.version, {plain(name) for name in self.vault.reals["name"]})
        return self._known[1]

    def learn(self, text):
        """Os nomes que a forma do texto denuncia viram nomes da sessão, antes da troca (só com as regras e o cofre, o
        conjunto congelado mascarava 83 de 187 pessoas; o maskai mostrou que a regra fecha boa parte disso):
        - um prenome de `nomes.FIRST_NAMES` é pessoa em qualquer caixa ("pergunta pra gisele"), e o que vem colado
          depois dele continua o nome: sobrenome conhecido, nome do cofre ou, com tudo capitalizado, qualquer palavra;
        - um nome do cofre escrito sem acento ("Livia") ou em minúsculas, se a palavra só é nome ("souza", não "casa");
        - o nome de um logradouro ("Rua das Acácias", "rua das acácias 482");
        - uma palavra igual a um falso já sorteado (um Alberto de verdade, com "Alberto" já sendo o falso de alguém).
        Um prenome que também é palavra comum ("Rosa", "Vitória") só vale com um sobrenome depois."""
        session, vault_names = self.session, self.vault.reals["name"]
        with self.vault.lock, session.lock:
            known = self._vault_plain()
            before = len(session.extra_names) + len(session.cap_names)
            tokens = list(_WORD.finditer(text))
            for i, match in enumerate(tokens):
                token = match.group()
                folded, key = token.casefold(), plain(token)
                session.words.add(folded)
                if len(token) < 3 or folded in self.stop or folded in session.released:
                    continue
                if folded in session.reverse["name"] and folded not in vault_names:
                    session.extra_names.add(folded)
                if key in known and folded not in vault_names and not token.islower():
                    session.cap_names.add(folded)
                listed = key in FIRST_NAMES or key in SURNAMES
                if token.islower() and key in known and listed and key not in AMBIGUOUS:
                    session.extra_names.add(folded)
                if key in FIRST_NAMES and key not in AMBIGUOUS:
                    session.extra_names.add(folded)
                    self._surnames(text, tokens, i, known, strict=False)
                elif key in FIRST_NAMES and not token.islower() and self._surnames(text, tokens, i, known, strict=True):
                    session.cap_names.add(folded)
            for match in STREET.finditer(text):
                self._street(text, match.end())
            if len(session.extra_names) + len(session.cap_names) != before:
                session.version += 1

    def _surnames(self, text, tokens, i, known, strict):
        """Aprende as palavras que continuam o nome começado em `tokens[i]`. `strict`: só sobrenomes das listas ou
        do cofre, capitalizados. Devolve quantas aprendeu."""
        session, first, learned, by_form = self.session, tokens[i].group(), 0, 0
        j = i + 1
        while j < len(tokens) and learned < MAX_SURNAMES:
            token = tokens[j].group()
            folded, key = token.casefold(), plain(token)
            if text[tokens[j - 1].end():tokens[j].start()] != " ":
                break
            if folded in _CONNECTIVES:
                j += 1
                continue
            if len(token) < 3 or folded in self.stop or folded in session.released:
                break
            listed = key in SURNAMES or key in FIRST_NAMES or key in known
            if token.islower():
                # Em minúsculas, só o que é nome e nada mais: em "fala pro lucas dias atrás", "dias" fica.
                if strict or not listed or key in AMBIGUOUS:
                    break
                session.extra_names.add(folded)
            elif listed:
                (session.cap_names if key in AMBIGUOUS else session.extra_names).add(folded)
            elif not strict and not first.islower() and by_form < 2:  # "Henrique Albuquerque"
                session.cap_names.add(folded)
                by_form += 1
            else:
                break
            learned += 1
            j += 1
        return learned

    def _street(self, text, at):
        """O nome do logradouro que começa em `at` (depois de "Rua "): capitalizado, com ou sem número; em minúsculas,
        só com o número depois ("rua das acácias 482"), porque "a rua estava cheia" não é endereço."""
        session, words = self.session, []
        while len(words) < MAX_STREET_WORDS:
            match = _STREET_WORD.match(text, at)
            if not match:
                break
            words.append((match.group(2), match.end(2)))
            at = match.end()
        capitalized = []
        for word, _ in words:
            if not (word[0].isupper() or word.isdigit()):
                break
            capitalized.append(word)
        if any(not word.isdigit() for word in capitalized):
            chosen, names = capitalized, session.cap_names
        else:
            chosen, names = [], session.extra_names
            for k, (_, end) in enumerate(words):
                if _STREET_NUMBER.match(text, end):
                    chosen = [word for word, _ in words[:k + 1]]
                    break
        for word in chosen:
            folded = word.casefold()
            if len(word) >= 3 and not word.isdigit() and folded not in self.stop and folded not in session.released:
                names.add(folded)

    # --- regex de passada única ---

    def _patterns(self):
        version = (self.vault.version, self.session.version)
        if self._built and self._built[0] == version:
            return self._built[1], self._built[2]

        def alternation(values):
            return "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True)) or r"(?!)"

        def build(names, literals, code):
            # Um literal só de números (um telefone que a IA local apontou, uma senha "1234") não casa dentro da lista
            # de coordenadas de um elemento da tela, "(0,100,1080,190)", nem colado a um decimal.
            words = [v for v in literals if any(c.isalpha() for c in v)]
            numbers = [v for v in literals if not any(c.isalpha() for c in v)]
            return re.compile(
                f"(?P<email>{EMAIL})|(?P<handle>{HANDLE})|(?P<card>{CARD})|(?P<card16>{CARD16})|(?P<cnpj>{CNPJ})"
                f"|(?P<cpf>{CPF})|(?P<cep>{CEP})|(?P<code>{code})"
                f"|(?P<literal>(?<!\\w)(?i:{alternation(words)})(?!\\w)"
                f"|(?<!\\w)(?:(?<![(,])(?<!, )|(?!\\d+(?:, ?\\d+){{0,3}}\\)))(?:{alternation(numbers)})(?!\\w|[.,]\\d))"
                f"|(?P<phone>{PHONE})|(?P<cpf11>{CPF11})|(?P<cnpj14>{CNPJ14})"
                # A borda do nome é a letra, não a palavra: "livia_bastos" e "Caio2" têm o nome dentro.
                f"|(?P<name>(?<![^\\W\\d_])(?:{alternation(names)})(?![^\\W\\d_]))"
            )

        def variants(tokens, any_case=()):
            # Minúsculas ficam de fora: "casa" não é o contato "Casa". Só valem para
            # o que a IA local ou as regras de `learn` apontaram como nome nesta tarefa.
            forms = {form for t in tokens for form in (t.capitalize(), t.upper())}
            return forms | set(any_case)

        with self.vault.lock, self.session.lock:
            session = self.session
            names = (self.vault.reals["name"] | session.extra_names | session.cap_names) - session.released
            fakes_any_case = {session.forward["name"][t] for t in session.extra_names if t in session.forward["name"]}
            mask_re = build(variants(names, session.extra_names),
                            self.vault.reals["literal"] | session.extra_literals, f"{PLATE}|{LABELED}")
            unmask_re = build(variants(session.reverse["name"], fakes_any_case), session.reverse["literal"],
                              f"(?<![\\w-])(?i:{alternation(session.reverse['code'])})(?![\\w-])")
            self._built = (version, mask_re, unmask_re)
        return mask_re, unmask_re

    def _replace(self, match, lookup):
        kind, text = match.lastgroup, match.group()
        if kind == "email":
            return lookup("email", text.lower()) or text
        if kind == "literal":
            # Com maiúsculas, o par é do texto como foi escrito: uma senha "Kz81!x" voltava "kz81!x" e o aparelho
            # digitava a senha errada. O falso volta em qualquer caixa.
            exact = text if text != text.lower() else text.casefold()
            return lookup("literal", exact) or lookup("literal", text.casefold()) or text
        if kind == "handle":
            return lookup("handle", text.casefold()) or text
        if kind == "name":
            other = lookup("name", text.casefold())
            return _keep_case(text, other.capitalize()) if other else text
        if kind == "code":
            other = lookup("code", text.upper())
            return (other.lower() if text.islower() else other) if other else text
        digits = re.sub(r"\D", "", text)
        if kind == "phone":
            other = lookup("phone", digits[-8:])
        else:
            other = lookup("digits", digits)
        return _swap_digits(text, other) if other else text

    def mask(self, text, counts=None, trace=None, learn=True):
        """`trace`, se dado, recebe uma tupla (tipo, real, falso) por troca feita. `learn=False`: sem as regras de
        nome de `learn` (as instruções fixas do executor, que não têm dado de ninguém)."""
        if learn:
            self.learn(text)

        def repl(match):
            group, found = match.lastgroup, match.group()
            if group == "handle" and found[1:].casefold() in self.session.released:
                return found
            if group in GROUP_KIND and not valid(group, re.sub(r"\D", "", found)):
                return found
            if group == "code" and not (_PLATE_SHAPE.fullmatch(found)
                                        or sum(c.isdigit() for c in found) >= MIN_CODE_DIGITS):
                return found
            new = self._replace(match, self.session.get)
            if new != found:
                kind = GROUP_KIND.get(group, group)
                if counts is not None:
                    counts[kind] = counts.get(kind, 0) + 1
                if trace is not None:
                    trace.append((kind, found, new))
            return new

        return self._patterns()[0].sub(repl, text)

    def unmask(self, text):
        return self._patterns()[1].sub(lambda m: self._replace(m, self.session.real), text)

    def walk(self, value, fn):
        """Aplica `fn` a todas as strings de uma estrutura JSON."""
        if isinstance(value, str):
            return fn(value)
        if isinstance(value, list):
            return [self.walk(v, fn) for v in value]
        if isinstance(value, dict):
            return {k: self.walk(v, fn) for k, v in value.items()}
        return value
