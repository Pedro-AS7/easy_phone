"""IA local (Ollama): julga o pedido do usuário e acha dados pessoais em texto livre.

Desde 2026-10-19 as duas chamadas vão aos modelos pequenos (lmphone/modelo_server.py); com LMPHONE_LOCAL_AI=gemma,
à Gemma pelo Ollama, como antes.

Ela só pode pedir mais máscara ou liberar negócios e instituições que precisam ser
pesquisados. Pessoas, e-mails, telefones e documentos seguem as regras fixas.
"""

import json
import os
import re
import time
import unicodedata
import urllib.request

OLLAMA = "http://127.0.0.1:11434"
# A mesma gemma4:e2b-it-qat sem o projetor de imagem e áudio, que o projeto não usa (1 GB a menos na memória, mesmas
# respostas). O run.sh a cria no Ollama quando falta. Raciocínio fica desligado: com ele, o tempo triplica.
MODEL = "gemma4-e2b-texto"

REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "intencao": {"type": "string", "enum": ["pesquisa", "acao", "mista"]},
        "entidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string"},
                    "tipo": {
                        "type": "string",
                        "enum": ["pessoa", "negocio", "instituicao", "lugar", "app", "outro"],
                    },
                    "precisa_pesquisa": {"type": "boolean"},
                },
                "required": ["texto", "tipo", "precisa_pesquisa"],
            },
        },
    },
    "required": ["intencao", "entidades"],
}

REQUEST_PROMPT = """Você analisa pedidos feitos a um assistente que controla o celular do usuário.

Classifique a intenção:
- "pesquisa": a resposta exige buscar informação pública na internet (endereço, horário, preço, notícia, como fazer algo).
- "acao": tudo se resolve no próprio celular (mandar mensagem, ligar, abrir app, mudar configuração, criar lembrete).
- "mista": precisa pesquisar na internet e também agir no celular.

Liste as entidades: só nomes próprios que aparecem no pedido, copiados exatamente como foram escritos (mesmo em minúsculas).
- "pessoa": qualquer pessoa, privada ou famosa (amigo, parente, colega, contato, artista, político, atleta). Na dúvida entre pessoa e outro tipo, use "pessoa".
- "negocio": loja, restaurante, barbearia, clínica, empresa.
- "instituicao": universidade, órgão público, banco, jornal.
- "lugar": cidade, bairro, país.
- "app": aplicativo ou site (Instagram, WhatsApp, Google, iFood).
"precisa_pesquisa" é true só quando o pedido exige buscar na internet informação pública sobre aquela entidade.
Não liste palavras comuns, e-mails, telefones nem documentos.

Exemplos:
Pedido: Qual o horário da Padaria Trigal?
{"intencao":"pesquisa","entidades":[{"texto":"Padaria Trigal","tipo":"negocio","precisa_pesquisa":true}]}
Pedido: fala pro marcos que já saí
{"intencao":"acao","entidades":[{"texto":"marcos","tipo":"pessoa","precisa_pesquisa":false}]}
Pedido: Manda mensagem pra Padaria Trigal pedindo 10 pães
{"intencao":"acao","entidades":[{"texto":"Padaria Trigal","tipo":"negocio","precisa_pesquisa":false}]}
Pedido: Vê o preço do ingresso do Cine Drive e manda pra Paula no WhatsApp
{"intencao":"mista","entidades":[{"texto":"Cine Drive","tipo":"negocio","precisa_pesquisa":true},{"texto":"Paula","tipo":"pessoa","precisa_pesquisa":false},{"texto":"WhatsApp","tipo":"app","precisa_pesquisa":false}]}"""

SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["pessoa", "usuario"]},
                },
                "required": ["texto", "tipo"],
            },
        }
    },
    "required": ["itens"],
}

SCREEN_PROMPT = """Você recebe o texto de uma tela de celular. Liste os nomes de pessoas e os nomes de usuário, copiados exatamente como aparecem (mesmo em minúsculas):
- "pessoa": nome de qualquer pessoa, privada ou famosa (nome, sobrenome ou apelido), inclusive dentro de frases e de buscas.
- "usuario": nome de usuário de rede social (ex.: ana_souza12, joao.lima).
Não liste: nomes de apps, empresas, marcas, canais, grupos, cidades, botões, menus nem palavras comuns. Se não houver nada, devolva a lista vazia.

Exemplo:
Tela: Curtido por bia.rocha e outras pessoas • Feliz aniversário, Tiago Mendes! • Seguir
{"itens":[{"texto":"bia.rocha","tipo":"usuario"},{"texto":"Tiago Mendes","tipo":"pessoa"}]}"""


