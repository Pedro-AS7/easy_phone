@echo off
rem Compila o app, instala no celular pelo adb e abre (etapa 0 de docs/plano-app-android.md).
rem Sem argumento, a variante completo (a de sempre); "build loja", a da Play Store (docs/plano-play-store.md).
rem JAVA_HOME e ANDROID_HOME ficam no ambiente do usuario (ver CLAUDE.md).
cd /d "%~dp0"
set variant=%1
if "%variant%"=="" set variant=completo
if "%variant%"=="completo" (set package=dev.pedro.lmphone& set task=assembleCompletoDebug)
if "%variant%"=="loja" (set package=dev.pedro.lmphone.guia& set task=assembleLojaDebug)
if "%task%"=="" (echo variante desconhecida: %variant% & exit /b 1)
call "%~dp0gradlew.bat" %task% --console=plain -q || exit /b 1
adb install -r "%~dp0app/build/outputs/apk/%variant%/debug/app-%variant%-debug.apk" || exit /b 1
rem Fora da economia de bateria: o congelador da Samsung (Freecess) congela o app em segundo plano mesmo com a acessibilidade ligada, e o servidor dele para de responder.
adb shell dumpsys deviceidle whitelist +%package%
adb shell cmd appops set %package% RUN_ANY_IN_BACKGROUND allow
adb shell am start -n %package%/dev.pedro.lmphone.MainActivity
