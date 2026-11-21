package dev.pedro.lmphone.cerebro

import java.io.File
import kotlin.system.exitProcess

/**
 * A conferência do cérebro em Kotlin contra o Python (`android\gradlew.bat :cerebro:conferir`, na raiz do projeto;
 * `-Ppartes=trilhas` para só uma parte). As trilhas dos testes (`tools/app/cerebro.py trilhas`) são fictícias e mostram
 * o detalhe das diferenças; as de tarefas de verdade (logs/trilhas/, LMPHONE_TRILHA=1), só o tipo.
 */
fun main(args: Array<String>) {
    val parts = args.toSet().ifEmpty { setOf("trilhas", "mascara", "agente") }
    var ok = true
    if ("agente" in parts) Mascara.models().use { ok = AgentCheck.check(it) and ok }
    if ("mascara" in parts) {
        val file = File("data/trilhas/mascara.jsonl")
        if (file.exists()) Mascara.models().use { ok = Mascara.check(file, it) and ok }
        else println("sem ${file.path}: rode .venv-modelo/Scripts/python.exe -m tools.app.cerebro mascara")
    }
    if ("trilhas" in parts) {
        val reference = File("data/trilhas/mapa.json")
        if (reference.exists()) ok = mapCheck(reference) and ok
        val tests = File("data/trilhas/testes.jsonl")
        if (tests.exists()) ok = Trilhas.check(tests, real = false) and ok
        else println("sem ${tests.path}: rode .venv/Scripts/python.exe -m tools.app.cerebro trilhas")
        File("logs/trilhas").listFiles { f -> f.name.endsWith(".jsonl") }?.sortedBy { it.name }?.forEach {
            ok = Trilhas.check(it, real = true, show = 3) and ok
        }
    }
    if (!ok) exitProcess(1)
}


/** O mapa dos nomes do aparelho (`Cache.learn`, `X.related`, `X.render`) contra o do Python (`tools.app.cerebro trilhas`). */
@Suppress("UNCHECKED_CAST")
fun mapCheck(reference: File): Boolean {
    val ref = Json.parse(reference.readText()) as Map<String, Any?>
    val folder = kotlin.io.path.createTempDirectory("mapa").toFile()
    try {
        val cache = Cache(folder)
        val out = (ref["fora"] as List<*>).map { it as String }.toSet()
        cache.learn((ref["trail"] as List<*>).map { it as Map<String, Any?> }) { it !in out }
        val tree = cache.maps()
        val text = X.render(X.related(tree, ref["task"] as String))
        val good = Json.dumps(tree) == Json.dumps(ref["tree"]) && text == ref["text"]
        println("mapa dos nomes: ${if (good) "ok" else "DIFERENTE: ${Json.dumps(tree)} / $text"}")
        return good
    } finally {
        folder.deleteRecursively()
    }
}
