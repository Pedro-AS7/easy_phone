"""O que os modelos pequenos (docs/plano-modelos-pequenos.md) e o servidor deles têm em comum, só com a biblioteca
padrão: os rótulos BIO da marcação, como os trechos de tela viram blocos, como a saída por token vira entidades e
como a escolha de controle monta a pergunta. O treino (tools/treino/treinar.py) e o servidor (lmphone/modelo_server.py)
usam o mesmo código, para o modelo ver no serviço o que viu no treino.
"""

import re

KINDS = ["pessoa", "usuario", "email", "telefone", "documento", "negocio", "instituicao", "lugar", "app",
         "negocio+", "instituicao+", "lugar+"]
LABELS = ["O"] + [f"{p}-{k}" for k in KINDS for p in "BI"]
INTENTS = ["acao", "pesquisa", "mista"]
BLOCK = 600  # caracteres por bloco de trechos de tela, como local_ai.batches (com blocos menores)
SEPARATOR = " • "


def blocks(fragments, spans, size=BLOCK):
    """Junta trechos seguidos em blocos (como o serviço manda à IA), levando as posições das entidades junto."""
    text, found = "", []
    for fragment, fragment_spans in zip(fragments, spans):
        if text and len(text) + len(SEPARATOR) + len(fragment) > size:
            yield text, found
            text, found = "", []
        offset = len(text) + (len(SEPARATOR) if text else 0)
        text = text + SEPARATOR + fragment if text else fragment
        found += [(offset + s, offset + e, k) for s, e, k in fragment_spans]
    if text:
        yield text, found


def decode(offsets, predicted, text):
    """Entidades (início, fim, tipo) a partir dos rótulos BIO de cada token."""
    spans, current = [], None
    for (start, end), label in zip(offsets, predicted):
        name = LABELS[label] if start != end else "O"
        if name == "O":
            current = None
            continue
        prefix, kind = name.split("-", 1)
        if current is not None and current[2] == kind and prefix == "I":
            current[1] = end
        else:
            current = [start, end, kind]
            spans.append(current)
    return whole_words([(s, e, k) for s, e, k in spans if text[s:e].strip()], text)


PRIVATE = ("pessoa", "usuario", "email", "telefone", "documento")
HANDLE = re.compile(r"[._\d]")


def whole_words(spans, text):
    """Estende cada entidade até as bordas da palavra (sequência sem espaço) e junta as que caem na mesma palavra.
    O modelo às vezes marca um nome de usuário em pedaços ("jo", "ao.", "va" em "joao.vitor.silva"); a máscara precisa
    da palavra inteira. Na junção, um tipo privado ganha de um público; pedaços de tipos diferentes numa palavra com
    ponto, sublinhado ou dígito viram usuário (ou e-mail, com @)."""
    out = []
    for s, e, k in spans:
        while s > 0 and not text[s - 1].isspace() and text[s - 1] not in "•,;:()\"'“”":
            s -= 1
        while e < len(text) and not text[e].isspace() and text[e] not in "•,;:()\"'“”?!":
            e += 1
        while e > s and text[e - 1] in ".…":  # ponto final da frase não é parte do nome
            e -= 1
        if out and s < out[-1][1]:
            ps, pe, pk = out[-1]
            kinds = {pk, k}
            word = text[min(ps, s):max(pe, e)]
            if len(kinds) > 1 and HANDLE.search(word) and " " not in word:
                kind = "email" if "@" in word else "usuario"
            else:
                kind = next((x for x in (pk, k) if x.rstrip("+") in PRIVATE), pk)
            out[-1] = (min(ps, s), max(pe, e), kind)
        else:
            out.append((s, e, k))
    return out


NONE_LABEL = "(none of these)"  # a opção "nenhum": o modelo dá nota a ela como a um rótulo


def query(wanted):
    return " / ".join(wanted)
