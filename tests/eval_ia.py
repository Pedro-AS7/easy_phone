"""Avalia a IA local nos casos de tests/ia_cases.py e gera um relatório visual.

Uso: .venv/bin/python -m tests.eval_ia
Saída: reports/ia-local.html (abra no navegador) e reports/ia-local.json.
Nada é enviado ao provedor: o relatório mostra o texto que seria enviado.
"""

import html
import json
import os
import re
import time

from lmphone import local_ai
from lmphone.masking import Masker, Vault

from .ia_cases import CASOS, CONTATOS, EMAILS, TELEFONES

OUT_DIR = "reports"
STATUS = {
    "ok": "Passou",
    "vazamento": "Vazamento",
    "excesso": "Mascarou demais",
    "intencao": "Intenção errada",
}
KIND = {"name": "nome", "email": "e-mail", "phone": "telefone", "cpf": "CPF", "card": "cartão",
        "handle": "@usuário", "literal": "usuário"}


def new_masker():
    masker = Masker(Vault())
    for name in CONTATOS:
        masker.add_name(name)
    for email in EMAILS:
        masker.vault.add("email", email)
    for phone in TELEFONES:
        masker.add_phone(phone)
    return masker


def run_case(case):
    masker = new_masker()
    text = case["entrada"]
    result = dict(case)

    # 1. O que as regras fixas pegam sozinhas (ensaio numa sessão separada).
    rules = []
    new_masker().mask(text, trace=rules)
    result["regras"] = rules

    # 2. Julgamento da IA local. Se ela falhar, valem só as regras fixas.
    judge, apply = (
        (local_ai.judge_request, local_ai.apply_request)
        if case["tipo"] == "pedido"
        else (local_ai.find_private, local_ai.apply_screen)
    )
    try:
        judgment, raw, seconds = judge(text)
        result["ia"] = {"julgamento": judgment, "bruto": raw, "segundos": round(seconds, 1)}
        # 3. Decisão por entidade.
        result["decisoes"] = apply(judgment, masker, text)
    except Exception as e:
        judgment = None
        result["ia"] = {"erro": repr(e)}
        result["decisoes"] = []

    # 4. Texto que o provedor receberia.
    swaps = []
    sent = masker.mask(text, trace=swaps)
    result["enviado"], result["trocas"] = sent, swaps
    result["volta"] = masker.unmask(sent) == text

    # 5. Conferência.
    checks = []
    for target in case["mascarar"]:
        checks.append({"regra": "mascarar", "alvo": target, "ok": target.casefold() not in sent.casefold()})
    for target in case["manter"]:
        checks.append({"regra": "manter", "alvo": target, "ok": target.casefold() in sent.casefold()})
    if case["intencao"]:
        got = judgment.get("intencao") if judgment else None
        checks.append({"regra": "intencao", "alvo": " ou ".join(case["intencao"]), "obtido": got,
                       "ok": got in case["intencao"]})
    result["checks"] = checks
    failed = {c["regra"] for c in checks if not c["ok"]}
    result["status"] = ("vazamento" if "mascarar" in failed else "excesso" if "manter" in failed
                        else "intencao" if "intencao" in failed else "ok")
    return result


# --- relatório ---

def esc(value):
    return html.escape(str(value), quote=True)


def highlight(text, needles, css):
    """Marca cada trecho de `needles` dentro de `text` (já devolve HTML)."""
    needles = sorted({n for n in needles if n}, key=len, reverse=True)
    if not needles:
        return esc(text)
    pattern = re.compile("|".join(re.escape(n) for n in needles))
    out, last = [], 0
    for match in pattern.finditer(text):
        out.append(esc(text[last:match.start()]))
        out.append(f'<mark class="{css}">{esc(match.group())}</mark>')
        last = match.end()
    out.append(esc(text[last:]))
    return "".join(out)


