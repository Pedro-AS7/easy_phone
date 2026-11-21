"""Gera o diagrama de uma tarefa a partir de logs/proxy.jsonl.

Uso: python -m lmphone.trace [sessão]     (sem argumento: a última tarefa do log)
Saída: reports/tarefa-<sessão>.html

O log só tem texto já mascarado, então o diagrama mostra a tarefa como o provedor a viu.
"""

import html
import json
import os
import re
import sys

from .local_ai import screen_fragments

LOG_PATH = "logs/proxy.jsonl"

KINDS = {"name": "nome", "literal": "usuário", "handle": "@usuário", "email": "e-mail", "phone": "telefone",
         "card": "cartão", "cpf": "CPF", "cnpj": "CNPJ", "cep": "CEP", "code": "documento ou placa"}
# Trocas de nome demais num só envio costumam ser palavra comum marcada como pessoa.
MANY_NAMES = 10

esc = html.escape


def load(session=None):
    with open(LOG_PATH, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    rows = [r for r in rows if "ts" in r]
    if session is None:
        session = next(r["session"] for r in reversed(rows) if "request" in r)
    return session, [r for r in rows if r["session"] == session]


def text_of(message):
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content


def build(rows):
    """Devolve (tarefa, julgamento do pedido, chamadas, passos locais, faixas da linha do tempo, início, fim).

    No modo local cada pedido do Mobilerun vira um registro "exec"; as chamadas ao provedor
    (plano e ajuda) acontecem dentro de um passo e ficam guardadas nele.
    """
    task = next((r["task"] for r in rows if "task" in r), "")
    judge = next((r for r in rows if "local_ai" in r), None)
    calls, by_number, pending, execs, inside = [], {}, [], [], []
    local = any("exec" in r for r in rows)
    for r in rows:
        if "local_ai_tela" in r:
            pending.append(r)
        elif "sent" in r:
            call = {"n": r["request"], "sent": r, "screens": pending, "answer": None}
            pending = []
            calls.append(call)
            inside.append(call)
            by_number[r["request"]] = call
        elif "exec" in r:
            execs.append({"row": r, "calls": inside})
            inside = []
        elif "request" in r:
            by_number[r["request"]]["answer"] = r

    start = rows[0]["ts"] - (judge["local_ai"].get("seconds", 0) if judge else 0)
    spans = []  # (faixa, início, fim, rótulo)
    if judge and "seconds" in judge["local_ai"]:
        spans.append(("local", start, judge["ts"], "Julgar o pedido"))
    previous_end = start
    for step in execs:
        row = step["row"]
        what = "Subir o agente e ler a tela" if step is execs[0] else "Executar a ação e ler a tela"
        spans.append(("phone", previous_end, row["arrived"], what))
        if row["exec"].get("ia_seconds"):
            spans.append(("local", row["ts"] - row["exec"]["ia_seconds"], row["ts"], "Achar o controle com outro nome"))
        previous_end = row["ts"]
    for call in calls:
        sent, answer = call["sent"], call["answer"]
        what = "Subir o agente e ler a tela" if call is calls[0] else "Executar a ação e ler a tela"
        if not local:
            spans.append(("phone", previous_end, sent["arrived"], what))
        for screen in call["screens"]:
            info = screen["local_ai_tela"]
            spans.append(("local", screen["ts"] - info["seconds"], screen["ts"],
                          f"Julgar {info['trechos']} trechos novos de tela (chamada {call['n']})"))
        seconds = answer.get("seconds", 0) if answer else 0
        spans.append(("provider", sent["ts"], sent["ts"] + seconds, f"Chamada {call['n']} ao provedor"))
        if not local:
            previous_end = sent["ts"] + seconds
    end = max([rows[-1]["ts"], previous_end])
    return task, judge, calls, execs, spans, start, end


def actions_of(text):
    """Chamadas de ferramenta que o provedor pediu: [(nome, {parâmetro: valor})]."""
    found = []
    for name, body in re.findall(r'<invoke name="([\w.-]+)">(.*?)</invoke>', text, re.S):
        found.append((name, dict(re.findall(r'<parameter name="([\w.-]+)">(.*?)</parameter>', body, re.S))))
    return found


def element_label(sent_text, index):
    match = re.search(rf'^{re.escape(index)}\. ([\w.$]+): (.*) - \(\d+, ?\d+, ?\d+, ?\d+\)', sent_text, re.M)
    if not match:
        return ""
    parts = [p.strip('"') for p in re.sub(r" ; \w+=\w+$", "", match.group(2)).split('", "')]
    texts = [p for p in parts if ":id/" not in p and not p.endswith("." + match.group(1))]
    return f"{match.group(1)} “{texts[-1]}”" if texts else f"{match.group(1)} sem texto"


def describe(name, params, sent_text):
    if name == "click" and "index" in params:
        label = element_label(sent_text, params["index"].strip())
        return f"Tocar no elemento {params['index'].strip()}" + (f": {label}" if label else "")
    if name == "open_app":
        return f"Abrir o app “{params.get('text', next(iter(params.values()), ''))}”"
    if name == "complete":
        ok = params.get("success", "").strip().lower() == "true"
        return ("Encerrar: tarefa concluída" if ok else "Encerrar: tarefa não concluída") + f". “{params.get('message', '').strip()}”"
    if name in ("type", "input_text", "type_text"):
        return f"Digitar “{params.get('text', '')}”"
    args = ", ".join(f"{k}={v.strip()}" for k, v in params.items())
    return f"{name}({args})"


def swaps(counts):
    if not counts:
        return "nada trocado"
    return ", ".join(f"{n} {KINDS.get(kind, kind)}" for kind, n in counts.items())


def seconds(value):
    return f"{value:.1f}".replace(".", ",") + " s"


def render_timeline(spans, start, end):
    total = end - start
    lanes = (("phone", "Mobilerun e celular"), ("local", "IA local (Ollama)"), ("provider", "Provedor"))
    step = 10 if total <= 150 else 30
    ticks = "".join(f"<span class='tick' style='left:{100 * t / total:.3f}%'><i></i>{t} s</span>"
                    for t in range(0, int(total) + 1, step))
    rows = ""
    for key, label in lanes:
        bars = ""
        for lane, a, b, what in spans:
            if lane != key or b - a < 0.05:
                continue
            tip = f"{what}|{seconds(b - a)}|de {seconds(a - start)} a {seconds(b - start)}"
            bars += (f"<span class='bar {key}' tabindex='0' data-tip='{esc(tip)}' "
                     f"style='left:{100 * (a - start) / total:.3f}%;width:calc({100 * (b - a) / total:.3f}% - 2px)'></span>")
        spent = sum(b - a for lane, a, b, _ in spans if lane == key)
        rows += (f"<div class='lane'><div class='lane-name'><span class='swatch {key}'></span>{label}"
                 f"<small>{seconds(spent)} · {100 * spent / total:.0f}%</small></div><div class='track'>{bars}</div></div>")
    return f"<div class='timeline'>{rows}<div class='lane axis'><div class='lane-name'></div><div class='track'>{ticks}</div></div></div>"


def render_call(call, start, local=False):
    sent, answer = call["sent"], call["answer"] or {}
    # Desde 2026-10-21 o pedido vem em duas mensagens: as instruções fixas (sistema) e a situação (tela, motivo).
    sent_text = "\n".join(text_of(message) for message in sent["sent"] or [])
    helper = not local and sent["messages"] == 1 and "<device_state>" not in sent_text
    wrong = re.search(r"What went wrong: (.*)", sent_text)
    results = re.findall(r"<output>(.*?)</output>", sent_text, re.S)
    fragments = [f for f in screen_fragments(sent_text) if not f.startswith("•")]
    app = re.search(r"\*\*App:\*\* (.+)", sent_text)
    elements = len(re.findall(r"^\d+\. ", sent_text, re.M))

    arrive = []
    if helper:
        arrive.append("Pergunta auxiliar do Mobilerun, fora do ciclo de passos: qual app instalado corresponde ao pedido de abrir.")
    if local:
        arrive.append(f"O executor local pede ajuda ao provedor. Motivo: <q>{esc(wrong.group(1))}</q>" if wrong
                      else "O executor local pede o plano ao provedor. Só o pedido vai, sem nenhuma tela.")
    for result in results:
        arrive.append(f"Resultado da ação anterior: <q>{esc(' '.join(result.split()))}</q>")
    if "could not be parsed" in sent_text:
        arrive.append("O Mobilerun não conseguiu interpretar a resposta anterior e pediu ao provedor para repetir a chamada.")
    if app:
        arrive.append(f"Tela lida no celular: <b>{esc(app.group(1).strip())}</b>, {elements} elementos, {len(fragments)} trechos de texto.")
    arrive_html = "".join(f"<p>{line}</p>" for line in arrive) or "<p>Primeira mensagem do agente, com o pedido.</p>"
    if fragments:
        chips = "".join(f"<span class='chip'>{esc(f[:60])}{'…' if len(f) > 60 else ''}</span>" for f in fragments[:40])
        arrive_html += f"<details><summary>Textos da tela (já mascarados)</summary><div class='chips'>{chips}</div></details>"

    local = ""
    for screen in call["screens"]:
        info = screen["local_ai_tela"]
        local += (f"<p>Julgou <b>{info['trechos']}</b> trechos novos em <b>{seconds(info['seconds'])}</b> "
                  f"e marcou <b>{info['mascarar']}</b> como pessoa ou usuário.</p>")
        if "erro" in info:
            local += f"<p class='warn'>Falhou em parte: {esc(info['erro'])}</p>"
    local = local or "<p class='muted'>Nenhum trecho novo de tela: nada a julgar.</p>"

    counts = sent.get("masked") or {}
    mask = f"<p>Trocas neste envio: <b>{swaps(counts)}</b>.</p>"
    if counts.get("name", 0) >= MANY_NAMES:
        mask += ("<p class='warn'>⚠ Muitas trocas de nome num só envio. Costuma ser uma palavra comum que a IA local "
                 "marcou como pessoa e que passou a ser trocada em todo o texto.</p>")
    usage = answer.get("usage") or {}
    mask += (f"<p class='muted'>{sent['messages']} mensagens na conversa"
             + (f" · {usage['prompt_tokens']:,} tokens de entrada".replace(",", ".") if usage.get("prompt_tokens") else "") + "</p>")
    mask += f"<details><summary>Última mensagem enviada ao provedor</summary><pre>{esc(sent_text)}</pre></details>"

    received = answer.get("received")
    if answer.get("status") != 200:
        back = f"<p class='warn'>Erro {answer.get('status', 'sem resposta')}: {esc(str(received or answer.get('erro', ''))[:400])}</p>"
        reply_text = ""
    else:
        reply = received[0] if isinstance(received, list) and received else {}
        reply_text = text_of(reply)
        said = re.sub(r"<function_calls>.*", "", reply_text, flags=re.S).strip()
        back = f"<p>Respondeu em <b>{seconds(answer.get('seconds', 0))}</b>"
        if usage.get("completion_tokens"):
            back += f" · {usage['completion_tokens']} tokens de saída"
        if usage.get("cost") is not None:
            back += f" · US$ {usage['cost']:.4f}".replace(".", ",")
        back += "</p>"
        if said and local:
            back += f"<details><summary>Resposta completa (JSON)</summary><pre>{esc(said)}</pre></details>"
        elif said:
            back += f"<blockquote>{esc(said)}</blockquote>"
        if reply.get("reasoning"):
            back += f"<details><summary>Raciocínio do modelo</summary><pre>{esc(reply['reasoning'])}</pre></details>"

    actions = actions_of(reply_text)
    if local:
        try:
            answer_json = json.loads(reply_text[reply_text.index("{"):reply_text.rindex("}") + 1])
        except ValueError:
            answer_json = {}
        steps = answer_json.get("steps") or []
        act = "<ol class='actions'>" + "".join(
            f"<li>{esc(st.get('action', ''))}: {esc(str((st.get('target') or ["elemento " + str(st.get("index"))])[0]))}</li>" for st in steps) + "</ol>"
        if "finish" in answer_json:
            act = f"<p>O provedor mandou encerrar: <q>{esc(str(answer_json['finish'].get('message', '')))}</q></p>"
        title = "Ajuda pedida ao provedor" if wrong else "Plano pedido ao provedor"
        act = f"<p>O executor local recebe {len(steps)} passos:</p>" + act if steps else act
    elif helper:
        act = f"<p>Usa a resposta para escolher o pacote do app: <q>{esc(reply_text.strip()[:120])}</q></p>"
    elif actions:
        act = "<ol class='actions'>" + "".join(f"<li>{esc(describe(n, p, sent_text))}</li>" for n, p in actions) + "</ol>"
        act += "<p class='muted'>Os valores falsos são trocados pelos reais antes de o Mobilerun executar.</p>"
    else:
        act = "<p class='muted'>Nenhuma ação reconhecida na resposta.</p>"

    if not local:
        title = "Chamada auxiliar" if helper else (describe(*actions[0], sent_text) if actions else "Sem ação")
        if len(actions) > 1:
            title += f" (+{len(actions) - 1})"
    return f"""
<details class="call" {'open' if call['n'] == 1 else ''}>
  <summary><span class="num">{call['n']:02d}</span><span class="when">{seconds(sent['arrived'] - start)}</span>
    <span class="title">{esc(title[:110])}</span><span class="meta">{swaps(counts)}</span></summary>
  <div class="flow">
    <section class="phone"><h3>1 · {'Executor local pede' if local else 'Mobilerun envia'}</h3>{arrive_html}</section>
    <section class="local"><h3>2 · IA local julga</h3>{local}</section>
    <section class="proxy"><h3>3 · Proxy mascara e envia</h3>{mask}</section>
    <section class="provider"><h3>4 · Provedor responde</h3>{back}</section>
    <section class="phone"><h3>5 · {'Executor local recebe' if local else 'Mobilerun executa'}</h3>{act}</section>
  </div>
</details>"""


WHO = {"código": ("phone", "Código"), "IA local": ("local", "IA local"), "provedor": ("provider", "Provedor")}


def render_exec(number, step, start):
    """Um passo do modo local: quem decidiu, a ação, e as chamadas ao provedor feitas dentro dele."""
    row, info = step["row"], step["row"]["exec"]
    lane, who = WHO.get(info.get("por"), ("phone", info.get("por", "")))
    tools = actions_of(info.get("acao", ""))
    action = describe(*tools[0], "") if tools else info.get("acao", "")
    progress = f"passo {info['passo']} de {info['de']}" if info.get("de") else "fora do plano"
    extra = f" · IA local {seconds(info['ia_seconds'])}" if info.get("ia_seconds") else ""
    inner = "".join(render_call(c, start, local=True) for c in step["calls"])
    return f"""
<div class="exec {lane}">
  <div class="exec-line"><span class="num">{number:02d}</span><span class="when">{seconds(row['arrived'] - start)}</span>
    <span class="who"><span class="swatch {lane}"></span>{esc(who)}</span>
    <span class="title">{esc(info.get('decisao') or action)}</span><span class="meta">{progress}{extra}</span></div>
  <p class="exec-action">Ação enviada ao Mobilerun: <code>{esc(action)}</code></p>{inner}
</div>"""


def render(session, rows):
    task, judge, calls, execs, spans, start, end = build(rows)
    total = end - start
    answers = [c["answer"] or {} for c in calls]
    usages = [a.get("usage") or {} for a in answers]
    local_calls = [s for s in spans if s[0] == "local"]
    local_time = sum(b - a for _, a, b, _ in local_calls)
    provider_time = sum(a.get("seconds", 0) for a in answers)
    last_text = text_of((answers[-1].get("received") or [{}])[0]) if answers and isinstance(answers[-1].get("received"), list) else ""
    if execs:
        last_text = execs[-1]["row"]["exec"].get("acao", "")
    done = [p for n, p in actions_of(last_text) if n == "complete"]
    if done:
        ok = done[-1].get("success", "").strip().lower() == "true"
        outcome = ("Concluída" if ok else "Não concluída", "good" if ok else "bad", done[-1].get("message", "").strip())
    else:
        outcome = ("Interrompida", "bad", "A última resposta não encerrou a tarefa.")
    names = sum((c["sent"].get("masked") or {}).get("name", 0) for c in calls)
    others = sum(n for c in calls for k, n in (c["sent"].get("masked") or {}).items() if k != "name")
    judged = judge["local_ai"] if judge else {}
    judge_text = (f"erro: {judged['erro']}" if "erro" in judged else
                  f"intenção “{judged.get('intencao')}”, decisões: {', '.join(f'{n} {k}' for k, n in (judged.get('decisoes') or {}).items()) or 'nenhuma'}, em {seconds(judged.get('seconds', 0))}") if judge else "não registrado"
    errors = sum(a.get("status") != 200 for a in answers)
    tiles = [
        ("Tempo total", seconds(total), f"{rows[0]['time']}"),
        ("Chamadas ao provedor", str(len(calls)), f"{errors} com erro · {seconds(provider_time)} esperando resposta"),
        ("Chamadas à IA local", str(len(local_calls)), f"{seconds(local_time)} · {100 * local_time / total:.0f}% do tempo"),
        ("Tokens", f"{sum(u.get('prompt_tokens', 0) for u in usages):,}".replace(",", "."),
         f"de entrada · {sum(u.get('completion_tokens', 0) for u in usages):,} de saída".replace(",", ".")),
        ("Custo no provedor", "US$ " + f"{sum(u.get('cost') or 0 for u in usages):.4f}".replace(".", ","), calls[0]["sent"].get("model") or ""),
        ("Trocas feitas", str(names + others), f"{names} de nome · {others} de outros tipos"),
    ]
    if execs:
        by = {key: sum(e["row"]["exec"].get("por") == key for e in execs) for key in WHO}
        tiles.insert(1, ("Ações decididas", str(len(execs)),
                         f"{by['código']} por código · {by['IA local']} pela IA local · {by['provedor']} com o provedor"))
        cards = "".join(render_exec(i, e, start) for i, e in enumerate(execs, 1))
        how = ("Modo local: cada linha é uma tela que o Mobilerun leu e a ação decidida para ela. "
               "As chamadas ao provedor (plano e ajuda) aparecem dentro do passo em que aconteceram.")
    else:
        cards = "".join(render_call(c, start) for c in calls)
        how = "Cada linha é uma chamada ao provedor, na ordem. Abra para ver as cinco etapas, da tela lida no celular até a ação executada."
    tiles_html = "".join(f"<div class='tile'><span>{esc(a)}</span><strong>{esc(b)}</strong><small>{esc(c)}</small></div>" for a, b, c in tiles)
    return f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tarefa {esc(session)}</title>
<style>
:root {{ --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --line:#e1e0d9; --axis:#c3c2b7;
  --provider:#2a78d6; --local:#eb6834; --phone:#1baf7a; --good:#006300; --bad:#d03b3b; --warn-bg:#fdf3dc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --line:#2c2c2a;
  --axis:#383835; --provider:#3987e5; --local:#d95926; --phone:#199e70; --good:#0ca30c; --bad:#e66767; --warn-bg:#3a2f12; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink); font:15px/1.5 system-ui, "Segoe UI", sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:40px 0 4px; }} h3 {{ font-size:13px; margin:0 0 8px; }}
.sub {{ color:var(--ink2); margin:0 0 12px; }} .muted {{ color:var(--muted); }} small {{ color:var(--muted); }}
.task {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:16px 0; }}
.task p {{ margin:4px 0; }} .badge {{ font-weight:600; }} .badge.good {{ color:var(--good); }} .badge.bad {{ color:var(--bad); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; }}
.tile {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:12px 14px; display:flex; flex-direction:column; }}
.tile span {{ color:var(--ink2); font-size:13px; }} .tile strong {{ font-size:24px; font-variant-numeric:tabular-nums; }}
.timeline {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px 20px 8px 16px; overflow-x:auto; }}
.lane {{ display:grid; grid-template-columns:190px 1fr; align-items:center; min-width:720px; }}
.lane-name {{ font-size:13px; padding-right:12px; }} .lane-name small {{ display:block; margin-left:18px; font-variant-numeric:tabular-nums; }}
.track {{ position:relative; height:38px; border-bottom:1px solid var(--line); }}
.bar {{ position:absolute; top:9px; height:20px; min-width:3px; border-radius:4px; cursor:default; outline-offset:2px; }}
.bar:hover, .bar:focus {{ filter:brightness(1.15); outline:2px solid var(--ink); }}
.provider {{ --c:var(--provider); }} .local {{ --c:var(--local); }} .phone {{ --c:var(--phone); }} .proxy {{ --c:var(--muted); }}
.bar, .swatch {{ background:var(--c); }}
.swatch {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:8px; }}
.axis .track {{ border:0; height:26px; }} .tick {{ position:absolute; top:0; font-size:11px; color:var(--muted); transform:translateX(-50%); padding-top:8px; white-space:nowrap; }}
.tick i {{ position:absolute; left:50%; top:0; height:6px; border-left:1px solid var(--axis); }}
#tip {{ position:fixed; z-index:9; pointer-events:none; background:var(--ink); color:var(--page); padding:6px 10px; border-radius:6px; font-size:12px; display:none; max-width:300px; }}
#tip b {{ display:block; }}
.call {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; margin:8px 0; }}
.call > summary {{ display:grid; grid-template-columns:36px 64px 1fr auto; gap:10px; align-items:baseline; padding:10px 14px; cursor:pointer; list-style:none; }}
.call > summary::-webkit-details-marker {{ display:none; }}
.num {{ font-weight:700; font-variant-numeric:tabular-nums; }} .when, .meta {{ color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }}
.title {{ font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.flow {{ display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; padding:4px 14px 14px; }}
@media (max-width:980px) {{ .flow {{ grid-template-columns:1fr; }} .call > summary {{ grid-template-columns:36px 64px 1fr; }} .meta {{ display:none; }} }}
.flow section {{ border-top:3px solid var(--c); background:var(--page); border-radius:0 0 8px 8px; padding:10px 12px; min-width:0; position:relative; }}
.flow section + section::before {{ content:"→"; position:absolute; left:-12px; top:6px; color:var(--muted); }}
@media (max-width:980px) {{ .flow section + section::before {{ content:"↓"; left:50%; top:-16px; }} }}
.flow p {{ margin:0 0 8px; font-size:13.5px; overflow-wrap:anywhere; }}
.warn {{ background:var(--warn-bg); border-radius:6px; padding:6px 8px; }}
blockquote {{ margin:0 0 8px; padding-left:10px; border-left:2px solid var(--axis); font-size:13.5px; white-space:pre-wrap; overflow-wrap:anywhere; }}
pre {{ font:12px/1.45 ui-monospace, monospace; white-space:pre-wrap; overflow-wrap:anywhere; max-height:420px; overflow:auto; margin:8px 0 0; }}
.flow details > summary {{ cursor:pointer; color:var(--ink2); font-size:13px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }} .chip {{ border:1px solid var(--line); border-radius:999px; padding:1px 8px; font-size:12px; }}
.actions {{ margin:0 0 8px; padding-left:18px; font-size:13.5px; }} .actions li {{ margin-bottom:4px; overflow-wrap:anywhere; }}
q {{ font-style:italic; }}
.exec {{ background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--c); border-radius:10px; margin:8px 0; padding:10px 14px; }}
.exec-line {{ display:grid; grid-template-columns:36px 64px 96px 1fr auto; gap:10px; align-items:baseline; }}
.who {{ font-size:13px; white-space:nowrap; }} .exec-action {{ margin:6px 0 0 110px; font-size:13px; color:var(--ink2); overflow-wrap:anywhere; }}
.exec .call {{ margin:10px 0 0; background:var(--page); }} code {{ font:12px ui-monospace, monospace; }}
@media (max-width:980px) {{ .exec-line {{ grid-template-columns:36px 64px 1fr; }} .exec-line .title {{ grid-column:1 / -1; white-space:normal; }} .exec-action {{ margin-left:0; }} }}
</style>
<main>
<h1>Diagrama da tarefa</h1>
<p class="sub">Sessão {esc(session)} · tudo aqui é o texto já mascarado, como o provedor o recebeu.</p>
<div class="task">
  <p><b>Pedido:</b> {esc(task) or '<span class="muted">não registrado</span>'}</p>
  <p><b>Julgamento do pedido pela IA local:</b> {esc(str(judge_text))}</p>
  <p><b>Resultado:</b> <span class="badge {outcome[1]}">{'✓' if outcome[1] == 'good' else '✗'} {outcome[0]}</span>. {esc(outcome[2])}</p>
</div>
<div class="tiles">{tiles_html}</div>

<h2>Para onde foi o tempo</h2>
<p class="sub">Cada barra é um trecho de trabalho de um dos três participantes. Passe o mouse para ver o que foi feito.
O julgamento do pedido roda ao mesmo tempo que a subida do agente, por isso as três somas passam um pouco do total.</p>
{render_timeline(spans, start, end)}

<h2>{'Passo a passo' if execs else 'Chamada por chamada'}</h2>
<p class="sub">{how}</p>
{cards}
</main>
<div id="tip"></div>
<script>
const tip = document.getElementById("tip");
function show(bar, x, y) {{
  const [what, took, when] = bar.dataset.tip.split("|");
  tip.innerHTML = "<b></b><span></span>"; tip.firstChild.textContent = what; tip.lastChild.textContent = took + " · " + when;
  tip.style.display = "block";
  tip.style.left = Math.min(x + 12, innerWidth - tip.offsetWidth - 8) + "px"; tip.style.top = (y + 14) + "px";
}}
for (const bar of document.querySelectorAll(".bar")) {{
  bar.addEventListener("mousemove", e => show(bar, e.clientX, e.clientY));
  bar.addEventListener("focus", () => {{ const r = bar.getBoundingClientRect(); show(bar, r.left, r.bottom); }});
  bar.addEventListener("mouseleave", () => tip.style.display = "none");
  bar.addEventListener("blur", () => tip.style.display = "none");
}}
</script>
</html>"""


def main():
    session, rows = load(sys.argv[1] if len(sys.argv) > 1 else None)
    os.makedirs("reports", exist_ok=True)
    path = f"reports/tarefa-{session}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(session, rows))
    print(path)


if __name__ == "__main__":
    main()
