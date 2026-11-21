"""Manda uma tarefa ao serviço (service.py) e mostra o andamento.

Uso: python -m lmphone.client "pedido"
Com LMPHONE_CONVERSA (um id), o pedido continua a conversa desse id: o assistente lembra os pedidos anteriores.
Sai com 0 se a tarefa foi concluída, 1 se não, 2 se o serviço não a aceitou. Interromper o cliente interrompe a tarefa.
"""

import json
import os
import sys
import urllib.error
import urllib.request

from . import bridge


def main(task=None, conversation=None):
    port = os.environ.get("LMPHONE_SERVICE_PORT", "8789")
    body = {"task": task or sys.argv[1], "conversa": conversation or os.environ.get("LMPHONE_CONVERSA") or None,
            "model": os.environ.get("MODEL") or None, "cache": os.environ.get("LMPHONE_CACHE", "1") != "0",
            "coleta": os.environ.get("LMPHONE_COLETA") == "1",
            # Live mode: o agente pode perguntar ao dono pela faixa. A suíte desliga (ninguém responde).
            "perguntar": os.environ.get("LMPHONE_PERGUNTAR", "1") != "0",
            # Começa na vez do dono (live mode, etapa 5): o agente mostra cada passo e espera ele fazer.
            "dono": os.environ.get("LMPHONE_VEZ_DO_DONO") == "1",
            # No guia, o agente toca (depois de uns segundos) em vez de esperar a pessoa: a opção do app, para testar.
            "guia_agente": os.environ.get("LMPHONE_GUIA") == "agente",
            # Só guia, como o app da loja (docs/plano-play-store.md): o agente nunca age.
            "agir": os.environ.get("LMPHONE_AGIR", "1") != "0"}
    request = urllib.request.Request(f"http://127.0.0.1:{port}/task", data=json.dumps(body).encode(),
                                     headers={"X-Lmphone-Token": bridge.read_token() or ""})
    done = None
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw in response:
                line = raw.decode(errors="replace")
                if line.startswith(("Goal achieved:", "Goal failed:")):
                    done = line.startswith("Goal achieved:")
                print(line, end="", flush=True)
    except urllib.error.HTTPError as e:
        print(f"O serviço recusou a tarefa: {e.read().decode(errors='replace')}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Sem resposta do serviço: {e}", file=sys.stderr)
        return 2
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
