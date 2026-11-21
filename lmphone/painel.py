"""Painel local para navegar pelas suítes e tarefas: cada rodada com as conferências, a saída do agente, a tela final,
o que a IA local gerou (logs/detalhe/), o que foi ao provedor e o que ele devolveu (logs/proxy.jsonl).

Uso: python -m lmphone.painel [--porta 8770]     e abrir http://127.0.0.1:8770

Só escuta em 127.0.0.1: a saída do agente, a tela final e o detalhe da IA local têm dados reais.
"""

import argparse
import glob
import html
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY_LOG = "logs/proxy.jsonl"
DETAIL_DIR = "logs/detalhe"
LIVE_DIR = "logs/live"
COLLECT_DIR = "data/treino/real"

esc = html.escape
_cache = {}


def cached(key, paths, build):
    """`build()` refeito só quando algum dos arquivos muda (o proxy.jsonl tem dezenas de MB)."""
    stamp = tuple((p, os.path.getmtime(p), os.path.getsize(p)) for p in paths if os.path.exists(p))
    if key not in _cache or _cache[key][0] != stamp:
        _cache[key] = (stamp, build())
    return _cache[key][1]


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def proxy_sessions():
    """Linhas do proxy.jsonl agrupadas por sessão, na ordem do log."""
    def build():
        by = {}
        for row in read_jsonl(PROXY_LOG) if os.path.exists(PROXY_LOG) else []:
            if "ts" in row and "session" in row:
                by.setdefault(row["session"], []).append(row)
        return by
    return cached("proxy", [PROXY_LOG], build)


def collected(session):
    """O que a coleta de treino (LMPHONE_COLETA=1) gravou da sessão: as tarefas de antes do registro detalhado."""
    paths = [p for p in sorted(glob.glob(os.path.join(COLLECT_DIR, "*.jsonl"))) if re.match(r"\d{4}-", os.path.basename(p))]

    def build():
        by = {}
        for path in paths:
            for row in read_jsonl(path):
                by.setdefault(row.get("session"), []).append(row)
        return by
    return cached("coleta", paths, build).get(session, [])


def detail(session):
    path = os.path.join(DETAIL_DIR, f"{session}.jsonl")
    return read_jsonl(path) if session and os.path.exists(path) else []


def suites():
    paths = sorted(glob.glob("reports/suite-*.json"), reverse=True)

    def build():
        found = {}
        for path in paths:
            try:
                with open(path, encoding="utf-8") as f:
                    found[re.search(r"suite-(.+)\.json$", path).group(1)] = json.load(f)
            except (OSError, ValueError):
                pass
        return found
    return cached("suites", paths, build)


# ---------------------------------------------------------------- formatação

def fmt_s(value):
    return f"{value or 0:.1f}".replace(".", ",") + " s"


def fmt_money(value):
    return "US$ " + f"{value or 0:.4f}".replace(".", ",")


def fmt_gb(mb):
    return f"{(mb or 0) / 1024:.1f}".replace(".", ",") + " GB"


def pre(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1, default=str)
    return f"<pre>{esc(text)}</pre>"


