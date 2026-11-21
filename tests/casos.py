"""Os 50 casos de tests/casos_loja.py no simulador, todos de uma vez (os mesmos que `tests.loja_suite` roda no celular).

Cada caso vira uma rodada do simulador com as telas de verdade (tests/celular_real.py): o preparo do caso é o estado do
começo do celular simulado, o provedor é o Haiku de verdade e o modelo de escolha é o de verdade (o servidor dos
modelos pequenos na porta 8788, que este comando sobe se faltar). As conferências do caso são as da suíte, aplicadas aos
fatos do aparelho simulado, à resposta final e ao registro no formato da faixa (`Simulacao.live`, lido por
`phone_suite.guide_checks`). As rodadas vão em paralelo, em processos (cada um troca o relógio do executor).

O resumo vai para reports/casos-sim-<hora>.json, e a gravação de cada rodada para reports/casos-sim-<hora>/<caso>.jsonl
(`tests.gravacao linha`, `repetir`).

    .venv/bin/python -m tests.casos                  # os 50, em 8 processos
    .venv/bin/python -m tests.casos caso-letra-erra caso-dnd-ligar --processos 2
"""

import argparse
import json
import multiprocessing
import os
import re
import subprocess
import sys
import time
import urllib.request

from tests import casos_loja, gravacao, phone_suite, simulador

# O celular do Pedro fora dos testes (2026-11-19): o estado de que o preparo de cada caso parte.
PADRAO = dict(dnd=False, modo="vibrar", toque=0, midia=0, fonte=1.0, brilho=35, brilho_auto=True, girar=True,
              tela_apaga=600, escuro=True, local=True, lanterna=False)
RESULTADOS_BONS = ("confirmado", "já estava", "respondido", "conferido", "lido")  # os de tests/loja_suite.py


def estado(caso):
    """O preparo do caso (o formato de tests/phone_cases.py) como o estado do celular simulado."""
    kw = dict(PADRAO)
    for kind, *args in caso.get("preparo", []):
        if kind == "ajuste":
            key, value = args
            if key == "font_scale":
                kw["fonte"] = float(value)
            elif key == "screen_brightness":
                kw["brilho"] = round(int(value) * 100 / 255)
            elif key == "screen_brightness_mode":
                kw["brilho_auto"] = value == "1"
            elif key == "accelerometer_rotation":
                kw["girar"] = value == "1"
            elif key == "screen_off_timeout":
                kw["tela_apaga"] = int(value) // 1000
        elif kind == "noturno":
            kw["escuro"] = args[0] == "yes"
        elif kind == "nao_perturbe":
            kw["dnd"] = args[0] == "on"
        elif kind == "modo_som":
            kw["modo"] = args[0]
        elif kind == "volume":
            stream, value = args
            kw["toque" if stream == 2 else "midia"] = round(value * 100 / 15)
        elif kind == "localizacao":
            kw["local"] = args[0] == "on"
        elif kind == "lanterna":
            kw["lanterna"] = False
    if kw["modo"] != "som":
        kw["toque"] = 0  # em Vibrar ou Silenciar a barra do toque fica no zero
    return kw


def _ajuste(key, fatos):
    """O valor de um ajuste do sistema (como `settings get`) a partir dos fatos do celular simulado."""
    return {"font_scale": fatos.get("font_scale"), "screen_brightness": round((fatos.get("brightness") or 0) * 255 / 100),
            "accelerometer_rotation": "1" if fatos.get("auto_rotate") else "0",
            "screen_off_timeout": (fatos.get("screen_timeout") or 0) * 1000,
            "ui_night_mode": "2" if fatos.get("dark_mode") else "1",
            "zen_mode": "1" if fatos.get("do_not_disturb") else "0",
            "screen_brightness_mode": "1" if fatos.get("auto_brightness") else "0"}.get(key)


def verificar(caso, sim):
    """As conferências do caso no fim da rodada simulada, com os nomes das da suíte (phone_suite.verify)."""
    fatos, estado_ = sim.celular.fatos(), sim.celular.estado
    resposta = (sim.fim or (None, ""))[1] or ""
    checks = []
    for kind, *args in caso["confere"]:
        if kind == "ajuste":
            got = _ajuste(args[0], fatos)
            checks.append((f"ajuste {args[0]} = {args[1]}", str(got) == args[1], f"está em {got}"))
        elif kind in ("ajuste_maior", "ajuste_menor"):
            got, limit = _ajuste(args[0], fatos), float(args[1])
            ok = got is not None and (float(got) > limit if kind == "ajuste_maior" else float(got) < limit)
            checks.append((f"ajuste {args[0]} {'>' if kind == 'ajuste_maior' else '<'} {args[1]}", ok, f"está em {got}"))
        elif kind in ("volume_min", "volume_max"):
            stream, n = args
            got = round((fatos.get("ring_volume" if stream == 2 else "media_volume") or 0) * 15 / 100)
            ok = got >= n if kind == "volume_min" else got <= n
            checks.append((f"volume do fluxo {stream} em {n} ou {'mais' if kind == 'volume_min' else 'menos'}", ok, f"está em {got}"))
        elif kind == "modo_som":
            checks.append((f"modo de som {args[0]}", fatos.get("sound_mode") == args[0], f"está em {fatos.get('sound_mode')}"))
        elif kind == "localizacao":
            got = bool(fatos.get("location"))
            checks.append((f"localização {'ligada' if args[0] else 'desligada'}", got is args[0], f"está {'ligada' if got else 'desligada'}"))
        elif kind == "nao_perturbe":
            got = bool(fatos.get("do_not_disturb"))
            checks.append((f"Não perturbe {'ligado' if args[0] else 'desligado'}", got is args[0], f"está {'ligado' if got else 'desligado'}"))
        elif kind == "silencio":
            quiet = bool(fatos.get("do_not_disturb")) or fatos.get("sound_mode") in ("vibrar", "mudo")
            checks.append(("sem tocar (Não perturbe, vibrar ou mudo)", quiet, "" if quiet else "o celular ainda toca"))
        elif kind == "lanterna":
            got = bool(estado_.get("lanterna"))
            checks.append((f"lanterna {'acesa' if args[0] else 'apagada'}", got is args[0], f"está {'acesa' if got else 'apagada'}"))
        elif kind == "resposta":
            hit = bool(re.search(args[0], resposta, re.I | re.S))
            checks.append((f"resposta casa com {args[0]}", hit, "" if hit else "a resposta não tem o valor esperado"))
        elif kind == "guia":
            checks += phone_suite.guide_checks(args or phone_suite.GUIDE_CRITERIA, sim.live, None)
    return checks