def render_case(index, r):
    ia = r["ia"]
    released = [d["texto"] for d in r["decisoes"] if d["decisao"] == "liberar"]
    step_input = highlight(r["entrada"], [s[1] for s in r["trocas"]], "real")
    step_input = step_input if not released else highlight_more(step_input, released)

    if r["regras"]:
        rules = "<ul class='pairs'>" + "".join(
            f"<li><span class='tag'>{esc(KIND.get(k, k))}</span> <mark class='real'>{esc(real)}</mark></li>"
            for k, real, _ in r["regras"]) + "</ul>"
    else:
        rules = "<p class='none'>Nenhuma regra fixa casou com este texto.</p>"

    if "erro" in ia:
        judgment = f"<p class='bad'>A IA local falhou: {esc(ia['erro'])}. Valeram só as regras fixas.</p>"
    else:
        j = ia["julgamento"]
        head = (f"<p>Intenção: <strong>{esc(j['intencao'])}</strong></p>" if r["tipo"] == "pedido" else "")
        items = j.get("entidades", j.get("itens", []))
        if items:
            rows = "".join(
                "<tr><td>{}</td><td>{}</td>{}</tr>".format(
                    esc(i["texto"]), esc(i["tipo"]),
                    f"<td>{'sim' if i.get('precisa_pesquisa') else 'não'}</td>" if r["tipo"] == "pedido" else "")
                for i in items)
            extra = "<th>Precisa de pesquisa</th>" if r["tipo"] == "pedido" else ""
            table = f"<div class='tw'><table><thead><tr><th>Trecho</th><th>Tipo</th>{extra}</tr></thead><tbody>{rows}</tbody></table></div>"
        else:
            table = "<p class='none'>A IA não apontou nenhuma entidade.</p>"
        judgment = (f"{head}{table}<details class='raw'><summary>Resposta bruta da IA ({ia['segundos']} s)</summary>"
                    f"<pre>{esc(ia['bruto'])}</pre></details>")

    if r["decisoes"]:
        decisions = "<ul class='decisions'>" + "".join(
            f"<li><span class='dec {esc(d['decisao'])}'>{esc(d['decisao'])}</span> "
            f"<strong>{esc(d['texto'])}</strong> <span class='why'>{esc(d['motivo'])}</span></li>"
            for d in r["decisoes"]) + "</ul>"
    else:
        decisions = "<p class='none'>Nenhuma decisão da IA; valem só as regras fixas.</p>"

    sent = highlight(r["enviado"], [s[2] for s in r["trocas"]], "fake")
    if r["trocas"]:
        swaps = "<ul class='pairs'>" + "".join(
            f"<li><span class='tag'>{esc(KIND.get(k, k))}</span> <mark class='real'>{esc(real)}</mark> → "
            f"<mark class='fake'>{esc(fake)}</mark></li>" for k, real, fake in r["trocas"]) + "</ul>"
    else:
        swaps = "<p class='none'>Nada foi trocado: o texto sai como entrou.</p>"

    labels = {"mascarar": "Não pode aparecer", "manter": "Precisa aparecer", "intencao": "Intenção esperada"}
    checks = "<ul class='checks'>" + "".join(
        "<li class='{}'><span class='mark'>{}</span> {}: <strong>{}</strong>{}</li>".format(
            "pass" if c["ok"] else "fail", "✓" if c["ok"] else "✗", labels[c["regra"]], esc(c["alvo"]),
            f" (a IA respondeu: {esc(c.get('obtido'))})" if c["regra"] == "intencao" and not c["ok"] else "")
        for c in r["checks"]) + "</ul>"
    back = "" if r["volta"] else "<p class='bad'>A tradução de volta não reconstruiu o texto original.</p>"

    kind = "Pedido" if r["tipo"] == "pedido" else "Texto de tela"
    return f"""
<details class="case {r['status']}" data-status="{r['status']}">
  <summary>
    <span class="num">{index:02d}</span>
    <span class="status">{STATUS[r['status']]}</span>
    <span class="title">{esc(r['entrada'])}</span>
    <span class="group">{esc(r['grupo'])}</span>
  </summary>
  <ol class="steps">
    <li><h3>Entrada <span class="hint">{kind}, como chegou à IA local</span></h3><p class="text">{step_input}</p></li>
    <li><h3>Regras fixas <span class="hint">cofre e padrões, sem IA</span></h3>{rules}</li>
    <li><h3>Julgamento da IA local</h3>{judgment}</li>
    <li><h3>Decisão por entidade</h3>{decisions}</li>
    <li><h3>O que foi trocado</h3>{swaps}</li>
    <li><h3>Texto que o provedor recebe</h3><p class="text sent">{sent}</p>{back}</li>
    <li><h3>Conferência</h3>{checks}</li>
  </ol>
</details>"""


