# O build de publicação (minificado pelo R8; docs/plano-play-store.md, fase 3).
# O onnxruntime chama as classes Java dele pelo JNI, pelos nomes: nada dele pode ser renomeado nem removido.
-keep class ai.onnxruntime.** { *; }
-keepclasseswithmembernames class * { native <methods>; }
# O cérebro lê o cerebro.json (recurso) e monta tudo por mapas, sem reflexão; os serviços do Android são achados pelo
# manifesto (o R8 já os mantém).
-dontwarn ai.onnxruntime.**
