"""Etapa 0 do plano (docs/plano-modelos-pequenos.md): mede a Gemma e o Laya atuais no conjunto congelado (tests/base)
e, em cada erro, diz em que parte do caminho ele aconteceu e onde mexer para corrigir.

Uso (no .venv; o Ollama precisa estar no ar, `ollama serve`; o servidor do Laya é subido se faltar):
    .venv/bin/python -m tests.eval_base                        # tudo
    .venv/bin/python -m tests.eval_base mascaramento            # só uma parte (ou: controles)
    .venv/bin/python -m tests.eval_base --caso wa-grupo ig-menu  # só esses casos, com o caminho inteiro no terminal
    .venv/bin/python -m tests.eval_base --falhas                # repete só o que falhou na última rodada completa
    .venv/bin/python -m tests.eval_base --listar                # ids, app e tela imitada, sem rodar

Saída: reports/base-<data>/relatorio.html e resultados.json. Cada caso é comparado com o último resultado dele numa
rodada anterior, e o relatório mostra o que passou a falhar e o que passou a passar.

O mascaramento roda o caminho do serviço (proxy.judge_task e proxy.judge_screen): regras fixas e cofre, filtro do Laya,
Gemma em blocos, decisões por entidade, troca. Nada vai ao provedor. Os dados são fictícios, então o terminal e o
relatório mostram tudo.
"""

import argparse
import glob
import html
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request

from lmphone import host, local_ai, proxy
from lmphone.executor import MAX_LABEL
from lmphone.masking import Masker, Vault
from lmphone.sources import load_stoplist

from .base.controles import ESCOLHAS
from .base.mascaramento import CASOS, CONTATOS, EMAILS, TELEFONES

OUT_DIR = "reports"
OLLAMA = local_ai.OLLAMA

# Causa de um erro: (nome curto, onde mexer). A ordem é a do caminho de um texto até o provedor.
CAUSES = {
    "leitura": ("O trecho não chegou à IA local",
                "local_ai.screen_fragments: o trecho foi descartado ao ler a tela (sem 3 letras seguidas?)"),
    "filtro_laya": ("O filtro do Laya descartou o trecho",
                    "proxy.GATE (corte) ou a pergunta REVIEW em laya_server.py; no plano, o modelo de marcação substitui o filtro"),
    "ia_erro": ("A chamada à Gemma falhou", "Ollama no ar? tempo limite (proxy.JUDGE_TIMEOUT); resposta fora do esquema"),
    "ia_omitiu": ("A Gemma não achou", "SCREEN_PROMPT ou REQUEST_PROMPT em local_ai.py (instrução, exemplos); no plano, caso para o treino"),
    "ia_parcial": ("A Gemma copiou só parte do trecho", "local_ai.align e o prompt (copiar exatamente)"),
    "ia_tipo": ("A Gemma achou, com o tipo errado", "tipos no REQUEST_PROMPT/SCREEN_PROMPT; local_ai.apply_request decide pelo tipo"),
    "ia_marcou": ("A Gemma marcou o que devia ficar", "prompt (o que não listar); data/stoplist.txt para palavras de interface"),
    "ia_nao_liberou": ("A Gemma não liberou para pesquisa", "REQUEST_PROMPT (intenção, precisa_pesquisa); local_ai.apply_request"),
    "ia_intencao": ("A Gemma errou a intenção do pedido", "REQUEST_PROMPT em local_ai.py"),
    "liberado": ("O pedido liberou a palavra para pesquisa", "local_ai.apply_request (release) e o julgamento do pedido"),
    "stoplist": ("A palavra está na STOPLIST", "masking.STOPLIST ou data/stoplist.txt"),
    "cofre": ("Palavra de um contato do cofre", "masking.Masker.add_name e STOPLIST: palavra comum no nome de um contato"),
    "regra_fixa": ("Regra fixa", "padrões EMAIL, PHONE, HANDLE, CPF, CARD em masking.py"),
    "curto": ("Palavra com menos de 3 letras", "masking.Session.protect_name ignora palavras curtas (decisão de projeto)"),
    "aplicacao": ("A decisão não virou troca (bug)", "local_ai.apply_screen/apply_request e masking.Masker"),
    "outro": ("Causa não identificada", "veja o caminho do caso; talvez o esperado do caso esteja errado"),
    # Escolha de controle
    "limiar": ("O certo foi o mais provável, mas abaixo do limiar", "laya_server.MIN_P (0,5)"),
    "nao_achou": ("O Laya preferiu 'nenhum' ou outro abaixo do limiar", "pergunta em laya_server.pick; no plano, o cross-encoder"),
    "toque_errado": ("O Laya escolheu outro controle (toque errado)", "pergunta em laya_server.pick; MIN_P; no plano, o cross-encoder"),
    "falso_positivo": ("O controle não estava na tela e o Laya tocou outro", "MIN_P e o critério NONE em laya_server.pick"),
    "rotulo_longo": ("O rótulo certo passa de executor.MAX_LABEL e nem foi oferecido", "executor.MAX_LABEL"),
    "laya_erro": ("A chamada ao Laya falhou", "servidor do Laya no ar? logs/laya.out"),
}
WORD = re.compile(r"[^\W\d_]+")


# --- mascaramento ---

def new_masker():
    masker = Masker(Vault(), load_stoplist())
    for name in CONTATOS:
        masker.add_name(name)
    for email in EMAILS:
        masker.vault.add("email", email)
    for phone in TELEFONES:
        masker.add_phone(phone)
    return masker


def laya(path, body=None):
    request = urllib.request.Request(proxy.LAYA + path, data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=proxy.JUDGE_TIMEOUT) as response:
        return json.load(response)


def device_text(fragments):
    """A tela no formato que o serviço manda (device.render), para passar pelo mesmo screen_fragments."""
    lines = [f'{i}. TextView: "{f}" - (0,{i * 100},1080,{i * 100 + 90})' for i, f in enumerate(fragments, 1)]
    return "<device_state>\nCurrent Clickable UI elements:\n" + "\n".join(lines) + "\n</device_state>"


def has_word(word, text):
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.I) is not None


def tokens(text):
    return [t for t in WORD.findall(text)]


