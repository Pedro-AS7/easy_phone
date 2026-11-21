// Os modelos pequenos no app (etapa 2 de docs/plano-app-android.md): tokenizador, a montagem do texto de
// lmphone/modelo.py e as chamadas ao onnxruntime, em Kotlin puro. O app usa o onnxruntime do Android, e a conferência
// no PC (`conferir`), o da JVM: a API é a mesma, então aqui ele entra só para compilar.
plugins {
    id("org.jetbrains.kotlin.jvm")
}

kotlin {
    jvmToolchain(17)
}

val onnxruntime = "1.31.0"  // a mesma versão do .venv-modelo
val json = "org.json:json:20240303"  // no Android, o org.json já vem no sistema

dependencies {
    compileOnly("com.microsoft.onnxruntime:onnxruntime:$onnxruntime")
    compileOnly(json)
    testImplementation("com.microsoft.onnxruntime:onnxruntime:$onnxruntime")
    testImplementation(json)
}

// Compara com as respostas do Python (tools/app/modelos.py referencia): o tokenizador token a token, a marcação e a
// escolha resposta a resposta. Mostra só contagens; os textos da coleta são reais.
tasks.register<JavaExec>("conferir") {
    group = "verification"
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("dev.pedro.lmphone.modelos.ConferirKt")
    workingDir = rootProject.projectDir.parentFile
    maxHeapSize = "2g"
}

// A palavra de ativação contra a biblioteca do openWakeWord (tools/app/escuta.py referencia), frase a frase.
tasks.register<JavaExec>("conferirEscuta") {
    group = "verification"
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("dev.pedro.lmphone.modelos.ConferirEscutaKt")
    workingDir = rootProject.projectDir.parentFile
}