def rodar_caso(args):
    """Uma rodada de um caso no simulador (num processo à parte). Devolve o registro dela."""
    caso, pasta, modelo, n = args
    comeco = time.monotonic()
    cenario = dict(simulador.REAIS, pedido=caso["pedido"], celular=dict(simulador.REAIS["celular"], **estado(caso)),
                   provedor_real=True, escolha_real=True, modelo=modelo, fatos={}, botoes=None, ajudas_max=99,
                   segundos_max=simulador.LIMITE, pessoa=dict(simulador.REAIS["pessoa"], erra=caso.get("pessoa") == "erra"))
    try:
        sim = simulador.rodar(cenario)
    except Exception as e:  # um caso que quebra o simulador não para os outros
        return {"caso": caso["id"], "nivel": caso["nivel"], "erro": repr(e)}
    nome = caso["id"] + (f"-{n}" if n else "")
    gravacao.gravar(os.path.join(pasta, f"{nome}.jsonl"), sim.gravacao)
    gravacao.gravar(os.path.join(pasta, f"{nome}.live.jsonl"), sim.live)  # o registro da faixa (as conferências do guia)
    checks = verificar(caso, sim)
    return {"caso": caso["id"], "rodada": n, "nivel": caso["nivel"], "pedido": caso["pedido"], "resultado": (sim.fim or (None,))[0],
            "resposta": (sim.fim or (None, ""))[1], "segundos": round(sim.relogio.agora - sim.inicio),
            "ajudas": sim.provedor.pedidos.count("ajuda"), "custo": round(sim.provedor.custo, 5),
            "relogio": round(time.monotonic() - comeco), "agente_agiu": sim.acoes[:2],
            "fora_da_varredura": sorted(set(sim.celular.fora))[:6],
            "confere": [{"nome": n, "ok": ok, "detalhe": d} for n, ok, d in checks]}


def servidor_dos_modelos():
    """O servidor dos modelos pequenos (o modelo de escolha) na porta 8788; sobe se faltar."""
    url = f"http://127.0.0.1:{os.environ.get('LMPHONE_LAYA_PORT', '8788')}/health"
    try:
        urllib.request.urlopen(url, timeout=2)
        return
    except OSError:
        pass
    subprocess.Popen([".venv-modelo/bin/python", "-m", "lmphone.modelo_server"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(60):
        time.sleep(1)
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            continue
    raise SystemExit("o servidor dos modelos pequenos não subiu")


def linha(r):
    if r.get("erro"):
        return f"ERRO  {r['caso']}: {r['erro']}"
    falhas = [c["nome"] for c in r["confere"] if c["ok"] is False]
    ok = r["resultado"] in RESULTADOS_BONS and not falhas and not r["agente_agiu"]
    return (f"{'ok   ' if ok else 'FALHA'} {r['caso']}{' #' + str(r['rodada']) if r.get('rodada') else ''}: {r['resultado']}, {r['segundos']} s, {r['ajudas']} ajuda(s)"
            + (f"\n      falhou: {'; '.join(falhas)}" if falhas else "")
            + (f"\n      fora da varredura: {r['fora_da_varredura']}" if r["fora_da_varredura"] else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("casos", nargs="*", help="ids de tests/casos_loja.py (sem nenhum, os 50)")
    parser.add_argument("--processos", type=int, default=8)
    parser.add_argument("--vezes", type=int, default=1, help="rodadas de cada caso (o provedor varia entre elas)")
    parser.add_argument("--modelo", help="o modelo do provedor (padrão: MODEL ou anthropic/claude-haiku-5.5)")
    args = parser.parse_args()
    casos = [c for c in casos_loja.CASOS if not args.casos or c["id"] in args.casos]
    servidor_dos_modelos()
    hora = time.strftime("%Y-%m-%d-%H%M%S")
    pasta = os.path.join("reports", f"casos-sim-{hora}")
    os.makedirs(pasta, exist_ok=True)
    registros = []
    with multiprocessing.Pool(args.processos) as pool:
        tarefas = [(c, pasta, args.modelo, n if args.vezes > 1 else 0) for c in casos for n in range(1, args.vezes + 1)]
        for r in pool.imap_unordered(rodar_caso, tarefas):
            registros.append(r)
            print(linha(r), flush=True)
    registros.sort(key=lambda r: ([c["id"] for c in casos].index(r["caso"]), r.get("rodada") or 0))
    with open(pasta + ".json", "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=1)
    bons = sum(1 for r in registros if not r.get("erro") and r["resultado"] in RESULTADOS_BONS
               and not any(c["ok"] is False for c in r["confere"]) and not r["agente_agiu"])
    print(f"\n{bons} de {len(registros)} sem falha; custo do provedor US$ {sum(r.get('custo', 0) for r in registros):.4f}; "
          f"{pasta}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
