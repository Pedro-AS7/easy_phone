#!/bin/sh
# Roda uma tarefa no celular: ./run.sh "Turn on dark mode" | --stop | --stop-laya (o que faz está em lmphone/run.py).
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m lmphone.run "$@"