def run_masking(case):
    masker, r = new_masker(), {"id": case["id"], "parte": "mascaramento", "caso": case}
    rules = []
    new_masker().mask(case.get("entrada") or " • ".join(case["trechos"]), trace=rules)
    r["regras"] = [list(t) for t in rules]
    if case["tipo"] == "pedido":
        text = case["entrada"]
        try:
            judgment, raw, seconds = local_ai.judge_request(text, proxy.JUDGE_TIMEOUT)
            r["ia"] = [{"fonte": text, "itens": judgment.get("entidades", []), "intencao": judgment.get("intencao"),
                        "bruto": raw, "segundos": round(seconds, 2)}]
            r["decisoes"] = local_ai.apply_request(judgment, masker, text)
        except Exception as e:
            r["ia"], r["decisoes"] = [{"fonte": text, "erro": repr(e)}], []
        r["trechos"] = []
    else:
        text = " • ".join(case["trechos"])
        read = local_ai.screen_fragments(device_text(case["trechos"]))
        r["trechos"] = [{"texto": f, "p": None, "descartado": False} for f in read]
        new = list(read)
        try:
            answer = laya("/private", {"fragments": new})
            for item, p in zip(r["trechos"], answer["p"]):
                item.update(p=p, descartado=p < proxy.GATE)
            new = [i["texto"] for i in r["trechos"] if not i["descartado"]]
            r["laya_segundos"] = answer["seconds"]
        except Exception as e:
            r["erro_laya"] = repr(e)
        r["ia"], r["decisoes"] = [], []
        for batch in local_ai.batches(new):
            source = " • ".join(batch)
            try:
                found, raw, seconds = local_ai.find_private(source, proxy.JUDGE_TIMEOUT)
                r["ia"].append({"fonte": source, "trechos": batch, "itens": found.get("itens", []), "bruto": raw,
                                "segundos": round(seconds, 2)})
                r["decisoes"] += local_ai.apply_screen(found, masker, source)
            except Exception as e:
                r["ia"].append({"fonte": source, "trechos": batch, "erro": repr(e)})
    swaps = []
    sent = masker.mask(text, trace=swaps)
    r.update(enviado=sent, trocas=[list(s) for s in swaps], volta=masker.unmask(sent) == text)
    r["conferencias"] = check_masking(case, r, masker, sent, swaps)
    r["status"] = masking_status(r["conferencias"])
    return r


def masking_status(checks):
    failed = {c["regra"] for c in checks if not c["ok"]}
    return ("vazamento" if failed & {"pessoa", "usuario", "outro"} else "excesso" if failed & {"manter", "liberar"}
            else "intencao" if "intencao" in failed else "ok")


def check_masking(case, r, masker, sent, swaps):
    checks = []
    for name in case["pessoas"]:
        words = [t for t in tokens(name) if len(t) >= 3]
        leaked = [t for t in words if has_word(t, sent)]
        check = {"regra": "pessoa", "alvo": name, "ok": not leaked}
        if leaked:
            check["causas"] = [leak_cause(t, "pessoa", r, masker) for t in leaked]
        checks.append(check)
    for user in case["usuarios"]:
        bare = user.lstrip("@")
        check = {"regra": "usuario", "alvo": user, "ok": bare.casefold() not in sent.casefold()}
        if not check["ok"]:
            check["causas"] = [leak_cause(bare, "usuario", r, masker)]
        checks.append(check)
    for value in case["outros"]:
        check = {"regra": "outro", "alvo": value, "ok": value.casefold() not in sent.casefold()}
        if not check["ok"]:
            check["causas"] = [cause("regra_fixa", f"nenhuma regra fixa casou com «{value}»")]
        checks.append(check)
    for rule in ("liberar", "manter"):
        for value in case[rule]:
            check = {"regra": rule, "alvo": value, "ok": value.casefold() in sent.casefold()}
            if not check["ok"]:
                check["causas"] = excess_causes(value, rule, r, masker, swaps)
            checks.append(check)
    if case["intencao"]:
        got = r["ia"][0].get("intencao") if r["ia"] else None
        check = {"regra": "intencao", "alvo": " ou ".join(case["intencao"]), "obtido": got, "ok": got in case["intencao"]}
        if not check["ok"]:
            check["causas"] = [cause("ia_erro", r["ia"][0]["erro"]) if r["ia"] and "erro" in r["ia"][0]
                               else cause("ia_intencao", f"a Gemma respondeu «{got}»")]
        checks.append(check)
    return checks


def cause(code, detail):
    return {"codigo": code, "detalhe": detail}


def _plain(text):
    return local_ai._plain(text)


def items_with(word, r):
    """Itens da Gemma que citam a palavra (sem acento e caixa): contêm a palavra, ou são um pedaço dela (um nome de
    usuário copiado pela metade)."""
    found, w = [], _plain(word)
    for call in r["ia"]:
        for item in call.get("itens", []):
            text = _plain(item.get("texto", "")).lstrip("@")
            if w in {_plain(t) for t in tokens(text)} or w in text or (len(text) >= 3 and text in w):
                found.append(item)
    return found