def highlight_more(html_text, released):
    for needle in sorted(set(released), key=len, reverse=True):
        html_text = html_text.replace(esc(needle), f'<mark class="free">{esc(needle)}</mark>')
    return html_text


def render(results, started):
    total = len(results)
    count = {key: sum(r["status"] == key for r in results) for key in STATUS}
    times = [r["ia"]["segundos"] for r in results if "segundos" in r["ia"]]
    groups = {}
    for r in results:
        g = groups.setdefault(r["grupo"], [0, 0])
        g[0] += r["status"] == "ok"
        g[1] += 1
    group_rows = "".join(
        f"<tr><td>{esc(name)}</td><td class='n'>{ok} de {n}</td>"
        f"<td><span class='bar'><span style='width:{100 * ok // n}%'></span></span></td></tr>"
        for name, (ok, n) in groups.items())
    cases = "".join(render_case(i, r) for i, r in enumerate(results, 1))
    avg = f"{sum(times) / len(times):.1f} s" if times else "sem medição"
    worst = f"{max(times):.1f} s" if times else "sem medição"
    return f"""<meta charset="utf-8">
<title>Avaliação da IA local</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: resumo no topo, depois uma lista de casos que abrem para mostrar os 7 passos em ordem. */
:root {{
  --bg: #f2f5f3; --fg: #16211d; --muted: #586661; --surface: #ffffff; --line: #c5d0cb;
  --ok: #1d6b4f; --ok-soft: #dcefe6; --leak: #b3261e; --leak-soft: #f9dedb;
  --warn: #8a5a00; --warn-soft: #f6e8c9; --real: #f9dedb; --fake: #dfe6f7; --free: #dcefe6;
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0e1513; --fg: #e3ebe7; --muted: #94a39d; --surface: #18221f; --line: #33423d;
    --ok: #6fd3a8; --ok-soft: #16332a; --leak: #ff8a80; --leak-soft: #3d1a17;
    --warn: #f0c060; --warn-soft: #3a2e12; --real: #4a211d; --fake: #233052; --free: #16332a;
    color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0e1513; --fg: #e3ebe7; --muted: #94a39d; --surface: #18221f; --line: #33423d;
  --ok: #6fd3a8; --ok-soft: #16332a; --leak: #ff8a80; --leak-soft: #3d1a17;
  --warn: #f0c060; --warn-soft: #3a2e12; --real: #4a211d; --fake: #233052; --free: #16332a;
  color-scheme: dark;
}}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.55 var(--body); padding-inline: 16px; padding-block: 40px 64px; margin: 0; }}
main {{ max-width: 980px; margin-inline: auto; display: flex; flex-direction: column; gap: 32px; }}
header {{ display: flex; flex-direction: column; gap: 10px; }}
h1 {{ font: 700 clamp(28px, 5vw, 38px)/1.1 var(--display); margin: 0; text-wrap: balance; }}
h2 {{ font: 600 21px/1.2 var(--display); margin: 0; }}
h3 {{ font: 600 14px/1.3 var(--body); margin: 0 0 6px; }}
p {{ margin: 0; max-width: 70ch; }}
.lede, .hint, .none, .why {{ color: var(--muted); }}
.hint {{ font-weight: 400; font-size: 13px; margin-left: 6px; }}
.none {{ font-size: 14px; }}
.bad {{ color: var(--leak); font-weight: 500; }}
section {{ display: flex; flex-direction: column; gap: 14px; }}

.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }}
.tile {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; display: flex; flex-direction: column; gap: 2px; }}
.tile b {{ font: 700 30px/1.1 var(--display); font-variant-numeric: tabular-nums; }}
.tile span {{ font-size: 13px; color: var(--muted); }}
.tile.leak b {{ color: var(--leak); }} .tile.ok b {{ color: var(--ok); }} .tile.warn b {{ color: var(--warn); }}

.tw {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 7px 14px 7px 0; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ font: 500 11.5px var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }}
td.n {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
.bar {{ display: block; width: 100%; min-width: 80px; height: 8px; background: var(--line); border-radius: 4px; overflow: hidden; }}
.bar span {{ display: block; height: 100%; background: var(--ok); }}

.filters {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.filters button {{ font: 500 13px var(--body); color: var(--fg); background: var(--surface); border: 1px solid var(--line); border-radius: 999px; padding: 6px 14px; cursor: pointer; }}
.filters button[aria-pressed="true"] {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
.filters button:focus-visible, summary:focus-visible {{ outline: 2px solid var(--fg); outline-offset: 2px; }}

.cases {{ display: flex; flex-direction: column; gap: 8px; }}
.case {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }}
.case > summary {{ display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: 4px 12px; align-items: baseline; padding: 12px 16px; cursor: pointer; list-style: none; }}
.case > summary::-webkit-details-marker {{ display: none; }}
.num {{ font: 500 12px var(--mono); color: var(--muted); }}
.status {{ font: 500 11.5px var(--mono); letter-spacing: .04em; padding: 2px 8px; border-radius: 4px; white-space: nowrap; }}
.case.ok .status {{ background: var(--ok-soft); color: var(--ok); }}
.case.vazamento .status {{ background: var(--leak-soft); color: var(--leak); }}
.case.excesso .status, .case.intencao .status {{ background: var(--warn-soft); color: var(--warn); }}
.title {{ font-weight: 500; min-width: 0; overflow-wrap: anywhere; }}
.group {{ grid-column: 3; font-size: 13px; color: var(--muted); }}
.steps {{ margin: 0; padding: 4px 16px 18px 40px; display: flex; flex-direction: column; gap: 16px; border-top: 1px solid var(--line); padding-top: 16px; }}
.steps > li {{ min-width: 0; }}
.steps > li::marker {{ font: 500 12px var(--mono); color: var(--muted); }}
.text {{ font: 14px/1.6 var(--mono); background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 10px 12px; max-width: none; overflow-wrap: anywhere; }}
.text.sent {{ border-color: var(--fg); }}
mark {{ color: inherit; border-radius: 3px; padding: 1px 3px; }}
mark.real {{ background: var(--real); }} mark.fake {{ background: var(--fake); }} mark.free {{ background: var(--free); }}
ul.pairs, ul.decisions, ul.checks {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 14px; }}
.tag {{ font: 500 11px var(--mono); color: var(--muted); display: inline-block; min-width: 72px; }}
.pairs mark {{ font-family: var(--mono); font-size: 13px; }}
.dec {{ font: 500 11.5px var(--mono); padding: 2px 8px; border-radius: 4px; display: inline-block; min-width: 76px; text-align: center; }}
.dec.mascarar {{ background: var(--real); }} .dec.liberar {{ background: var(--free); }} .dec.manter {{ background: var(--bg); border: 1px solid var(--line); }}
.checks .mark {{ font-weight: 700; display: inline-block; width: 18px; }}
.checks .pass .mark {{ color: var(--ok); }} .checks .fail {{ color: var(--leak); }}
.raw summary {{ font-size: 13px; color: var(--muted); cursor: pointer; margin-top: 8px; }}
pre {{ font: 12.5px/1.5 var(--mono); background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 10px 12px; overflow-x: auto; margin: 6px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); }}
</style>
<main>
  <header>
    <h1>Avaliação da IA local</h1>
    <p class="lede">{total} casos com dados fictícios, rodados em {esc(started)} com o modelo <strong>{esc(local_ai.MODEL)}</strong>. Cada caso mostra o caminho inteiro: o que entrou, o que as regras fixas pegaram, o que a IA julgou, o que foi trocado e o texto que o provedor receberia. Nada foi enviado ao provedor.</p>
  </header>

  <section>
    <div class="tiles">
      <div class="tile ok"><b>{count['ok']} de {total}</b><span>casos passaram</span></div>
      <div class="tile leak"><b>{count['vazamento']}</b><span>vazamentos: dado privado saiu sem máscara</span></div>
      <div class="tile warn"><b>{count['excesso']}</b><span>mascarou algo que devia ficar</span></div>
      <div class="tile warn"><b>{count['intencao']}</b><span>só a intenção errada</span></div>
      <div class="tile"><b>{avg}</b><span>tempo médio da IA por caso (pior: {worst})</span></div>
    </div>
  </section>

  <section>
    <h2>Por grupo</h2>
    <div class="tw"><table><thead><tr><th>Grupo</th><th>Passaram</th><th></th></tr></thead><tbody>{group_rows}</tbody></table></div>
  </section>

  <section>
    <h2>Casos</h2>
    <div class="legend">
      <span><mark class="real">dado real que foi trocado</mark></span>
      <span><mark class="fake">valor falso</mark></span>
      <span><mark class="free">liberado para pesquisa</mark></span>
    </div>
    <div class="filters" role="group" aria-label="Filtrar casos">
      <button type="button" id="f-todos" data-filter="todos" aria-pressed="true">Todos ({total})</button>
      <button type="button" id="f-falhas" data-filter="falhas" aria-pressed="false">Só falhas ({total - count['ok']})</button>
      <button type="button" id="f-vazamento" data-filter="vazamento" aria-pressed="false">Vazamentos ({count['vazamento']})</button>
      <button type="button" id="f-abrir" data-toggle="1" aria-pressed="false">Abrir todos</button>
    </div>
    <div class="cases">{cases}</div>
  </section>
</main>
<script>
(function () {{
  var cases = Array.prototype.slice.call(document.querySelectorAll('.case'));
  var filters = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
  filters.forEach(function (button) {{
    button.addEventListener('click', function () {{
      var f = button.dataset.filter;
      filters.forEach(function (b) {{ b.setAttribute('aria-pressed', b === button ? 'true' : 'false'); }});
      cases.forEach(function (c) {{
        var s = c.dataset.status;
        c.hidden = !(f === 'todos' || (f === 'falhas' && s !== 'ok') || f === s);
      }});
    }});
  }});
  var toggle = document.querySelector('[data-toggle]');
  toggle.addEventListener('click', function () {{
    var open = toggle.getAttribute('aria-pressed') !== 'true';
    toggle.setAttribute('aria-pressed', open ? 'true' : 'false');
    toggle.textContent = open ? 'Fechar todos' : 'Abrir todos';
    cases.forEach(function (c) {{ c.open = open; }});
  }});
}})();
</script>
"""


def main():
    local_ai.BACKEND = "gemma"  # esta avaliação é da Gemma (os modelos pequenos: tests.eval_base --novo)
    started = time.strftime("%d/%m/%Y %H:%M")
    results = []
    for i, case in enumerate(CASOS, 1):
        result = run_case(case)
        results.append(result)
        print(f"{i:02d} {STATUS[result['status']]:16} {result['ia'].get('segundos', 'erro')!s:>5}  {case['entrada'][:70]}")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "ia-local.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT_DIR, "ia-local.html"), "w", encoding="utf-8") as f:
        f.write(render(results, started))
    ok = sum(r["status"] == "ok" for r in results)
    print(f"\n{ok} de {len(results)} passaram; vazamentos: {sum(r['status'] == 'vazamento' for r in results)}")
    print(f"relatório: {OUT_DIR}/ia-local.html")


if __name__ == "__main__":
    main()