def _chat(system, user, schema, timeout, **options):
    body = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "format": schema,
        # use_mmap: o arquivo do modelo é mapeado em vez de copiado, e o sistema pode soltar essas páginas se faltar memória.
        "options": {"temperature": 0, "num_ctx": 4096, "use_mmap": True, **options},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    request = urllib.request.Request(
        f"{OLLAMA}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)["message"]["content"]


def ask(system, user, schema, timeout=300, head=None):
    """Devolve (resposta já em dict, texto bruto, segundos). Levanta exceção se a IA falhar.

    `head` é o começo fixo de `user` ("Pedido:"). O servidor do Ollama só retoma a leitura de um prompt
    de onde ele mesmo salvou um ponto, e salva um no fim de cada prompt. Uma chamada de preparo que
    termina em `head` deixa o ponto no fim da parte fixa, e a chamada de verdade lê só o texto novo:
    de 7,5 s para 0,2 a 0,4 s no pedido. Com o ponto já salvo, o preparo custa 0,2 s."""
    start = time.monotonic()
    if head:
        try:
            _chat(system, head, schema, timeout, num_predict=1)
        except Exception:
            pass  # sem o preparo, a chamada abaixo só é mais lenta
    raw = _chat(system, user, schema, timeout)
    return json.loads(raw), raw, time.monotonic() - start


# Os modelos pequenos (lmphone/modelo_server.py, na porta do Laya); LMPHONE_LOCAL_AI=gemma volta à Gemma.
BACKEND = os.environ.get("LMPHONE_LOCAL_AI", "novo")
SMALL = f"http://127.0.0.1:{os.environ.get('LMPHONE_LAYA_PORT', '8788')}"


def small(path, text, timeout):
    """Mesma resposta que `ask`, vinda do servidor dos modelos pequenos."""
    request = urllib.request.Request(SMALL + path, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        answer = json.load(response)
    seconds = answer.pop("seconds")
    return answer, json.dumps(answer, ensure_ascii=False), seconds


def judge_request(text, timeout=300):
    if BACKEND == "novo":
        return small("/judge", text, timeout)
    return ask(REQUEST_PROMPT, f"Pedido: {text}", REQUEST_SCHEMA, timeout, head="Pedido:")


def find_private(text, timeout=300):
    if BACKEND == "novo":
        return small("/entities", text, timeout)
    return ask(SCREEN_PROMPT, f"Tela: {text}", SCREEN_SCHEMA, timeout, head="Tela:")


_STATE = re.compile(r"<device_state>(.*?)(?:</device_state>|\Z)", re.S)
# "12. TextView: "id", "texto" ; isChecked=True - (0,0,10,10)"; um elemento sem classe não tem o "TextView: ".
_ELEMENT = re.compile(r"\s*\d+\. (?:([\w.$]+): )?(.*?)(?: ; isChecked=\w+)? - \(\d+, ?\d+, ?\d+, ?\d+\)")
_HEADERS = ("**Current Phone State:**", "Current Clickable UI elements:", "'index. className:", "• **App:**", "• **Keyboard:**")
_FOCUSED = re.compile(r"• \*\*Focused Element:\*\* '(.*)'")


def screen_fragments(text):
    """Trechos de texto visíveis na tela (árvore de acessibilidade do Mobilerun), na ordem
    em que aparecem. Ficam de fora ids, nomes de classe, o cabeçalho (app e teclado) e trechos sem nenhuma palavra."""
    fragments = []
    for state in _STATE.findall(text):
        for line in state.splitlines():
            line = line.strip()
            element, focused = _ELEMENT.fullmatch(line), _FOCUSED.fullmatch(line)
            if element:
                cls = element.group(1)
                parts = [p.strip('"') for p in element.group(2).split('", "')]
                parts = [p for p in parts if ":id/" not in p and not (cls and p.endswith("." + cls))]
            elif focused:
                parts = [focused.group(1)]
            else:
                parts = [] if line.startswith(_HEADERS) else [line]
            fragments.extend(p.strip() for p in parts if re.search(r"[^\W\d_]{3}", p))
    return list(dict.fromkeys(fragments))


def batches(fragments, size=1200):
    """Junta os trechos em blocos de até `size` caracteres: uma chamada à IA por bloco."""
    batch, length = [], 0
    for fragment in fragments:
        if batch and length + len(fragment) > size:
            yield batch
            batch, length = [], 0
        batch.append(fragment)
        length += len(fragment) + 3
    if batch:
        yield batch


def _plain(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def align(span, source):
    """A IA nem sempre copia o trecho com os mesmos acentos e maiúsculas: devolve as
    palavras de `span` do jeito que estão escritas em `source`."""
    written = {}
    for token in re.findall(r"[^\W\d_]+", source):
        written.setdefault(_plain(token), set()).add(token)
    words = []
    for token in re.findall(r"[^\W\d_]+", span):
        words.extend(sorted(written.get(_plain(token), {token})))
    return " ".join(words)


# Um nome de usuário de verdade tem a forma de um (@, ponto, _, número) ou vem num pedido sobre uma rede social.
HANDLE = re.compile(r"[@._\d]")
SOCIAL = re.compile(r"@|instagram|\binsta\b|tiktok|twitter|\bx\.com|threads|telegram|facebook|\bface\b|youtube|"
                    r"\bcanal\b|perfil|profile|\bsegu[ei]|seguir|follow|\bdm\b|direct|usu[aá]rio|\buser|arroba|discord|"
                    r"twitch|kwai|linkedin|snapchat|reddit|github|whatsapp|\bzap\b", re.I)


# Um endereço de site não é pessoa: o modelo de marcação já marcou "metropoles.com" assim, e o nome falso no lugar do
# site estragava a busca.
URLISH = re.compile(r"(?i)://|\bwww\.|[\w-]\.(?:com|net|org|gov|edu|br|io|app|tv|me|ly)\b")


def apply_request(judgment, masker, source):
    """Aplica o julgamento do pedido à sessão. Devolve uma linha de decisão por entidade."""
    decisions = []
    for entity in judgment.get("entidades", []):
        text, kind = align(entity["texto"], source), entity["tipo"]
        known = masker.knows(text)
        wants_search = entity["precisa_pesquisa"] and judgment["intencao"] != "acao"
        if kind in ("pessoa", "pessoa_publica") and URLISH.search(entity["texto"]):
            decision, reason = "manter", "tem a forma de um endereço de site"
        elif kind in ("pessoa", "pessoa_publica"):  # famoso também é pessoa (o tipo antigo pode vir de um log)
            masker.session.protect_name(text, masker.stop)
            decision, reason = "mascarar", "pessoa"
        elif kind == "usuario" and not HANDLE.search(entity["texto"]) and not SOCIAL.search(source):
            # Uma palavra solta, sem @, ponto, _ ou número, num pedido que não fala de rede social: o modelo marcou
            # "o que é o esporte rayrox" (o Hyrox ouvido errado) como usuário, e o provedor só viu um nome falso.
            decision, reason = "manter", "sem forma de nome de usuário e sem rede social no pedido"
        elif kind in ("usuario", "email", "telefone", "documento"):  # o modelo da etapa 4 dá estes tipos; a Gemma, não
            masker.session.protect_literal(entity["texto"])  # inteiro, com pontos e números (align os tiraria)
            decision, reason = "mascarar", "identifica alguém"
        elif kind in ("negocio", "instituicao", "lugar"):
            if wants_search:
                masker.session.release(text)
                decision, reason = "liberar", "precisa ser pesquisado na internet"
            elif known:
                decision, reason = "mascarar", "é um contato e a tarefa não exige pesquisa"
            else:
                decision, reason = "manter", "não está no cofre"
        else:
            decision, reason = "manter", "não identifica ninguém"
        decisions.append({"texto": text, "tipo": kind, "decisao": decision, "motivo": reason})
    return decisions


def apply_screen(found, masker, source):
    decisions = []
    for item in found.get("itens", []):
        text, kind = item["texto"], item["tipo"]
        if kind != "usuario" and URLISH.search(text):
            decisions.append({"texto": text, "tipo": kind, "decisao": "manter",
                              "motivo": "tem a forma de um endereço de site"})
            continue
        if kind == "usuario":
            masker.session.protect_literal(text)
        else:
            text = align(text, source)
            # O que o pedido liberou para pesquisa continua liberado.
            masker.session.protect_name(text, masker.stop, keep_released=True)
        decisions.append({"texto": text, "tipo": kind, "decisao": "mascarar",
                          "motivo": "nome de usuário na tela" if kind == "usuario" else "pessoa na tela"})
    return decisions
