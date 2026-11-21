"""Os casos de guia e de sintoma da suíte (tests/phone_cases.py) no app da loja, no celular, com a pessoa simulada.

Para cada caso e cada rodada: o preparo da suíte (`phone_suite.prepare`: o estado do começo, pelo adb), o pedido ao
app da loja com a pessoa simulada fazendo o que o guia pede (`pessoa_loja.rodar`; no caso "erra", ela aperta Voltar no
primeiro destaque; "olha" vira "toca", porque na loja só a pessoa faz), as conferências da suíte (`phone_suite.verify`:
o ajuste no aparelho, a resposta, os critérios do guia no registro do live mode), o preparo desfeito e a gravação da
rodada em tests/gravacoes/<caso>-<n>.jsonl (`tests.gravacao`: repetir, comparar com o simulador).

A acessibilidade da loja é ligada no começo e desligada no fim. A suíte divide o celular com quem o usa: antes de cada
rodada, espera ele ficar PARADO segundos sem nenhum toque nem tecla (o `getevent`, como a `varredura.Vigia`); se alguém
mexer no meio da rodada, ela é desfeita e repetida depois (até REPETE vezes). O resumo vai para reports/loja-<hora>.json.

    .venv/bin/python -m tests.loja_suite                     # todos os casos de guia e de sintoma, 3 rodadas cada
    .venv/bin/python -m tests.loja_suite guia-letra --vezes 1
"""

import argparse
import json
import os
import sys
import time

from tests import gravacao, pessoa_loja, phone_suite, varredura
from tests.casos_loja import CASOS
from tests.phone_cases import CASES

SERVICO = "dev.pedro.lmphone.guia/dev.pedro.lmphone.AgentService"
NIVEIS = ("guia", "sintoma")
PARADO = 15  # segundos sem toque antes de uma rodada
RESULTADOS_BONS = ("confirmado", "já estava", "respondido", "lido")
REPETE = 2  # rodadas desfeitas por um toque de alguém, repetidas no máximo isto


def esperar_parado(segundos=PARADO, limite=4 * 3600):
    """Espera o celular ficar `segundos` sem toque nem tecla (até `limite`). Devolve False se não ficou."""
    comeco = time.monotonic()
    while time.monotonic() - comeco < limite:
        vigia = varredura.Vigia()
        vigia.start()
        time.sleep(segundos)
        vigia.parar()
        if not vigia.mexeu:
            return True
        print(f"{time.strftime('%H:%M:%S')}   um toque na tela: espero {segundos} s sem toque para a próxima rodada", flush=True)
    return False


def acessibilidade(ligar):
    if ligar:
        pessoa_loja.adb("shell", "settings", "put", "secure", "enabled_accessibility_services", SERVICO)
        pessoa_loja.adb("shell", "settings", "put", "secure", "accessibility_enabled", "1")
        time.sleep(2)
    else:
        pessoa_loja.adb("shell", "settings", "delete", "secure", "enabled_accessibility_services")


