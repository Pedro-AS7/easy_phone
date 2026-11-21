// O cérebro do lm_phone em Kotlin (etapa 3 de docs/plano-app-android.md): a tradução de lmphone/ (máscara, IA local,
// fatos, cache, executor, o caminho ao provedor), em Kotlin puro. O app o usa no celular; a conferência (`conferir`)
// o compara com o Python no PC. Os prompts, as listas e as expressões regulares vêm do Python pelo cerebro.json
// (tools/app/cerebro.py exportar).
plugins {
    id("org.jetbrains.kotlin.jvm")
}

kotlin {
    jvmToolchain(17)
}

val onnxruntime = "1.31.0"
val json = "org.json:json:20240303"

dependencies {
    implementation(project(":modelos"))
    compileOnly("com.microsoft.onnxruntime:onnxruntime:$onnxruntime")
    testImplementation("com.microsoft.onnxruntime:onnxruntime:$onnxruntime")
    testImplementation(json)
}

// Compara com o Python: a máscara, a IA local e as trilhas do executor (tools/app/cerebro.py referencia).
tasks.register<JavaExec>("conferir") {
    group = "verification"
    classpath = sourceSets["test"].runtimeClasspath
    mainClass.set("dev.pedro.lmphone.cerebro.ConferirKt")
    workingDir = rootProject.projectDir.parentFile
    maxHeapSize = "2g"
    args = (project.findProperty("partes") as String?)?.split(",") ?: emptyList()
}