def leak_cause(word, kind, r, masker):
    """Por que `word` (palavra de um nome, ou nome de usuário inteiro) saiu sem troca."""
    session, low = masker.session, word.casefold()
    if kind == "pessoa":
        if len(word) < 3:
            return cause("curto", f"«{word}» tem menos de 3 letras")
        if low in masker.stop:
            return cause("stoplist", f"«{word}» está na STOPLIST")
        if low in session.released:
            return cause("liberado", f"o julgamento do pedido liberou «{word}» para pesquisa")
    if r["trechos"]:
        holders = [t for t in r["trechos"] if (has_word(word, t["texto"]) if kind == "pessoa" else low in t["texto"].casefold())]
        if not holders:
            return cause("leitura", f"nenhum trecho lido da tela contém «{word}»")
        if all(t["descartado"] for t in holders):
            t = holders[0]
            return cause("filtro_laya", f"o Laya deu p={t['p']} ao trecho «{t['texto']}» (corte {proxy.GATE}) e ele não foi à Gemma")
        calls = [c for c in r["ia"] if any(t["texto"] in c["trechos"] for t in holders)]
        if calls and all("erro" in c for c in calls):
            return cause("ia_erro", calls[0]["erro"])
    elif r["ia"] and "erro" in r["ia"][0]:
        return cause("ia_erro", r["ia"][0]["erro"])
    found = items_with(word, r)
    if not found:
        return cause("ia_omitiu", f"a Gemma não listou «{word}»")
    item = found[0]
    if kind == "usuario":
        if item["texto"].lstrip("@").casefold() != low:
            return cause("ia_parcial", f"a Gemma listou «{item['texto']}» ({item['tipo']}), não o nome de usuário inteiro «{word}»")
    elif r["caso"]["tipo"] == "pedido" and item.get("tipo") != "pessoa":
        decision = next((d for d in r["decisoes"] if _plain(word) in _plain(d["texto"])), None)
        return cause("ia_tipo", f"a Gemma classificou «{item['texto']}» como {item['tipo']}"
                     + (f" (precisa_pesquisa={item.get('precisa_pesquisa')}); decisão: {decision['decisao']}, {decision['motivo']}" if decision else ""))
    if kind == "pessoa" and low not in session.extra_names:
        return cause("aplicacao", f"a Gemma listou «{item['texto']}» como {item['tipo']}, mas «{word}» não entrou nos nomes a mascarar")
    return cause("aplicacao", f"«{word}» foi marcado ({item['tipo']}), mas a troca não aconteceu no texto")


def excess_causes(value, rule, r, masker, swaps):
    """Por que `value`, que devia sair como está, saiu trocado: as trocas que mexeram nele e de onde cada uma veio."""
    session, causes = masker.session, []
    hits = [s for s in swaps if s[1].casefold() in value.casefold() or value.casefold() in s[1].casefold()]
    for kind, real, _ in hits:
        low = real.casefold()
        if kind not in ("name", "literal"):
            causes.append(cause("regra_fixa", f"a regra fixa de {kind} trocou «{real}»"))
        elif kind == "name" and low in session.extra_names:
            found = items_with(real, r)
            causes.append(cause("ia_marcou", f"a Gemma marcou «{found[0]['texto']}» como {found[0]['tipo']}" if found
                                else f"«{real}» entrou nos nomes a mascarar sem item da Gemma que o cite"))
        elif kind == "name":
            owner = next((c for c in CONTATOS if low in {t.casefold() for t in tokens(c)}), "?")
            if rule == "liberar":
                found = items_with(real, r)
                causes.append(cause("ia_nao_liberou", f"«{real}» é do contato «{owner}» e não foi liberado; a Gemma disse "
                                    + (f"{found[0]['tipo']}, precisa_pesquisa={found[0].get('precisa_pesquisa')}" if found else "nada sobre ele")
                                    + f", intenção {r['ia'][0].get('intencao') if r['ia'] else '?'}"))
            else:
                causes.append(cause("cofre", f"«{real}» é palavra do contato «{owner}» do cofre"))
        else:
            found = items_with(real, r)
            causes.append(cause("ia_marcou" if low in session.extra_literals else "cofre",
                                f"«{real}» virou nome de usuário" + (f" (a Gemma: «{found[0]['texto']}», {found[0]['tipo']})" if found else "")))
    unique = [dict(k) for k in dict.fromkeys(tuple(k.items()) for k in causes)]  # uma por palavra trocada repete a mesma
    return unique or [cause("outro", f"nenhuma troca cita «{value}»; texto enviado: «{r.get('enviado', '')}»")]


# --- escolha de controle ---

def run_pick(case):
    r = {"id": case["id"], "parte": "controles", "caso": case}
    offered = list(dict.fromkeys(l for l in case["tela"] if len(l) <= MAX_LABEL))
    try:
        answer = laya("/pick", {"wanted": case["pedidos"], "labels": offered})
    except Exception as e:
        r.update(status="erro", causas=[cause("laya_erro", repr(e))])
        return r
    r.update(escolhido=answer["label"], p=answer["p"], ranking=answer.get("ranking"), segundos=answer["seconds"])
    r["status"], r["causas"] = pick_status(case, answer, offered)
    return r


def rights(case):
    """Os rótulos certos de uma escolha: um, ou vários quando o mesmo controle aparece como mais de um elemento
    (a etiqueta da linha e o texto dela)."""
    right = case["certo"]
    return () if right is None else tuple(right) if isinstance(right, (list, tuple)) else (right,)


def pick_status(case, answer, offered):
    chosen, ranking = answer["label"], answer.get("ranking") or []
    if case["certo"] is None and chosen is None or chosen in rights(case):
        return "ok", []
    if case["certo"] is None:
        return "falso_positivo", [cause("falso_positivo", f"tocaria «{chosen}» (p={answer['p']})")]
    if not any(r in offered for r in rights(case)):
        return "nao_achou", [cause("rotulo_longo", f"«{rights(case)[0]}» tem mais de {MAX_LABEL} caracteres")]
    place = next((i for i, (label, _) in enumerate(ranking) if label in rights(case)), None)
    right = ranking[place][0] if place is not None else rights(case)[0]
    p_right = ranking[place][1] if place is not None else None
    if chosen is not None:
        return "toque_errado", [cause("toque_errado", f"tocaria «{chosen}» (p={answer['p']}); o certo ficou em {place + 1}º com p={p_right}"
                                      if place is not None else f"tocaria «{chosen}» (p={answer['p']})")]
    if place == 0:
        return "nao_achou", [cause("limiar", f"«{right}» foi o mais provável com p={p_right}, abaixo de 0,5")]
    return "nao_achou", [cause("nao_achou", f"«{right}» ficou em {place + 1}º com p={p_right}; o primeiro foi «{ranking[0][0]}» ({ranking[0][1]})"
                               if place is not None else "sem ranking (reinicie o Laya: ./run.sh --stop-laya)")]


# --- ambiente ---

def get_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


NEW = None  # URL do servidor dos modelos da etapa 4, com --novo


def use_new_models(url):
    """Troca a Gemma e o Laya pelo servidor da etapa 4: o mesmo caminho do serviço, com outras respostas."""
    global NEW
    NEW = url
    proxy.LAYA = url

    def call(path, text):
        request = urllib.request.Request(url + path, data=json.dumps({"text": text}).encode())
        with urllib.request.urlopen(request, timeout=proxy.JUDGE_TIMEOUT) as response:
            answer = json.load(response)
        return answer, json.dumps(answer, ensure_ascii=False), answer.pop("seconds")

    local_ai.find_private = lambda text, timeout=None: call("/entities", text)
    local_ai.judge_request = lambda text, timeout=None: call("/judge", text)