def table(rows, columns=None):
    """Lista de dicionários em tabela; valores compostos viram JSON."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return "<p class='muted'>nada</p>"
    columns = columns or list(dict.fromkeys(k for r in rows for k in r))

    def cell(v):
        if isinstance(v, (dict, list)):
            return f"<code>{esc(json.dumps(v, ensure_ascii=False, default=str))}</code>"
        if isinstance(v, float):
            return f"{v:.3f}".replace(".", ",")
        return esc("—" if v is None else str(v))
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{cell(r.get(c))}</td>" for c in columns) + "</tr>" for r in rows)
    return f"<div class='scroll'><table class='grid'><tr>{head}</tr>{body}</table></div>"


def badge(status):
    return f"<span class='badge {esc(status or '')}'>{esc(status or '?')}</span>"


STYLE = """
:root { --page:#f9f9f7; --surface:#fff; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --line:#e1e0d9;
  --ok:#1a7f37; --bad:#c62828; --pend:#9a6700; --accent:#2a78d6; --local:#eb6834; --mark:#fde7a8; }
@media (prefers-color-scheme: dark) { :root { --page:#0d0d0d; --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7;
  --muted:#8f8d86; --line:#2c2c2a; --ok:#3fb950; --bad:#f06c6c; --pend:#d29922; --accent:#4f9bf0; --local:#e07040; --mark:#5a4a12; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--page); color:var(--ink); font:15px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width:1240px; margin:0 auto; padding:20px 16px 64px; }
nav.crumbs { font-size:14px; color:var(--muted); margin-bottom:12px; } nav.crumbs a { color:var(--accent); }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
h1 { font-size:24px; margin:0 0 6px; } h2 { font-size:18px; margin:32px 0 8px; } h3 { font-size:15px; margin:16px 0 6px; }
.muted, small { color:var(--muted); }
.tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin:14px 0; }
.tile { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:10px 14px; }
.tile span { display:block; color:var(--ink2); font-size:13px; } .tile b { font-size:21px; font-variant-numeric:tabular-nums; }
.card { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:12px 16px; margin:10px 0; }
.scroll { overflow-x:auto; }
table.grid { border-collapse:collapse; width:100%; font-size:13.5px; }
table.grid th, table.grid td { border-top:1px solid var(--line); padding:7px 8px; text-align:left; vertical-align:top; }
table.grid th { color:var(--ink2); font-weight:600; white-space:nowrap; }
table.grid tr.link { cursor:pointer; } table.grid tr.link:hover td { background:color-mix(in srgb, var(--accent) 7%, transparent); }
td.n { white-space:nowrap; font-variant-numeric:tabular-nums; }
.badge { border-radius:4px; color:#fff; padding:1px 8px; font-size:12.5px; background:var(--pend); white-space:nowrap; }
.badge.passou { background:var(--ok); } .badge.falhou, .badge.erro { background:var(--bad); }
ul.checks { margin:4px 0; padding-left:18px; } li.ok { color:var(--ok); } li.bad { color:var(--bad); } li.pend { color:var(--pend); }
pre { font:12px/1.45 ui-monospace, Consolas, monospace; white-space:pre-wrap; overflow-wrap:anywhere; max-height:480px;
  overflow:auto; margin:6px 0; background:var(--page); border:1px solid var(--line); border-radius:6px; padding:8px; }
code { font:12px ui-monospace, Consolas, monospace; overflow-wrap:anywhere; }
details > summary { cursor:pointer; } details.row { border-top:1px solid var(--line); padding:6px 0; }
details.row > summary { font-size:13.5px; } details.row > summary b { font-weight:600; }
.filters { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0; }
.filters button { font:inherit; font-size:13px; border:1px solid var(--line); background:var(--surface); color:var(--ink);
  border-radius:999px; padding:3px 12px; cursor:pointer; } .filters button.on { border-color:var(--accent); color:var(--accent); }
.chips { display:flex; flex-wrap:wrap; gap:4px; } .chip { border:1px solid var(--line); border-radius:999px; padding:1px 8px; font-size:12px; }
.chip.marked { background:var(--mark); border-color:transparent; } .chip.dropped { opacity:.5; }
.split { display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:10px; }
iframe.trace { width:100%; border:1px solid var(--line); border-radius:10px; min-height:600px; background:var(--page); }
img.shot { max-width:320px; width:100%; border:1px solid var(--line); border-radius:10px; }
.pager { display:flex; justify-content:space-between; gap:10px; margin:6px 0 0; font-size:14px; }
.warn { background:color-mix(in srgb, var(--pend) 18%, transparent); border-radius:6px; padding:6px 10px; }
"""

SCRIPT = """
for (const row of document.querySelectorAll("tr[data-href]")) row.addEventListener("click", e => {
  if (e.target.closest("a")) return; location.href = row.dataset.href; });
const bar = document.querySelector(".filters[data-for]");
if (bar) bar.addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  for (const x of bar.querySelectorAll("button")) x.classList.toggle("on", x === b);
  for (const row of document.querySelectorAll(bar.dataset.for))
    row.style.display = !b.dataset.v || row.dataset.status === b.dataset.v ? "" : "none";
});
const frame = document.querySelector("iframe.trace");
if (frame) frame.addEventListener("load", () => {
  const fit = () => frame.style.height = frame.contentDocument.documentElement.scrollHeight + 20 + "px";
  fit(); new ResizeObserver(fit).observe(frame.contentDocument.body);
});
"""


def page(title, crumbs, body):
    nav = " / ".join(f"<a href='{esc(href)}'>{esc(label)}</a>" if href else esc(label) for label, href in crumbs)
    return (f"<!doctype html><html lang='pt-BR'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{STYLE}</style><main><nav class='crumbs'>{nav}</nav>{body}</main>"
            f"<script>{SCRIPT}</script></html>")


# ---------------------------------------------------------------- páginas

def home():
    rows = []
    for stamp, records in suites().items():
        count = {s: sum(r.get("status") == s for r in records) for s in ("passou", "falhou", "erro", "manual")}
        levels = sorted({r.get("nivel", "") for r in records})
        rows.append(
            f"<tr class='link' data-href='/suite/{esc(stamp)}'><td><a href='/suite/{esc(stamp)}'>{esc(stamp)}</a></td>"
            f"<td>{esc(', '.join(levels))}</td><td class='n'>{len(records)}</td>"
            f"<td class='n'><span style='color:var(--ok)'>{count['passou']}</span> · <span style='color:var(--bad)'>{count['falhou'] + count['erro']}</span>"
            f"{' · ' + str(count['manual']) + ' manual' if count['manual'] else ''}</td>"
            f"<td class='n'>{sum(r.get('segundos', 0) for r in records) / 60:.1f} min</td>"
            f"<td class='n'>{fmt_money(sum(r.get('custo', 0) for r in records))}</td></tr>")
    body = ("<h1>Baterias de testes</h1><p class='muted'>Cada linha é uma rodada da suíte no celular (reports/suite-*.json). "
            "<a href='/tarefas'>Todas as tarefas do log</a>, inclusive as de fora da suíte.</p>"
            "<div class='scroll'><table class='grid'><tr><th>Suíte</th><th>Níveis</th><th>Rodadas</th><th>Passou · falhou</th>"
            f"<th>Tempo</th><th>Custo</th></tr>{''.join(rows)}</table></div>")
    return page("Baterias de testes", [("lm_phone", None)], body)


def suite_page(stamp):
    records = suites().get(stamp)
    if records is None:
        return None
    statuses = sorted({r.get("status", "") for r in records})
    rows = []
    for i, r in enumerate(records):
        checks = "".join(f"<li class='{'ok' if c['ok'] else 'pend' if c['ok'] is None else 'bad'}'>{esc(c['nome'])}</li>"
                         for c in r.get("conferencias", []) if c["ok"] is not True)
        href = f"/rodada/{stamp}/{i}"
        rows.append(
            f"<tr class='link round' data-status='{esc(r.get('status', ''))}' data-href='{href}'>"
            f"<td><a href='{href}'>{esc(r['id'])}</a>{' #' + str(r['rodada'] + 1) if r.get('rodada') else ''}<br><small>{esc(r.get('nivel', ''))}</small></td>"
            f"<td>{badge(r.get('status'))}</td>"
            f"<td>{esc(r.get('pedido', ''))}<ul class='checks'>{checks}</ul></td>"
            f"<td>{esc(r.get('agente', ''))}<br><small>{esc(r.get('resultado') or '')}</small></td>"
            f"<td class='n'>{fmt_s(r.get('segundos'))}</td><td class='n'>{r.get('chamadas', 0)} · {r.get('ajudas', 0)} aj.</td>"
            f"<td class='n'>{fmt_money(r.get('custo'))}</td></tr>")
    filters = "<button class='on' data-v=''>todas</button>" + "".join(
        f"<button data-v='{esc(s)}'>{esc(s)} ({sum(r.get('status') == s for r in records)})</button>" for s in statuses)
    body = (f"<h1>Suíte {esc(stamp)}</h1><p class='muted'>{len(records)} rodadas · "
            f"{sum(r.get('segundos', 0) for r in records) / 60:.1f} min · {fmt_money(sum(r.get('custo', 0) for r in records))}</p>"
            f"<div class='filters' data-for='tr.round'>{filters}</div>"
            "<div class='scroll'><table class='grid'><tr><th>Caso</th><th>Resultado</th><th>Pedido e conferências que falharam</th>"
            f"<th>Agente</th><th>Tempo</th><th>Provedor</th><th>Custo</th></tr>{''.join(rows)}</table></div>")
    return page(f"Suíte {stamp}", [("lm_phone", "/"), (stamp, None)], body)


def round_page(stamp, index):
    records = suites().get(stamp)
    if records is None or not 0 <= index < len(records):
        return None
    r = records[index]
    session = r.get("sessao")
    ram = r.get("ram") or {}
    tiles = [("Tempo", fmt_s(r.get("segundos"))), ("Provedor", fmt_s(r.get("provedor_s"))), ("IA local", fmt_s(r.get("ia_local_s"))),
             ("Chamadas", r.get("chamadas", 0)), ("Ajudas", r.get("ajudas", 0)), ("Ações", r.get("acoes", 0)),
             ("Tokens", f"{r.get('tokens_entrada', 0)} / {r.get('tokens_saida', 0)}"), ("Custo", fmt_money(r.get("custo"))),
             ("Trocas", r.get("trocas", 0)), ("RAM (pico)", fmt_gb(ram.get("pico_mb")) if ram else "—"),
             ("Cache", {True: "usado", False: "não", None: "—"}.get(r.get("cache"), str(r.get("cache"))))]
    tiles_html = "".join(f"<div class='tile'><span>{esc(a)}</span><b>{esc(str(b))}</b></div>" for a, b in tiles)
    checks = "".join(f"<li class='{'ok' if c['ok'] else 'pend' if c['ok'] is None else 'bad'}'>{'✓' if c['ok'] else '?' if c['ok'] is None else '✗'} "
                     f"{esc(c['nome'])}{' <small>(' + esc(c['detalhe']) + ')</small>' if c.get('detalhe') else ''}</li>"
                     for c in r.get("conferencias", []))
    errors = "".join(f"<li class='bad'>{esc(e)}</li>" for e in r.get("erros", []))
    pager = "<div class='pager'>" + (f"<a href='/rodada/{stamp}/{index - 1}'>← {esc(records[index - 1]['id'])}</a>" if index else "<span></span>") + \
        (f"<a href='/rodada/{stamp}/{index + 1}'>{esc(records[index + 1]['id'])} →</a>" if index + 1 < len(records) else "<span></span>") + "</div>"

    output = ""
    if r.get("saida") and os.path.exists(r["saida"]):
        with open(r["saida"], encoding="utf-8", errors="replace") as f:
            output = f.read()
    shot = ""
    if r.get("captura") and os.path.isdir(r["captura"]):
        files = os.listdir(r["captura"])
        link = lambda name: "/arquivo?c=" + urllib.parse.quote(os.path.basename(r["captura"])) + "&f=" + name
        if "tela.png" in files:
            shot += f"<a href='{link('tela.png')}' target='_blank'><img class='shot' src='{link('tela.png')}' alt='Tela final'></a>"
        if "tela.txt" in files:
            with open(os.path.join(r["captura"], "tela.txt"), encoding="utf-8", errors="replace") as f:
                shot += f"<details><summary>Texto da tela final</summary>{pre(f.read())}</details>"

    body = (f"{pager}<h1>{esc(r['id'])}{' #' + str(r['rodada'] + 1) if r.get('rodada') else ''} {badge(r.get('status'))}</h1>"
            f"<p><b>Pedido:</b> {esc(r.get('pedido', ''))}</p>"
            f"<p class='muted'>{esc(r.get('testa', ''))} · {esc(r.get('nivel', ''))} · {esc(r.get('categoria', ''))} · "
            f"início {esc(r.get('inicio', ''))} · sessão {esc(session or '—')}</p>"
            f"<div class='tiles'>{tiles_html}</div>"
            f"<div class='split'><div class='card'><h3>Conferências no aparelho</h3><ul class='checks'>{checks or '<li>nenhuma</li>'}</ul>"
            + (f"<h3>Erros</h3><ul class='checks'>{errors}</ul>" if errors else "")
            + f"<h3>O que o agente declarou</h3><p>{esc(r.get('agente', ''))}{' · ' + esc(r['resultado']) if r.get('resultado') else ''}</p></div>"
            + (f"<div class='card'><h3>Tela final</h3>{shot}</div>" if shot else "") + "</div>"
            + (f"<details class='card'><summary><b>Saída do agente</b> <small>({esc(r['saida'])}, dados reais)</small></summary>{pre(output)}</details>" if output else "")
            + session_sections(session)
            + f"<details class='card'><summary><b>Registro da suíte (JSON)</b></summary>{pre(r)}</details>")
    return page(f"{r['id']} · {stamp}", [("lm_phone", "/"), (stamp, f"/suite/{stamp}"), (r["id"], None)], body)


def session_sections(session):
    """O que a IA local gerou, as chamadas ao provedor (o diagrama do trace) e o log bruto da sessão."""
    if not session:
        return "<p class='warn'>Esta rodada não registrou a sessão: não há como achá-la no log.</p>"
    rows = proxy_sessions().get(session, [])
    out = live_section(session) + "<h2>IA local</h2>" + local_ai_section(session)
    if rows:
        out += "<h2>Chamadas ao provedor</h2>" + provider_section(rows)
        out += ("<h2>Passos e provedor</h2><p class='muted'>O diagrama da tarefa: cada passo, quem decidiu, e cada chamada ao "
                f"provedor com o que foi enviado (já mascarado) e o que ele respondeu. <a href='/sessao/{esc(session)}' target='_blank'>Abrir sozinho</a></p>"
                f"<iframe class='trace' src='/sessao/{esc(session)}' title='Diagrama da tarefa'></iframe>")
        out += f"<h2>Log bruto do proxy</h2><p class='muted'>{len(rows)} linhas de logs/proxy.jsonl, na ordem.</p><div class='card'>"
        for row in rows:
            kind = next((k for k in row if k not in ("time", "ts", "session", "arrived")), "?")
            extra = ""
            if kind == "exec":
                extra = f" · {row['exec'].get('por', '')}: {row['exec'].get('decisao', '')[:120]}"
            elif kind == "sent":
                extra = f" · chamada {row.get('request')} · {row.get('messages')} mensagens"
            elif kind == "received":
                extra = f" · chamada {row.get('request')} · {fmt_s(row.get('seconds'))} · status {row.get('status')}"
            out += f"<details class='row'><summary><b>{esc(kind)}</b> <small>{esc(row.get('time', ''))}</small>{esc(extra)}</summary>{pre(row)}</details>"
        out += "</div>"
    else:
        out += "<p class='warn'>A sessão não está em logs/proxy.jsonl.</p>"
    return out


# A primeira chave que aparece no texto decide; a conferência final vem dentro de um pedido de ajuda, então vem antes.
CALL_KINDS = (("every step of the plan was carried out", "Conferência final"), ("The owner now says:", "Turno do assistente"),
              ("You write step-by-step plans", "Plano"), ("got stuck and needs you", "Ajuda"), ("It needs you.", "Ajuda"))


def provider_section(rows):
    """Cada chamada ao provedor: o texto exato que saiu (já mascarado) e o que voltou, lado a lado."""
    answers = {r["request"]: r for r in rows if "received" in r or ("request" in r and "status" in r)}
    out, start = "", rows[0]["ts"]
    sent_rows = [r for r in rows if "sent" in r]
    if not sent_rows:
        return "<p class='muted'>Nenhuma chamada: o caminho veio do cache.</p>"
    for r in sent_rows:
        messages = r.get("sent") or []
        texts = [trace.text_of(m) for m in messages]
        kind = next((label for key, label in CALL_KINDS if any(key in t for t in texts)), "Outra")
        answer = answers.get(r["request"]) or {}
        usage = answer.get("usage") or {}
        received = answer.get("received")
        reply = received[0] if isinstance(received, list) and received else {}
        reply_text = trace.text_of(reply) if reply else json.dumps(received, ensure_ascii=False) if received else ""
        masked = ", ".join(f"{n} {trace.KINDS.get(k, k)}" for k, n in (r.get("masked") or {}).items()) or "nada trocado"
        sent_html = "".join(f"<p class='muted'>mensagem {i + 1} · {esc(m.get('role', ''))} · {len(t)} caracteres</p>{pre(t)}"
                            for i, (m, t) in enumerate(zip(messages, texts)))
        back = pre(reply_text or "(vazio)")
        if reply.get("reasoning"):
            back += f"<p class='muted'>raciocínio</p>{pre(reply['reasoning'])}"
        out += (f"<details class='card' {'open' if r is sent_rows[0] else ''}><summary><b>{r['request']:02d} · {kind}</b> "
                f"<small>+{r['ts'] - start:.1f} s · {esc(r.get('model', ''))} · {fmt_s(answer.get('seconds'))} · "
                f"{usage.get('prompt_tokens', 0)} → {usage.get('completion_tokens', 0)} tokens · {fmt_money(usage.get('cost'))} · "
                f"trocas: {esc(masked)}{' · status ' + str(answer.get('status')) if answer.get('status') != 200 else ''}</small></summary>"
                f"<div class='split'><div><h3>Enviado ao provedor (exato, mascarado)</h3>{sent_html}</div>"
                f"<div><h3>Resposta do provedor</h3>{back}</div></div></details>")
    return out


LIVE_LABELS = {"pedido": "Pedido", "status": "Faixa mostrou", "acao": "Ação do agente", "fim": "Fim",
               "usuario_instrucao": "Você escreveu", "usuario_toque": "Você tocou", "usuario_toque_longo": "Você tocou e segurou",
               "usuario_pausa": "Você pausou", "usuario_retomada": "Você continuou", "usuario_interrupcao": "Você interrompeu",
               "usuario_escrevendo": "Você abriu o campo", "erro": "Erro da faixa"}


def live_section(session):
    """A linha do tempo do live mode (logs/live/): o que a faixa mostrou, cada ação do agente e tudo o que o usuário fez."""
    path = os.path.join(LIVE_DIR, f"{session}.jsonl")
    if not os.path.exists(path):
        return ""
    rows = read_jsonl(path)
    start, body = rows[0]["ts"] if rows else 0, ""
    for row in rows:
        kind = row.get("tipo", "?")
        fields = {k: v for k, v in row.items() if k not in ("ts", "tipo", "t")}
        if kind == "status":
            what = esc(fields.get("texto", ""))
        elif kind == "acao":
            what = f"<code>{esc(fields.get('ferramenta', ''))}</code> {esc(json.dumps(fields.get('parametros') or {}, ensure_ascii=False))} "                    f"<small>por {esc(str(fields.get('por')))} · passo {esc(str(fields.get('passo')))}</small>"
        elif kind.startswith("usuario_toque"):
            what = (f"“{esc(fields.get('texto', ''))}” <small>{esc(fields.get('pacote', ''))} · {esc(fields.get('classe', ''))} · "
                    f"{fields.get('ms_desde_agente', 0)} ms depois do agente{' · duvidoso' if fields.get('duvidoso') else ''}</small>")
        else:
            what = esc(fields.get("texto") or fields.get("mensagem") or fields.get("motivo") or fields.get("erro") or
                       (json.dumps(fields, ensure_ascii=False) if fields else ""))
        mine = kind.startswith("usuario_")
        body += (f"<tr><td class='n'>+{row['ts'] - start:.1f} s</td><td{' style=color:var(--local)' if mine else ''}><b>"
                 f"{esc(LIVE_LABELS.get(kind, kind))}</b></td><td>{what}</td></tr>")
    count = sum(r.get("tipo", "").startswith("usuario_") for r in rows)
    return (f"<h2>Live mode</h2><p class='muted'>{len(rows)} eventos, {count} seus (logs/live/, valores reais).</p>"
            f"<div class='card scroll'><table class='grid'>{body}</table></div>")


def local_ai_section(session):
    rows = detail(session)
    if not rows:
        old = collected(session)
        if not old:
            return ("<p class='muted'>Sem o registro detalhado da IA local: a tarefa é de antes de ele existir (2026-10-19) "
                    "ou rodou com LMPHONE_DETALHE=0. O log do proxy guarda só contagens.</p>")
        return ("<p class='muted'>Sem o registro detalhado; abaixo, o que a coleta de treino gravou desta tarefa.</p>"
                + "".join(f"<details class='row'><summary><b>{esc(r.get('tipo', '?'))}</b></summary>{pre(r)}</details>" for r in old))
    out = "<p class='muted'>Valores reais (logs/detalhe/, só nesta máquina).</p>"
    start = rows[0]["ts"]
    for row in rows:
        kind, when = row.get("tipo"), f"+{row['ts'] - start:.1f}".replace(".", ",") + " s"
        if kind == "pedido":
            judgment = row.get("julgamento") or {}
            out += (f"<div class='card'><h3>Julgamento do pedido <small>{when} · {fmt_s(row.get('segundos'))}</small></h3>"
                    f"<p><b>Pedido:</b> {esc(row.get('texto', ''))}<br><b>Intenção:</b> {esc(str(judgment.get('intencao')))}</p>"
                    f"<p class='muted'>Entidades que o modelo de marcação achou e a decisão de cada uma:</p>"
                    f"{table(row.get('decisoes') or [], ['texto', 'tipo', 'decisao', 'motivo'])}"
                    f"<details><summary>Saída completa do modelo</summary>{pre(judgment)}</details></div>")
        elif kind == "tela":
            judgment = row.get("julgamento") or {}
            fragments = judgment.get("trechos") or []
            gate = judgment.get("laya") or []
            marked = {str(m.get("texto", m)) if isinstance(m, dict) else str(m)
                      for found in judgment.get("gemma") or [] for m in found.get("mascarados") or []}
            chips = ""
            for i, fragment in enumerate(fragments):
                p = gate[i] if i < len(gate) else None
                hit = any(m and m in fragment for m in marked)
                chips += (f"<span class='chip{' marked' if hit else ''}{' dropped' if p is not None and p < 0.15 else ''}' "
                          f"title='{'filtro: ' + format(p, '.2f') if p is not None else ''}'>{esc(fragment[:80])}</span>")
            found = [item for f in judgment.get("gemma") or [] for item in ((f.get("achou") or {}).get("itens") or [])]
            out += (f"<div class='card'><h3>Tela julgada <small>{when} · {row.get('trechos', 0)} trechos novos · {row.get('mascarar', 0)} mascarados · "
                    f"{fmt_s(row.get('seconds'))}</small></h3>"
                    + (f"<p class='warn'>{esc(row.get('erro') or row.get('erro_laya'))}</p>" if row.get("erro") or row.get("erro_laya") else "")
                    + f"<div class='chips'>{chips}</div><p class='muted'>Em destaque, os trechos com algo mascarado; apagados, os que o filtro descartou.</p>"
                    + (f"<h3>O que o modelo achou</h3>{table(found)}" if found else "")
                    + f"<details><summary>Saída completa</summary>{pre(judgment)}</details></div>")
        elif kind == "escolha_ia":
            answer = row.get("resposta") or {}
            ranking = [{"rótulo": label if label is not None else "(nenhum)", "p": p} for label, p in answer.get("ranking") or []]
            out += (f"<div class='card'><h3>Modelo de escolha <small>{when} · {fmt_s(answer.get('seconds'))}</small></h3>"
                    f"<p><b>Procurava:</b> {esc(', '.join(map(str, row.get('pedido') or [])))} → "
                    f"<b>{esc(str(answer.get('label')) if answer.get('label') is not None else 'nenhum')}</b> "
                    f"<small>(p = {answer.get('p', 0):.2f}, {len(row.get('rotulos') or [])} rótulos na tela)</small></p>"
                    f"<details><summary>Ranking</summary>{table(ranking)}</details></div>")
        elif kind == "fim":
            swaps = [{"tipo": k, "real": real, "falso": fake} for k, pairs in (row.get("trocas") or {}).items() for real, fake in pairs.items()]
            out += (f"<div class='card'><h3>Fim da tarefa <small>{when}</small></h3><p><b>Resultado:</b> {esc(str(row.get('resultado')))} · "
                    f"{row.get('ajudas', 0)} ajudas</p><h3>Trocas real → falso da tarefa</h3>{table(swaps)}"
                    + "".join(f"<p><b>{label}:</b> {esc(', '.join(row.get(key) or [])) or '—'}</p>" for label, key in
                              (("Nomes extras mascarados", "nomes_extra"), ("Usuários extras", "usuarios_extra"), ("Liberados", "liberados")))
                    + f"<h3>Controles escolhidos</h3>{table(row.get('escolhas') or [], ['passo', 'escolhido', 'por', 'efeito', 'app'])}</div>")
        else:
            out += f"<details class='row'><summary><b>{esc(str(kind))}</b> <small>{when}</small></summary>{pre(row)}</details>"
    return out


def tasks_page():
    by = proxy_sessions()
    in_suite = {r.get("sessao"): (stamp, i) for stamp, records in suites().items() for i, r in enumerate(records)}
    rows = []
    for session, lines in sorted(by.items(), key=lambda kv: -kv[1][0]["ts"])[:300]:
        task = next((l["task"] for l in lines if "task" in l), "")
        if not task:
            continue
        end = next((l["exec"].get("resultado") for l in reversed(lines) if "exec" in l and l["exec"].get("resultado")), "")
        calls = sum("sent" in l for l in lines)
        where = in_suite.get(session)
        link = f"/rodada/{where[0]}/{where[1]}" if where else f"/sessao/{session}/pagina"
        rows.append(f"<tr class='link' data-href='{link}'><td class='n'>{esc(lines[0]['time'])}</td><td><a href='{link}'>{esc(task)}</a></td>"
                    f"<td>{esc(end)}</td><td class='n'>{calls}</td><td><small>{esc(where[0] if where else '—')}</small></td></tr>")
    body = ("<h1>Tarefas</h1><p class='muted'>As 300 últimas sessões de logs/proxy.jsonl. O pedido aparece como o provedor o viu (mascarado).</p>"
            "<div class='scroll'><table class='grid'><tr><th>Quando</th><th>Pedido</th><th>Resultado</th><th>Chamadas</th><th>Suíte</th></tr>"
            f"{''.join(rows)}</table></div>")
    return page("Tarefas", [("lm_phone", "/"), ("tarefas", None)], body)


def session_page(session):
    rows = proxy_sessions().get(session)
    if rows is None:
        return None
    task = next((l["task"] for l in rows if "task" in l), "")
    body = f"<h1>Tarefa {esc(session)}</h1><p><b>Pedido (mascarado):</b> {esc(task)}</p>{session_sections(session)}"
    return page(f"Tarefa {session}", [("lm_phone", "/"), ("tarefas", "/tarefas"), (session, None)], body)


def trace_page(session):
    rows = proxy_sessions().get(session)
    if not rows:
        return None
    try:
        return trace.render(session, rows)
    except Exception as e:
        return page("Diagrama", [], f"<p class='warn'>O diagrama não pôde ser montado: {esc(repr(e))}</p>")


# ---------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, kind="text/html; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
        try:
            body = None
            if not parts:
                body = home()
            elif parts[0] == "suite" and len(parts) == 2:
                body = suite_page(parts[1])
            elif parts[0] == "rodada" and len(parts) == 3 and parts[2].isdigit():
                body = round_page(parts[1], int(parts[2]))
            elif parts == ["tarefas"]:
                body = tasks_page()
            elif parts[0] == "sessao" and len(parts) == 2:
                body = trace_page(parts[1])
            elif parts[0] == "sessao" and len(parts) == 3 and parts[2] == "pagina":
                body = session_page(parts[1])
            elif parts == ["arquivo"]:
                return self.capture(urllib.parse.parse_qs(url.query))
            if body is None:
                return self.send(404, page("Não encontrado", [("lm_phone", "/")], "<h1>Não encontrado</h1>"))
            self.send(200, body)
        except Exception as e:
            self.send(500, page("Erro", [("lm_phone", "/")], f"<h1>Erro</h1>{pre(repr(e))}"))

    def capture(self, query):
        """Só arquivos de uma captura (data/capturas/<nome>/), sem sair da pasta."""
        name, file = (query.get("c") or [""])[0], (query.get("f") or [""])[0]
        if not re.fullmatch(r"[\w.-]+", name) or file not in ("tela.png", "tela.txt", "app.txt", "trechos.json"):
            return self.send(404, "")
        path = os.path.join("data", "capturas", name, file)
        if not os.path.isfile(path):
            return self.send(404, "")
        with open(path, "rb") as f:
            self.send(200, f.read(), "image/png" if file.endswith(".png") else "text/plain; charset=utf-8")


def main():
    parser = argparse.ArgumentParser(description="Painel local das suítes e tarefas")
    parser.add_argument("--porta", type=int, default=8770)
    options = parser.parse_args()
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", options.porta), Handler)
    print(f"Painel em http://127.0.0.1:{options.porta} (Ctrl+C encerra)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
