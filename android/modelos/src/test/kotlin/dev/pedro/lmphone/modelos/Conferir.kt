package dev.pedro.lmphone.modelos

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import kotlin.math.abs
import kotlin.system.exitProcess

/**
 * A conferência do Kotlin contra o Python (`android\gradlew.bat :modelos:conferir`, na raiz do projeto): lê as
 * respostas que `tools/app/modelos.py referencia` gravou e refaz cada uma aqui, com o onnxruntime da JVM.
 *
 * Os textos da coleta são reais: só os grupos fictícios (casos escritos à mão, aleatórios, pares longos) mostram o
 * texto de uma diferença; os outros, só a contagem.
 */
private const val REFERENCE = "data/modelos/app/referencia"
private val FICTITIOUS = setOf("casos", "aleatorios", "pares longos", "pares aleatorios", "caso")
private const val SHOW = 8  // diferenças mostradas por grupo fictício

private fun lines(name: String): Sequence<JSONObject> = File(REFERENCE, name).bufferedReader(Charsets.UTF_8).lineSequence()
    .filter { it.isNotBlank() }.map { JSONObject(it) }

private fun ints(array: JSONArray) = IntArray(array.length()) { array.getInt(it) }

private fun show(text: String) = text.map { c -> if (c.code < 0x20 || c.code in 0x7F..0xA0) "\\u%04x".format(c.code) else "$c" }.joinToString("")

private class Count {
    var total = 0
    var ids = 0
    var offsets = 0
    var shown = 0
}

fun main() {
    val files = mapOf(
        "tokenizador.bin" to File("data/modelos/app/tokenizador.bin"),
        "marcacao.onnx" to File("data/modelos/marcacao/modelo-tabela.onnx"),
        "marcacao.json" to File("data/modelos/marcacao/modelo.json"),
        "escolha.onnx" to File("data/modelos/escolha/modelo-tabela.onnx"),
        "escolha.json" to File("data/modelos/escolha/modelo.json"),
    )
    val started = System.nanoTime()
    val tokenizer = Tokenizer.load(files.getValue("tokenizador.bin"))
    println("tokenizador carregado em %.2f s".format((System.nanoTime() - started) / 1e9))
    var failed = tokens(tokenizer)
    Models({ files.getValue(it) }).use { models ->
        failed = marking(models) or failed
        failed = choosing(models) or failed
    }
    if (failed) exitProcess(1)
}

private fun tokens(tokenizer: Tokenizer): Boolean {
    val counts = linkedMapOf<String, Count>()
    var seconds = 0.0
    for (case in lines("tokens.jsonl")) {
        val group = case.getString("grupo")
        val pair = case.has("a")
        val key = "$group (${if (pair) "par, " else ""}${case.getInt("max").takeIf { it > 0 } ?: "sem corte"})"
        val count = counts.getOrPut(key) { Count() }
        val started = System.nanoTime()
        val encoding = if (pair) tokenizer.encodePair(case.getString("a"), case.getString("b"), case.getInt("max"))
        else tokenizer.encode(case.getString("t"), case.getInt("max"))
        seconds += (System.nanoTime() - started) / 1e9
        val ids = ints(case.getJSONArray("ids"))
        val offsets = case.getJSONArray("o")
        val sameIds = ids.contentEquals(encoding.ids)
        val sameOffsets = sameIds && (0 until offsets.length()).all {
            offsets.getJSONArray(it).getInt(0) == encoding.starts[it] && offsets.getJSONArray(it).getInt(1) == encoding.ends[it]
        }
        count.total++
        if (sameIds) count.ids++
        if (sameOffsets) count.offsets++
        if (!sameOffsets && group in FICTITIOUS && count.shown < SHOW) {
            count.shown++
            val text = if (pair) "«${show(case.getString("a"))}» + «${show(case.getString("b"))}»" else "«${show(case.getString("t"))}»"
            println("  diferente em $key: $text")
            println("    python: ${ids.toList()} ${offsets}")
            println("    kotlin: ${encoding.ids.toList()} ${encoding.starts.indices.map { listOf(encoding.starts[it], encoding.ends[it]) }}")
        }
    }
    var failed = false
    println("tokenizador (iguais em ids / em ids e posições / total):")
    for ((key, count) in counts) {
        println("  $key: ${count.ids} / ${count.offsets} / ${count.total}")
        if (count.offsets != count.total) failed = true
    }
    println("  tempo: %.1f s em %d textos".format(seconds, counts.values.sumOf { it.total }))
    return failed
}

private fun marking(models: Models): Boolean {
    val totals = linkedMapOf<String, IntArray>()  // iguais, total
    var seconds = 0.0
    var shown = 0
    for (case in lines("marcacao.jsonl")) {
        val kind = case.getString("tipo")
        val started = System.nanoTime()
        val (items, intent) = models.marker.mark(case.getString("t"))
        seconds += (System.nanoTime() - started) / 1e9
        val expected = case.getJSONArray("itens").let { list ->
            List(list.length()) { list.getJSONObject(it).getString("texto") to list.getJSONObject(it).getString("tipo") }
        }
        val same = expected == items.map { it.text to it.kind } && case.opt("intencao").let { if (it == JSONObject.NULL) null else it } == intent
        val total = totals.getOrPut(kind) { IntArray(2) }
        if (same) total[0]++
        total[1]++
        if (!same && kind in FICTITIOUS && shown++ < SHOW) {
            println("  marcação diferente: «${show(case.getString("t"))}»")
            println("    python: $expected ${case.opt("intencao")}")
            println("    kotlin: ${items.map { it.text to it.kind }} $intent")
        }
    }
    println("marcação (iguais / total):")
    for ((kind, total) in totals) println("  $kind: ${total[0]} / ${total[1]}")
    println("  tempo: %.1f ms por texto".format(seconds * 1000 / totals.values.sumOf { it[1] }))
    return totals.values.any { it[0] != it[1] }
}

private fun choosing(models: Models): Boolean {
    var total = 0
    var sameLabel = 0
    var sameRanking = 0
    var worst = 0.0
    var seconds = 0.0
    for (case in lines("escolha.jsonl")) {
        val wanted = case.getJSONArray("wanted").let { list -> List(list.length()) { list.getString(it) } }
        val labels = case.getJSONArray("labels").let { list -> List(list.length()) { list.getString(it) } }
        val started = System.nanoTime()
        val probabilities = models.picker.probabilities(wanted, labels)
        val pick = models.picker.pick(wanted, labels)
        seconds += (System.nanoTime() - started) / 1e9
        val expected = case.getJSONArray("p")
        for (k in probabilities.indices) worst = maxOf(worst, abs(probabilities[k] - expected.getDouble(k)))
        total++
        if ((case.opt("label").takeIf { it != JSONObject.NULL }) == pick.label) sameLabel++
        val ranking = case.getJSONArray("ranking")
        val same = ranking.length() == pick.ranking.size && (0 until ranking.length()).all {
            val row = ranking.getJSONArray(it)
            row.opt(0).takeIf { label -> label != JSONObject.NULL } == pick.ranking[it].first && row.getDouble(1) == pick.ranking[it].second
        }
        if (same) sameRanking++
    }
    println("escolha: mesmo rótulo em $sameLabel de $total, mesmo ranking em $sameRanking; maior diferença de probabilidade %.2e; %.1f ms por escolha"
        .format(worst, seconds * 1000 / total))
    return sameLabel != total
}