def ensure_services(parts):
    """O Ollama precisa estar no ar; o Laya é subido como no run.sh. Devolve a descrição do ambiente."""
    env = {"commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "alterado": bool(subprocess.run(["git", "status", "--porcelain", "lmphone"], capture_output=True, text=True).stdout.strip()),
           "gate": proxy.GATE, "max_label": MAX_LABEL}
    if NEW:
        try:
            info = get_json(NEW + "/")
        except Exception:
            sys.exit(f"o servidor dos modelos novos não responde em {NEW}: rode tools.treino.servidor no .venv-treino")
        env["novo"] = f"{info['model']} (limiar {info['min_p']})"
        env["laya"] = env["gemma"] = "substituídos por --novo"
        return env
    if "mascaramento" in parts:
        try:
            tags = get_json(f"{OLLAMA}/api/tags")["models"]
        except Exception:
            sys.exit("Ollama fora do ar: rode `ollama serve` (o mascaramento precisa da Gemma).")
        model = next((m for m in tags if m["name"].split(":")[0] == local_ai.MODEL), None)
        if not model:
            sys.exit(f"o Ollama não tem {local_ai.MODEL}: rode ./run.sh uma vez para criá-lo.")
        env["gemma"] = f"{local_ai.MODEL} ({model['digest'][:12]})"
    try:
        info = get_json(proxy.LAYA + "/")
    except Exception:
        print("subindo o servidor do Laya…", flush=True)
        os.makedirs("logs", exist_ok=True)
        with open("logs/laya.pid", "w") as f:
            f.write(str(host.spawn([host.venv_python(".venv-laya"), "-u", "-m", "lmphone.laya_server"], "logs/laya.out")))
        for _ in range(240):
            time.sleep(0.5)
            try:
                info = get_json(proxy.LAYA + "/")
                break
            except Exception:
                pass
        else:
            sys.exit("o servidor do Laya não subiu; veja logs/laya.out")
    if str(info.get("model", "")).startswith("modelos pequenos"):
        sys.exit("na porta do Laya estão os modelos pequenos (o padrão do run): rode ./run.sh --stop-laya e repita, "
                 "ou avalie-os com --novo http://127.0.0.1:8788")
    if "model" not in info:
        sys.exit("o servidor do Laya no ar é de antes do diagnóstico (sem ranking): rode ./run.sh --stop-laya e repita.")
    env["laya"] = f"{info['model']} (MIN_P {info['min_p']})"
    return env


def memory():
    from .phone_suite import ram_sample
    ram, _ = ram_sample()
    return {"laya_mb": round(ram["laya"]), "ollama_mb": round(ram["ollama"])}


# --- rodada anterior ---

