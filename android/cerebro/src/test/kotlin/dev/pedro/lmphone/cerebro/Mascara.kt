package dev.pedro.lmphone.cerebro

import dev.pedro.lmphone.modelos.Models
import java.io.File

/**
 * A conferência da máscara e da IA local de ponta a ponta (`tools/app/cerebro.py mascara`): os mesmos pedidos e telas,
 * julgados pelos modelos, com as decisões aplicadas, mascarados e desmascarados, com os mesmos valores falsos
 * (determinísticos dos dois lados). Os casos da coleta são reais: deles o terminal mostra só a contagem.
 */
object Mascara {
    /** Os valores falsos de `tools/app/cerebro.stub_fake`. */
    class StubSession(vault: Vault) : Session(vault) {
        override fun newFake(kind: String, real: String): String {
            val n = reverse.getValue(kind).size + 1
            val letters = (0 until 3).map { k -> (97 + (n / Math.pow(26.0, k.toDouble()).toInt()) % 26).toChar() }.joinToString("")
            return when (kind) {
                "name" -> "fake$letters"
                "email" -> "contato${1000 + n}@exemplo.com"
                "literal" -> "usuario${1000 + n}"
                "handle" -> "@usuario${1000 + n}"
                else -> (0 until Py.len(real)).joinToString("") { k -> ((n * 7 + k * 3) % 10).toString() }
            }
        }
    }

    private const val SEPARATOR = " • "

    @Suppress("UNCHECKED_CAST")
    fun check(file: File, models: Models): Boolean {
        val ai = LocalAi(models)
        val lines = file.readLines(Charsets.UTF_8).filter { it.isNotBlank() }
        val header = Json.parse(lines[0]) as Map<String, Any?>
        val vault = Vault()
        for ((kind, values) in header["cofre"] as Map<String, Any?>) (values as List<*>).forEach { vault.add(kind, it as String) }
        val stoplist = (header["stoplist"] as List<*>).map { it as String }

        fun sessionState(masker: Masker): Map<String, Any?> {
            val session = masker.session
            return linkedMapOf("extra_names" to session.extraNames.sortedWith(Py.ORDER), "cap_names" to session.capNames.sortedWith(Py.ORDER),
                "extra_literals" to session.extraLiterals.sortedWith(Py.ORDER), "released" to session.released.sortedWith(Py.ORDER),
                "forward" to session.forward.filterValues { it.isNotEmpty() })
        }

        val totals = linkedMapOf<String, IntArray>()
        var shown = 0
        for (line in lines.drop(1)) {
            val case = Json.parse(line) as Map<String, Any?>
            val kind = case["tipo"] as String
            val real = case["real"] == true
            val mine: Map<String, Any?> = when (kind) {
                "pedido" -> {
                    val text = case["entrada"] as String
                    val masker = Masker(vault, stoplist, StubSession(vault))
                    for (password in Masking.passwords(text)) masker.session.protectLiteral(password)
                    val decisions = LocalAi.applyRequest(ai.judgeRequest(text).first, masker, text)
                    val counts = LinkedHashMap<String, Int>()
                    val trace = ArrayList<Triple<String, String, String>>()
                    val masked = masker.mask(text, counts, trace)
                    linkedMapOf("decisoes" to decisions, "mascarado" to masked, "volta" to masker.unmask(masked),
                        "trocas" to trace.map { it.toList() }, "contagem" to counts, "sessao" to sessionState(masker))
                }
                "tela" -> {
                    val fragments = (case["entrada"] as List<*>).map { it as String }
                    val masker = Masker(vault, stoplist, StubSession(vault))
                    val applied = LocalAi.batches(fragments).map { batch ->
                        val source = batch.joinToString(SEPARATOR)
                        LocalAi.applyScreen(ai.findPrivate(source).first, masker, source)
                    }
                    val masked = fragments.map { masker.mask(it) }
                    linkedMapOf("decisoes" to applied, "mascarado" to masked, "volta" to masked.map { masker.unmask(it) },
                        "sessao" to sessionState(masker))
                }
                else -> linkedMapOf("trechos" to LocalAi.screenFragments(case["entrada"] as String))
            }
            val differs = mine.keys.filter { !Trilhas.same(Trilhas.encode(mine[it]), case[it]) }
            val group = "$kind${if (real) " (real)" else ""}"
            val total = totals.getOrPut(group) { IntArray(2) }
            total[1]++
            if (differs.isEmpty()) {
                total[0]++
            } else if (shown++ < 8) {
                println("  diferente: $group em ${differs.joinToString(", ")}")
                if (!real) differs.take(2).forEach {
                    println("    $it\n      kotlin: ${Py.head(Json.dumps(Trilhas.encode(mine[it])), 500)}\n      python: ${Py.head(Json.dumps(case[it]), 500)}")
                }
            }
        }
        println("máscara e IA local (iguais / total): " + totals.entries.joinToString("; ") { "${it.key}: ${it.value[0]} / ${it.value[1]}" })
        return totals.values.all { it[0] == it[1] }
    }

    fun models() = Models({ name ->
        when (name) {
            "tokenizador.bin" -> File("data/modelos/app/tokenizador.bin")
            "marcacao.onnx" -> File("data/modelos/marcacao/modelo-tabela.onnx")
            "marcacao.json" -> File("data/modelos/marcacao/modelo.json")
            "escolha.onnx" -> File("data/modelos/escolha/modelo-tabela.onnx")
            else -> File("data/modelos/escolha/modelo.json")
        }
    })
}
