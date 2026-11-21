package dev.pedro.lmphone.cerebro

import dev.pedro.lmphone.modelos.Models

/**
 * A tradução de `lmphone/local_ai.py`, só com os modelos pequenos (no celular não há a Gemma): julga o pedido, acha
 * dados pessoais nos trechos de tela, tira os trechos da tela e aplica as decisões à sessão. As respostas têm o formato
 * do `modelo_server` (o Python as recebe por HTTP; aqui elas vêm do `Models` direto).
 */
class LocalAi(private val models: Models) {
    /** (resposta, texto da resposta, segundos), como `local_ai.judge_request`. */
    fun judgeRequest(text: String): Triple<Map<String, Any?>, String, Double> = timed {
        val (items, intent) = models.marker.mark(text)
        linkedMapOf("intencao" to intent, "entidades" to items.map {
            linkedMapOf("texto" to it.text, "tipo" to it.kind.trimEnd('+'), "precisa_pesquisa" to it.kind.endsWith("+"))
        })
    }

    /** Pessoas e usuários num texto de tela, como `local_ai.find_private` (e-mail, telefone e documento vão como usuário). */
    fun findPrivate(text: String): Triple<Map<String, Any?>, String, Double> = timed {
        linkedMapOf("itens" to models.marker.mark(text).first.filter { it.kind in PRIVATE }.map {
            linkedMapOf("texto" to it.text, "tipo" to if (it.kind == "pessoa") "pessoa" else "usuario")
        })
    }

    /** A escolha de controle, como `/pick` do `modelo_server`: {"label", "p", "ranking"}, mais "seconds". */
    fun pick(wanted: List<String>, labels: List<String>): Map<String, Any?> {
        val started = System.nanoTime()
        val pick = models.picker.pick(wanted, labels)
        return linkedMapOf("label" to pick.label, "p" to pick.p, "ranking" to pick.ranking.map { listOf(it.first, it.second) },
            "seconds" to Math.round((System.nanoTime() - started) / 1e6) / 1000.0)
    }

    private fun timed(block: () -> Map<String, Any?>): Triple<Map<String, Any?>, String, Double> {
        val started = System.nanoTime()
        val answer = block()
        return Triple(answer, Json.dumps(answer), Math.round((System.nanoTime() - started) / 1e6) / 1000.0)
    }

