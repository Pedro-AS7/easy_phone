@echo off
rem Roda uma tarefa no celular: run "Turn on dark mode" | --stop | --stop-laya (o que faz esta em lmphone\run.py).
setlocal
set PYTHONUTF8=1
pushd "%~dp0"
".venv\Scripts\python.exe" -m lmphone.run %*
set code=%errorlevel%
popd
exit /b %code%