def apagar_lanterna():
    """Apaga a lanterna pelo bloco do painel de atalhos (One UI 9: pelo lado direito do alto, «Expandir», rolar). O
    truque da suíte de abrir e fechar a câmera não a apaga nesta One UI (2026-11-19)."""
    if not phone_suite.torch_on():
        return
    pessoa_loja.adb("shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(1)
    for gesto in (("900", "5", "900", "1200"), ("tap", "540", "1908"), ("540", "1600", "540", "800")):
        pessoa_loja.adb("shell", "input", *(gesto if gesto[0] == "tap" else ("swipe", *gesto, "500")))
        time.sleep(1.5)
    tela = varredura.Varredura().ler()
    bloco = next((e for e in tela.elementos if e["text"] == "Lanterna" and e["checked"]), None)
    if bloco:
        x1, y1, x2, y2 = bloco["bounds"]
        pessoa_loja.adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
        time.sleep(1)
    pessoa_loja.adb("shell", "cmd", "statusbar", "collapse")


phone_suite.torch_off = apagar_lanterna


def rodada(caso, n, vigia):
    """Uma rodada de um caso. Devolve o registro dela."""
    registro = {"caso": caso["id"], "rodada": n, "erros": []}
    desfazer = []
    try:
        desfazer = phone_suite.prepare(caso)
        time.sleep(1.0)
        comeco = time.monotonic()
        linhas, feitos, terminou = pessoa_loja.rodar(caso["pedido"], erra=caso.get("pessoa") == "erra")
        registro["segundos"] = round(time.monotonic() - comeco)
        fim = next((r for r in reversed(linhas) if r.get("tipo") == "fim"), {})
        registro["resultado"] = fim.get("resultado") if terminou else "tempo esgotado"
        registro["resposta"] = fim.get("mensagem") or ""
        registro["pessoa"] = feitos
        registro["agente_agiu"] = [r for r in linhas if r.get("tipo") == "acao" and r.get("por") != "dono"
                                   and r.get("ferramenta") not in ("wait", "complete")]
        if vigia.mexeu:
            raise varredura.Parar(f"alguém mexeu no celular ({vigia.mexeu})")
        checks, _ = phone_suite.verify(caso, registro["resposta"], {}, live=linhas, person=None)
        registro["confere"] = [{"nome": nome, "ok": ok, "detalhe": detalhe} for nome, ok, detalhe in checks]
    except phone_suite.SetupError as e:
        registro["erros"].append(f"preparo: {e}")
    finally:
        for undo in reversed(desfazer):
            try:
                undo()
            except Exception as e:  # o desfazer não pode parar a suíte
                registro["erros"].append(f"ao desfazer o preparo: {e!r}")
    if "resultado" not in registro:
        return registro  # o pedido nem foi feito: não há gravação desta rodada
    try:
        registro["gravacao"] = gravacao.puxar(f"{caso['id']}-{n}")
        eventos = gravacao.ler(registro["gravacao"])
        registro["ajudas"] = sum(1 for e in eventos if e["tipo"] == "cb" and e["cb"] == "provider"
                                 and "You live on their phone" not in (e.get("pergunta") or ""))
        registro["repeticao"] = len(gravacao.repetir(eventos).diferencas)
    except Exception as e:
        registro["erros"].append(f"gravação: {e!r}")
    return registro


def linha(r):
    falhas = [c["nome"] for c in r.get("confere", []) if c["ok"] is False]
    # «lido»: o guia leu na tela que já estava como pedido (2026-11-19: a agenda «Dormir» do Não perturbar já existia).
    ok = r.get("resultado") in RESULTADOS_BONS and not falhas and not r["erros"] and not r.get("agente_agiu")
    return (f"{'ok   ' if ok else 'FALHA'} {r['caso']} #{r['rodada']}: {r.get('resultado')}, {r.get('segundos', '?')} s, "
            f"{r.get('ajudas', '?')} ajuda(s), repetição {r.get('repeticao', '?')} dif."
            + (f"\n      falhou: {'; '.join(falhas)}" if falhas else "")
            + (f"\n      erros: {'; '.join(r['erros'])}" if r["erros"] else "")
            + (f"\n      o agente agiu: {r['agente_agiu'][:1]}" if r.get("agente_agiu") else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("casos", nargs="*", help="ids de tests/phone_cases.py (sem nenhum, os de guia e de sintoma)")
    parser.add_argument("--vezes", type=int, default=3)
    args = parser.parse_args()
    todos = CASES + CASOS  # os da suíte e os 50 do app da loja (tests/casos_loja.py), os mesmos do simulador
    casos = [c for c in todos if (c["id"] in args.casos if args.casos else c.get("nivel") in NIVEIS)]
    registros = []
    saida = os.path.join("reports", f"loja-{time.strftime('%Y-%m-%d-%H%M%S')}.json")
    os.makedirs("reports", exist_ok=True)
    try:
        for caso in casos:
            for n in range(1, args.vezes + 1):
                for tentativa in range(REPETE + 1):
                    print(f"{time.strftime('%H:%M:%S')}   {caso['id']} #{n}: começa", flush=True)
                    if not esperar_parado():
                        raise varredura.Parar("o celular não ficou parado")
                    pessoa_loja.adb("reverse", "tcp:8792", "tcp:8792")  # o servidor da loja no PC (some quando o celular reconecta)
                    acessibilidade(True)
                    vigia = varredura.Vigia()
                    vigia.start()
                    try:
                        r = rodada(caso, n, vigia)
                    except varredura.Parar as parada:
                        r = {"caso": caso["id"], "rodada": n, "erros": [str(parada)], "interrompida": True}
                    finally:
                        vigia.parar()
                        acessibilidade(False)
                    if not r.get("interrompida"):
                        break
                    print(f"{time.strftime('%H:%M:%S')}   {caso['id']} #{n}: alguém mexeu no celular no meio; desfeita, vai de novo",
                          flush=True)
                registros.append(r)
                print(f"{time.strftime('%H:%M:%S')} {linha(r)}", flush=True)
                with open(saida, "w", encoding="utf-8") as f:
                    json.dump(registros, f, ensure_ascii=False, indent=1)
    except varredura.Parar as parada:
        print(f"PAROU: {parada}", flush=True)
    finally:
        acessibilidade(False)
    print(f"{saida}: {len(registros)} rodadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