    companion object {
        private val PRIVATE = setOf("pessoa", "usuario", "email", "telefone", "documento")
        private val STATE = Consts.re("local_ai", "_STATE")
        private val ELEMENT = Consts.re("local_ai", "_ELEMENT")
        private val HEADERS = Consts.strings("local_ai", "_HEADERS")
        private val FOCUSED = Consts.re("local_ai", "_FOCUSED")
        private val HANDLE = Consts.re("local_ai", "HANDLE")
        private val SOCIAL = Consts.re("local_ai", "SOCIAL")
        private val URLISH = Consts.re("local_ai", "URLISH")
        private val WORD3 = Py.re("[^\\W\\d_]{3}")

        /**
         * Trechos de texto visíveis na tela, na ordem em que aparecem. Ficam de fora ids, nomes de classe, o cabeçalho
         * (app e teclado) e trechos sem nenhuma palavra.
         */
        fun screenFragments(text: String): List<String> {
            val fragments = LinkedHashSet<String>()
            for (state in Py.findallText(STATE, text)) {
                for (raw in Py.splitlines(state)) {
                    val line = Py.strip(raw)
                    val element = Py.fullmatch(ELEMENT, line)
                    val focused = Py.fullmatch(FOCUSED, line)
                    val parts = when {
                        element != null -> {
                            val cls = element.group(1)
                            element.group(2).split("\", \"").map { Py.strip(it, "\"") }
                                .filter { ":id/" !in it && !(!cls.isNullOrEmpty() && it.endsWith(".$cls")) }
                        }
                        focused != null -> listOf(focused.group(1))
                        HEADERS.any { line.startsWith(it) } -> emptyList()
                        else -> listOf(line)
                    }
                    for (part in parts) if (Py.search(WORD3, part) != null) fragments.add(Py.strip(part))
                }
            }
            return fragments.toList()
        }

        /** Junta os trechos em blocos de até `size` caracteres: uma chamada à IA por bloco. */
        fun batches(fragments: List<String>, size: Int = 1200): List<List<String>> {
            val out = ArrayList<List<String>>()
            var batch = ArrayList<String>()
            var length = 0
            for (fragment in fragments) {
                if (batch.isNotEmpty() && length + Py.len(fragment) > size) {
                    out.add(batch)
                    batch = ArrayList()
                    length = 0
                }
                batch.add(fragment)
                length += Py.len(fragment) + 3
            }
            if (batch.isNotEmpty()) out.add(batch)
            return out
        }

        private fun plain(text: String) = Py.casefold(Py.withoutMarks(text))

        /** As palavras de `span` do jeito que estão escritas em `source` (a IA nem sempre copia acentos e maiúsculas). */
        fun align(span: String, source: String): String {
            val written = HashMap<String, MutableSet<String>>()
            for (token in Masking.words(source)) written.getOrPut(plain(token)) { HashSet() }.add(token)
            val words = ArrayList<String>()
            for (token in Masking.words(span)) words.addAll((written[plain(token)] ?: setOf(token)).sortedWith(Py.ORDER))
            return words.joinToString(" ")
        }

        /** Aplica o julgamento do pedido à sessão. Devolve uma linha de decisão por entidade. */
        @Suppress("UNCHECKED_CAST")
        fun applyRequest(judgment: Map<String, Any?>, masker: Masker, source: String): List<Map<String, Any?>> {
            val decisions = ArrayList<Map<String, Any?>>()
            for (raw in judgment["entidades"] as? List<Any?> ?: emptyList()) {
                val entity = raw as Map<String, Any?>
                val text = align(entity["texto"] as String, source)
                val kind = entity["tipo"] as String
                val known = masker.knows(text)
                val wantsSearch = Py.truthy(entity["precisa_pesquisa"]) && judgment["intencao"] != "acao"
                val (decision, reason) = when {
                    (kind == "pessoa" || kind == "pessoa_publica") && Py.search(URLISH, entity["texto"] as String) != null ->
                        "manter" to "tem a forma de um endereço de site"
                    kind == "pessoa" || kind == "pessoa_publica" -> {
                        masker.session.protectName(text, masker.stop)
                        "mascarar" to "pessoa"
                    }
                    kind == "usuario" && Py.search(HANDLE, entity["texto"] as String) == null && Py.search(SOCIAL, source) == null ->
                        "manter" to "sem forma de nome de usuário e sem rede social no pedido"
                    kind in setOf("usuario", "email", "telefone", "documento") -> {
                        masker.session.protectLiteral(entity["texto"] as String)
                        "mascarar" to "identifica alguém"
                    }
                    kind in setOf("negocio", "instituicao", "lugar") -> when {
                        wantsSearch -> {
                            masker.session.release(text)
                            "liberar" to "precisa ser pesquisado na internet"
                        }
                        known -> "mascarar" to "é um contato e a tarefa não exige pesquisa"
                        else -> "manter" to "não está no cofre"
                    }
                    else -> "manter" to "não identifica ninguém"
                }
                decisions.add(linkedMapOf("texto" to text, "tipo" to kind, "decisao" to decision, "motivo" to reason))
            }
            return decisions
        }

        @Suppress("UNCHECKED_CAST")
        fun applyScreen(found: Map<String, Any?>, masker: Masker, source: String): List<Map<String, Any?>> {
            val decisions = ArrayList<Map<String, Any?>>()
            for (raw in found["itens"] as? List<Any?> ?: emptyList()) {
                val item = raw as Map<String, Any?>
                var text = item["texto"] as String
                val kind = item["tipo"] as String
                if (kind != "usuario" && Py.search(URLISH, text) != null) {
                    decisions.add(linkedMapOf("texto" to text, "tipo" to kind, "decisao" to "manter",
                        "motivo" to "tem a forma de um endereço de site"))
                    continue
                }
                if (kind == "usuario") {
                    masker.session.protectLiteral(text)
                } else {
                    text = align(text, source)
                    // O que o pedido liberou para pesquisa continua liberado.
                    masker.session.protectName(text, masker.stop, keepReleased = true)
                }
                decisions.add(linkedMapOf("texto" to text, "tipo" to kind, "decisao" to "mascarar",
                    "motivo" to if (kind == "usuario") "nome de usuário na tela" else "pessoa na tela"))
            }
            return decisions
        }
    }
}
