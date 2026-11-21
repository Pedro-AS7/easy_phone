#!/bin/sh
# Compila o app, instala no celular pelo adb e abre (etapa 0 de docs/plano-app-android.md).
# Sem argumento, a variante `completo` (a de sempre); `android/build.sh loja`, a da Play Store (docs/plano-play-store.md).
set -e
cd "$(dirname "$0")"
variant="${1:-completo}"
case "$variant" in
    completo) package=dev.pedro.lmphone; task=assembleCompletoDebug ;;
    loja) package=dev.pedro.lmphone.guia; task=assembleLojaDebug ;;
    *) echo "variante desconhecida: $variant (completo ou loja)"; exit 1 ;;
esac
./gradlew "$task" --console=plain -q
adb install -r "app/build/outputs/apk/$variant/debug/app-$variant-debug.apk"
# Fora da economia de bateria: o congelador da Samsung (Freecess) congela o app em segundo plano mesmo com a
# acessibilidade ligada, e o servidor dele para de responder.
adb shell dumpsys deviceidle whitelist +$package
adb shell cmd appops set $package RUN_ANY_IN_BACKGROUND allow
adb shell am start -n $package/dev.pedro.lmphone.MainActivity