def previous_results():
    """Último status de cada caso nas rodadas anteriores, e o caminho da última rodada completa."""
    last, full = {}, None
    for path in sorted(glob.glob(os.path.join(OUT_DIR, "base-*", "resultados.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for r in data["resultados"]:
            last[r["id"]] = {"status": r["status"], "rodada": data["rodada"]}
        if not data.get("parcial"):
            full = data
    return last, full


# --- terminal ---

def describe(r):
    """O caminho inteiro de um caso, em texto (--caso)."""
    case, out = r["caso"], []
    out.append(f"== {r['id']} ({case['app']}; {case.get('onde', '')}) -> {r['status']}")
    if case.get("nota"):
        out.append(f"   nota: {case['nota']}")
    if r["parte"] == "controles":
        out.append(f"   pedidos: {case['pedidos']}  certo: {' ou '.join(rights(case)) or None}")
        out.append(f"   escolhido: {r.get('escolhido')} (p={r.get('p')}, {r.get('segundos')} s)")
        for label, p in (r.get("ranking") or [])[:6]:
            out.append(f"     {p:5.3f}  {label}")
    else:
        out.append(f"   entrada: {case.get('entrada') or ' • '.join(case['trechos'])}")
        if r["regras"]:
            out.append("   regras fixas: " + ", ".join(f"{k}:{real}" for k, real, _ in r["regras"]))
        for t in r["trechos"]:
            out.append(f"     laya p={t['p']!s:5} {'DESCARTADO ' if t['descartado'] else ''}{t['texto']}")
        for call in r["ia"]:
            out.append(f"   gemma <- {call['fonte']}")
            out.append(f"   gemma -> {call.get('bruto') or call.get('erro')}  ({call.get('segundos', '?')} s)")
        for d in r["decisoes"]:
            out.append(f"   decisão: {d['decisao']} {d['texto']} ({d['tipo']}; {d['motivo']})")
        out.append(f"   enviado: {r['enviado']}")
    for c in r.get("conferencias", []):
        if not c["ok"]:
            out.append(f"   x {c['regra']}: {c['alvo']}")
            for k in c.get("causas", []):
                out.append(f"       [{k['codigo']}] {k['detalhe']}")
    for k in r.get("causas", []):
        out.append(f"   [{k['codigo']}] {k['detalhe']}")
    return "\n".join(out)


def causes_of(r):
    return [k for c in r.get("conferencias", []) if not c["ok"] for k in c.get("causas", [])] + r.get("causas", [])


# --- números ---

def summary(results):
    masks = [r for r in results if r["parte"] == "mascaramento"]
    picks = [r for r in results if r["parte"] == "controles"]
    s = {}
    if masks:
        checks = [c for r in masks for c in r["conferencias"]]
        for rule in ("pessoa", "usuario", "outro", "manter", "liberar", "intencao"):
            mine = [c for c in checks if c["regra"] == rule]
            s[rule] = [sum(c["ok"] for c in mine), len(mine)]
        s["casos_ok"] = [sum(r["status"] == "ok" for r in masks), len(masks)]
        s["vazamentos"] = sum(r["status"] == "vazamento" for r in masks)
        times = [c["segundos"] for r in masks for c in r["ia"] if "segundos" in c]
        s["gemma_s"] = [round(statistics.mean(times), 2), round(max(times), 2)] if times else None
        frags = [t for r in masks for t in r["trechos"]]
        s["filtrados"] = [sum(t["descartado"] for t in frags), len(frags)]
    if picks:
        present = [r for r in picks if r["caso"]["certo"]]
        absent = [r for r in picks if not r["caso"]["certo"]]
        s["presentes"] = [sum(r["status"] == "ok" for r in present), len(present)]
        s["ausentes"] = [sum(r["status"] == "ok" for r in absent), len(absent)]
        s["toques_errados"] = sum(r["status"] in ("toque_errado", "falso_positivo") for r in picks)
        real = [r for r in picks if r["caso"].get("conferido")]
        s["conferidos"] = [sum(r["status"] == "ok" for r in real), len(real)]
        times = [r["segundos"] for r in picks if "segundos" in r]
        s["laya_s"] = [round(statistics.mean(times), 2), round(max(times), 2)] if times else None
    counts = {}
    for r in results:
        for k in causes_of(r):
            counts.setdefault(k["codigo"], []).append(r["id"])
    s["causas"] = {code: sorted(set(ids)) for code, ids in sorted(counts.items(), key=lambda kv: -len(set(kv[1])))}
    return s


# --- relatório ---

def esc(value):
    return html.escape(str(value), quote=True)


def mark(text, needles, css):
    needles = sorted({n for n in needles if n}, key=len, reverse=True)
    if not needles:
        return esc(text)
    pattern = re.compile("|".join(re.escape(n) for n in needles), re.I)
    out, last = [], 0
    for m in pattern.finditer(text):
        out += [esc(text[last:m.start()]), f'<mark class="{css}">{esc(m.group())}</mark>']
        last = m.end()
    return "".join(out) + esc(text[last:])


STATUS = {"ok": "Passou", "vazamento": "Vazamento", "excesso": "Mascarou demais", "intencao": "Intenção errada",
          "nao_achou": "Não achou", "toque_errado": "Toque errado", "falso_positivo": "Tocaria sem estar na tela", "erro": "Erro"}
RULE = {"pessoa": "Pessoa não pode sair", "usuario": "Usuário não pode sair", "outro": "Dado não pode sair",
        "manter": "Precisa ficar", "liberar": "Precisa sair real (pesquisa)", "intencao": "Intenção"}


def render_causes(causes):
    return "".join(f"<li class='cause'><span class='code'>{esc(k['codigo'])}</span> {esc(k['detalhe'])}"
                   f"<br><span class='where'>Onde mexer: {esc(CAUSES[k['codigo']][1])}</span></li>" for k in causes)


def render_case(r, before):
    case = r["caso"]
    rerun = f"{host.venv_python('.venv')} -m tests.eval_base --caso {case['id']}"
    capture = f"{host.venv_python('.venv')} -m tests.captura {case['id']}"
    change = ""
    if before and before["status"] != r["status"]:
        change = f"<span class='chg'>antes: {esc(STATUS.get(before['status'], before['status']))}</span>"
    if r["parte"] == "controles":
        right = " ou ".join(rights(case)) or "nenhum"
        rows = "".join(f"<tr class='{'right' if label in rights(case) else 'chosen' if label == r.get('escolhido') else ''}'>"
                       f"<td class='n'>{p:.3f}</td><td>{esc(label)}</td></tr>" for label, p in (r.get("ranking") or []))
        body = (f"<li><h3>Pedidos do plano</h3><p class='text'>{esc(' | '.join(case['pedidos']))}</p></li>"
                f"<li><h3>Resposta do Laya <span class='hint'>certo: {esc(right)}; escolhido: "
                f"{esc(r.get('escolhido') or 'nenhum')} (p={esc(r.get('p'))}, {esc(r.get('segundos'))} s)</span></h3>"
                f"<div class='tw'><table><thead><tr><th>p</th><th>Rótulo</th></tr></thead><tbody>{rows}</tbody></table></div></li>")
        checks = f"<ul class='checks'>{render_causes(r.get('causas', []))}</ul>" if r["status"] != "ok" else "<p class='none'>Escolha certa.</p>"
        body += f"<li><h3>Conferência</h3>{checks}</li>"
        title = f"{' | '.join(case['pedidos'])} → {right}"
    else:
        leaked = [c["alvo"] for c in r["conferencias"] if not c["ok"] and c["regra"] in ("pessoa", "usuario", "outro")]
        source = case.get("entrada") or " • ".join(case["trechos"])
        body = f"<li><h3>Entrada <span class='hint'>{'pedido' if case['tipo'] == 'pedido' else 'trechos da tela, na ordem'}</span></h3><p class='text'>{mark(source, leaked, 'real')}</p></li>"
        rules = ", ".join(f"{k}: {real}" for k, real, _ in r["regras"]) or "nenhuma"
        body += f"<li><h3>Regras fixas e cofre</h3><p>{esc(rules)}</p></li>"
        if r["trechos"]:
            rows = "".join(f"<tr class='{'drop' if t['descartado'] else ''}'><td class='n'>{esc(t['p'])}</td><td>{esc(t['texto'])}</td>"
                           f"<td>{'descartado' if t['descartado'] else 'vai à Gemma'}</td></tr>" for t in r["trechos"])
            body += (f"<li><h3>Filtro do Laya <span class='hint'>p de citar pessoa; abaixo de {proxy.GATE} não vai à Gemma</span></h3>"
                     f"<div class='tw'><table><tbody>{rows}</tbody></table></div></li>")
        calls = "".join(
            f"<div class='call'><p class='hint'>Entrada</p><pre>{esc(c['fonte'])}</pre><p class='hint'>Resposta "
            f"({esc(c.get('segundos', '?'))} s)</p><pre>{esc(c.get('bruto') or c.get('erro'))}</pre></div>" for c in r["ia"])
        body += f"<li><h3>Gemma</h3>{calls or '<p class=none>Nada foi à Gemma.</p>'}</li>"
        decisions = "".join(f"<li><span class='dec {esc(d['decisao'])}'>{esc(d['decisao'])}</span> <strong>{esc(d['texto'])}</strong> "
                            f"<span class='hint'>{esc(d['tipo'])}; {esc(d['motivo'])}</span></li>" for d in r["decisoes"])
        body += f"<li><h3>Decisões</h3><ul class='plain'>{decisions or '<li class=none>Nenhuma.</li>'}</ul></li>"
        body += f"<li><h3>Texto que o provedor recebe</h3><p class='text sent'>{mark(r['enviado'], [s[2] for s in r['trocas']], 'fake')}</p></li>"
        checks = "".join(
            f"<li class='{'pass' if c['ok'] else 'fail'}'><span class='mk'>{'✓' if c['ok'] else '✗'}</span> {esc(RULE[c['regra']])}: "
            f"<strong>{esc(c['alvo'])}</strong>{' (respondeu ' + esc(c.get('obtido')) + ')' if c['regra'] == 'intencao' and not c['ok'] else ''}"
            f"<ul class='plain'>{render_causes(c.get('causas', []))}</ul></li>" for c in r["conferencias"])
        body += f"<li><h3>Conferência</h3><ul class='checks'>{checks}</ul></li>"
        title = source
    note = f"<p class='note'>{esc(case['nota'])}</p>" if case.get("nota") else ""
    tools = (f"<div class='tools'><p><strong>Repetir só este caso</strong>, com o caminho no terminal: <code>{esc(rerun)}</code></p>"
             f"<p><strong>Conferir no aparelho</strong> se o erro pode ser do caso (a tela real é diferente): abra "
             f"<em>{esc(case['onde'])}</em> e rode <code>{esc(capture)}</code>. O print e o texto da tela ficam em "
             f"data/capturas/, só no notebook; têm dados reais.</p></div>") if r["status"] != "ok" else ""
    return f"""
<details class="case s-{esc(r['status'])}" data-status="{'ok' if r['status'] == 'ok' else 'falha'}" data-parte="{r['parte']}" data-causas="{esc(' '.join(sorted({k['codigo'] for k in causes_of(r)})))}" id="{esc(case['id'])}">
  <summary><span class="status">{esc(STATUS.get(r['status'], r['status']))}</span><code class="cid">{esc(case['id'])}</code>{change}
    <span class="title">{esc(title)}</span><span class="group">{esc(case['app'])} · {esc(case.get('onde', ''))}{' · tela conferida no aparelho' if case.get('conferido') else ''}</span></summary>
  <div class="body">{note}<ol class="steps">{body}</ol>{tools}</div>
</details>"""


CSS = """
:root { --bg:#f2f5f3; --fg:#16211d; --muted:#586661; --surface:#fff; --line:#c5d0cb; --ok:#1d6b4f; --ok-soft:#dcefe6;
  --bad:#b3261e; --bad-soft:#f9dedb; --warn:#8a5a00; --warn-soft:#f6e8c9; --fake:#dfe6f7;
  --body:"IBM Plex Sans",system-ui,sans-serif; --mono:"IBM Plex Mono",ui-monospace,monospace; --display:"Bricolage Grotesque",system-ui,sans-serif; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0e1513; --fg:#e3ebe7; --muted:#94a39d; --surface:#18221f;
  --line:#33423d; --ok:#6fd3a8; --ok-soft:#16332a; --bad:#ff8a80; --bad-soft:#3d1a17; --warn:#f0c060; --warn-soft:#3a2e12; --fake:#233052; color-scheme:dark; } }
:root[data-theme="dark"] { --bg:#0e1513; --fg:#e3ebe7; --muted:#94a39d; --surface:#18221f; --line:#33423d; --ok:#6fd3a8; --ok-soft:#16332a;
  --bad:#ff8a80; --bad-soft:#3d1a17; --warn:#f0c060; --warn-soft:#3a2e12; --fake:#233052; color-scheme:dark; }
body { background:var(--bg); color:var(--fg); font:15px/1.55 var(--body); margin:0; padding:40px 16px 64px; }
main { max-width:1040px; margin:0 auto; display:flex; flex-direction:column; gap:28px; }
h1 { font:700 clamp(26px,5vw,36px)/1.1 var(--display); margin:0; } h2 { font:600 20px/1.2 var(--display); margin:0; }
h3 { font:600 14px/1.3 var(--body); margin:0 0 6px; } p { margin:0; max-width:75ch; }
.hint, .none, .lede { color:var(--muted); font-weight:400; } .hint { font-size:13px; }
section { display:flex; flex-direction:column; gap:12px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; }
.tile { background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:12px 14px; }
.tile b { display:block; font:700 26px/1.1 var(--display); font-variant-numeric:tabular-nums; } .tile span { font-size:13px; color:var(--muted); }
.tile.bad b { color:var(--bad); } .tile.ok b { color:var(--ok); }
.tw { overflow-x:auto; } table { border-collapse:collapse; width:100%; font-size:14px; }
th, td { text-align:left; padding:6px 12px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
th { font:500 11.5px var(--mono); text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
td.n { font-variant-numeric:tabular-nums; white-space:nowrap; font-family:var(--mono); }
tr.drop td { color:var(--muted); text-decoration:line-through; } tr.right td { background:var(--ok-soft); } tr.chosen td { background:var(--bad-soft); }
.filters { display:flex; flex-wrap:wrap; gap:8px; }
.filters button { font:500 13px var(--body); color:var(--fg); background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:5px 13px; cursor:pointer; }
.filters button[aria-pressed="true"] { background:var(--fg); color:var(--bg); }
.case { background:var(--surface); border:1px solid var(--line); border-radius:6px; margin-bottom:6px; }
.case > summary { display:flex; flex-wrap:wrap; gap:4px 10px; align-items:baseline; padding:10px 14px; cursor:pointer; }
.status { font:500 11.5px var(--mono); padding:2px 8px; border-radius:4px; background:var(--bad-soft); color:var(--bad); white-space:nowrap; }
.s-ok .status { background:var(--ok-soft); color:var(--ok); } .s-excesso .status, .s-intencao .status, .s-nao_achou .status { background:var(--warn-soft); color:var(--warn); }
.cid { font:12px var(--mono); color:var(--muted); } .chg { font:500 11.5px var(--mono); color:var(--warn); }
.title { flex-basis:100%; font-weight:500; overflow-wrap:anywhere; } .group { flex-basis:100%; font-size:13px; color:var(--muted); }
.body { border-top:1px solid var(--line); padding:14px 16px 16px; display:flex; flex-direction:column; gap:12px; }
.steps { margin:0; padding-left:22px; display:flex; flex-direction:column; gap:14px; } .steps > li { min-width:0; }
.text { font:13.5px/1.6 var(--mono); background:var(--bg); border:1px solid var(--line); border-radius:4px; padding:8px 10px; max-width:none; overflow-wrap:anywhere; }
.text.sent { border-color:var(--fg); }
pre { font:12.5px/1.5 var(--mono); background:var(--bg); border:1px solid var(--line); border-radius:4px; padding:8px 10px; margin:4px 0 8px; white-space:pre-wrap; overflow-wrap:anywhere; }
mark { color:inherit; border-radius:3px; padding:0 2px; } mark.real { background:var(--bad-soft); } mark.fake { background:var(--fake); }
ul.checks, ul.plain { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:5px; }
.checks .fail { color:var(--bad); } .checks .mk { display:inline-block; width:16px; font-weight:700; } .checks .pass .mk { color:var(--ok); }
.cause { color:var(--fg); margin:4px 0 0 16px; font-size:14px; } .code { font:500 11.5px var(--mono); background:var(--bg); border:1px solid var(--line); border-radius:4px; padding:1px 6px; }
.where { color:var(--muted); font-size:13px; }
.dec { font:500 11.5px var(--mono); padding:1px 7px; border-radius:4px; background:var(--bg); border:1px solid var(--line); }
.dec.mascarar { background:var(--bad-soft); } .dec.liberar { background:var(--ok-soft); }
.note { font-size:14px; color:var(--warn); } .tools { font-size:13.5px; display:flex; flex-direction:column; gap:6px; border-top:1px dashed var(--line); padding-top:10px; }
code { font:12.5px var(--mono); overflow-wrap:anywhere; }
a { color:inherit; }
"""


def render(results, s, env, started, previous, partial):
    tiles = []
    if "pessoa" in s:
        rec = lambda k: f"{s[k][0]} de {s[k][1]}"
        tiles += [("bad" if s["vazamentos"] else "ok", s["vazamentos"], "casos com vazamento"),
                  ("", rec("pessoa"), "pessoas mascaradas"), ("", rec("usuario"), "nomes de usuário mascarados"),
                  ("", rec("outro"), "e-mails, telefones e documentos"), ("", rec("manter"), "textos que deviam ficar e ficaram"),
                  ("", rec("liberar"), "liberados para pesquisa"), ("", rec("intencao"), "intenções certas"),
                  ("", f"{s['filtrados'][0]} de {s['filtrados'][1]}", "trechos descartados pelo filtro do Laya")]
        if s.get("gemma_s"):
            tiles.append(("", f"{s['gemma_s'][0]} s", f"por chamada à Gemma (pior {s['gemma_s'][1]} s)"))
    if "presentes" in s:
        tiles += [("", f"{s['presentes'][0]} de {s['presentes'][1]}", "controles presentes achados"),
                  ("", f"{s['ausentes'][0]} de {s['ausentes'][1]}", "ausentes respondidos como nenhum"),
                  ("bad" if s["toques_errados"] else "ok", s["toques_errados"], "toques errados"),
                  ("", f"{s['conferidos'][0]} de {s['conferidos'][1]}", "certos nas telas conferidas no aparelho")]
        if s.get("laya_s"):
            tiles.append(("", f"{s['laya_s'][0]} s", f"por escolha do Laya (pior {s['laya_s'][1]} s)"))
    if env.get("memoria"):
        tiles.append(("", f"{env['memoria']['ollama_mb'] + env['memoria']['laya_mb']} MB",
                      f"Ollama {env['memoria']['ollama_mb']} + Laya {env['memoria']['laya_mb']} no fim"))
    tiles_html = "".join(f"<div class='tile {c}'><b>{esc(v)}</b><span>{esc(t)}</span></div>" for c, v, t in tiles)
    cause_rows = "".join(
        f"<tr><td><code>{esc(code)}</code></td><td>{esc(CAUSES[code][0])}</td><td class='n'>{len(ids)}</td>"
        f"<td>{', '.join(f'<a href=\"#{esc(i)}\">{esc(i)}</a>' for i in ids)}</td><td class='hint'>{esc(CAUSES[code][1])}</td></tr>"
        for code, ids in s["causas"].items())
    changed = [(r["id"], previous[r["id"]]["status"], r["status"]) for r in results
               if r["id"] in previous and previous[r["id"]]["status"] != r["status"]]
    change_html = ("<ul class='plain'>" + "".join(
        f"<li><a href='#{esc(i)}'>{esc(i)}</a>: {esc(STATUS.get(a, a))} → <strong>{esc(STATUS.get(b, b))}</strong></li>"
        for i, a, b in changed) + "</ul>") if changed else "<p class='none'>Nenhum caso mudou de resultado (ou não há rodada anterior).</p>"
    apps = {}
    for r in results:
        a = apps.setdefault(r["caso"]["app"], [0, 0])
        a[0] += r["status"] == "ok"
        a[1] += 1
    app_rows = "".join(f"<tr><td>{esc(a)}</td><td class='n'>{ok} de {n}</td></tr>" for a, (ok, n) in sorted(apps.items(), key=lambda kv: kv[1][0] / kv[1][1]))
    failures = [r for r in results if r["status"] != "ok"]
    cases = "".join(render_case(r, previous.get(r["id"])) for r in failures + [r for r in results if r["status"] == "ok"])
    env_line = " · ".join(f"{k}: {v}" for k, v in env.items() if k != "memoria")
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Linha de base</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<main>
<header><h1>Linha de base da IA local</h1>
<p class="lede">{'Rodada parcial: ' if partial else ''}{len(results)} casos do conjunto congelado (tests/base), em {esc(started)}. {esc(env_line)}.
Cada erro diz em que parte do caminho aconteceu e onde mexer; as falhas vêm primeiro.</p></header>
<section><div class="tiles">{tiles_html}</div></section>
<section><h2>Causas dos erros</h2><div class="tw"><table><thead><tr><th>Código</th><th>Causa</th><th>Casos</th><th>Quais</th><th>Onde mexer</th></tr></thead>
<tbody>{cause_rows or '<tr><td colspan=5 class=none>Nenhum erro.</td></tr>'}</tbody></table></div></section>
<section><h2>Mudanças desde a rodada anterior</h2>{change_html}</section>
<section><h2>Por app</h2><div class="tw"><table><thead><tr><th>App</th><th>Passaram</th></tr></thead><tbody>{app_rows}</tbody></table></div></section>
<section><h2>Casos</h2>
<div class="filters" role="group" aria-label="Filtrar">
<button type="button" data-f="todos" aria-pressed="false">Todos ({len(results)})</button>
<button type="button" data-f="falha" aria-pressed="true">Só falhas ({len(failures)})</button>
<button type="button" data-f="mascaramento" aria-pressed="false">Mascaramento</button>
<button type="button" data-f="controles" aria-pressed="false">Controles</button></div>
<div class="cases">{cases}</div></section>
</main>
<script>
(function () {{
  var cases = [].slice.call(document.querySelectorAll('.case')), buttons = [].slice.call(document.querySelectorAll('[data-f]'));
  function apply(f) {{
    buttons.forEach(function (b) {{ b.setAttribute('aria-pressed', b.dataset.f === f ? 'true' : 'false'); }});
    cases.forEach(function (c) {{ c.hidden = !(f === 'todos' || c.dataset.status === f || c.dataset.parte === f); }});
  }}
  buttons.forEach(function (b) {{ b.addEventListener('click', function () {{ apply(b.dataset.f); }}); }});
  apply('falha');
  function openHash() {{ var c = document.getElementById(location.hash.slice(1)); if (c) {{ c.hidden = false; c.open = true; c.scrollIntoView(); }} }}
  window.addEventListener('hashchange', openHash); openHash();
}})();
</script>
"""


# --- principal ---

def main():
    parser = argparse.ArgumentParser(description="Linha de base da IA local no conjunto congelado (tests/base).")
    parser.add_argument("parte", nargs="?", choices=["mascaramento", "controles"])
    parser.add_argument("--caso", nargs="+", metavar="ID", help="só estes casos, com o caminho inteiro no terminal")
    parser.add_argument("--falhas", action="store_true", help="só o que falhou na última rodada completa")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--novo", metavar="URL", help="modelos da etapa 4 (tools/treino/servidor.py, ex.: http://127.0.0.1:8790) "
                        "no lugar da Gemma e do Laya")
    options = parser.parse_args()
    if options.novo:
        use_new_models(options.novo.rstrip("/"))
    else:
        local_ai.BACKEND = "gemma"  # a linha de base é a Gemma e o Laya, mesmo com os modelos pequenos como padrão

    selected = [("mascaramento", c) for c in CASOS] + [("controles", c) for c in ESCOLHAS]
    if options.listar:
        for part, c in selected:
            print(f"{c['id']:28} {part:13} {c['app']:14} {c.get('onde', '')}")
        return
    previous, full = previous_results()
    if options.parte:
        selected = [(p, c) for p, c in selected if p == options.parte]
    if options.caso:
        unknown = set(options.caso) - {c["id"] for _, c in selected}
        if unknown:
            sys.exit(f"casos desconhecidos: {', '.join(sorted(unknown))} (veja --listar)")
        selected = [(p, c) for p, c in selected if c["id"] in options.caso]
    if options.falhas:
        if not full:
            sys.exit("não há rodada completa anterior em reports/base-*")
        failed = {r["id"] for r in full["resultados"] if r["status"] != "ok"}
        selected = [(p, c) for p, c in selected if c["id"] in failed]
    partial = bool(options.parte or options.caso or options.falhas)

    env = ensure_services({p for p, _ in selected})
    started = time.strftime("%d/%m/%Y %H:%M")
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    results = []
    try:
        for i, (part, case) in enumerate(selected, 1):
            r = run_masking(case) if part == "mascaramento" else run_pick(case)
            results.append(r)
            before = previous.get(case["id"])
            mark_change = f"  (antes: {before['status']})" if before and before["status"] != r["status"] else ""
            codes = ", ".join(sorted({k["codigo"] for k in causes_of(r)}))
            print(f"{i:3} {r['status']:15} {case['id']:28} {codes}{mark_change}", flush=True)
            if options.caso:
                print(describe(r) + "\n")
    except KeyboardInterrupt:
        print("interrompida; o relatório cobre o que já rodou")
        partial = True
    env["memoria"] = memory()
    s = summary(results)
    folder = os.path.join(OUT_DIR, f"base-{stamp}")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "resultados.json"), "w", encoding="utf-8") as f:
        json.dump({"rodada": stamp, "parcial": partial, "ambiente": env, "resumo": s, "resultados": results}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "relatorio.html"), "w", encoding="utf-8") as f:
        f.write(render(results, s, env, started, previous, partial))

    print()
    if "pessoa" in s:
        print(f"mascaramento: {s['casos_ok'][0]} de {s['casos_ok'][1]} casos; pessoas {s['pessoa'][0]}/{s['pessoa'][1]}, "
              f"usuários {s['usuario'][0]}/{s['usuario'][1]}, outros {s['outro'][0]}/{s['outro'][1]}, manter {s['manter'][0]}/{s['manter'][1]}, "
              f"liberar {s['liberar'][0]}/{s['liberar'][1]}, intenção {s['intencao'][0]}/{s['intencao'][1]}")
    if "presentes" in s:
        print(f"controles: presentes {s['presentes'][0]}/{s['presentes'][1]}, ausentes {s['ausentes'][0]}/{s['ausentes'][1]}, "
              f"toques errados {s['toques_errados']}; nas telas conferidas no aparelho {s['conferidos'][0]}/{s['conferidos'][1]}")
    for code, ids in s["causas"].items():
        print(f"  {code:15} {len(ids):3}  {CAUSES[code][0]}: {', '.join(ids[:8])}{' …' if len(ids) > 8 else ''}")
    print(f"memória no fim: Ollama {env['memoria']['ollama_mb']} MB, Laya {env['memoria']['laya_mb']} MB")
    print(f"relatório: {folder}/relatorio.html")


if __name__ == "__main__":
    main()
