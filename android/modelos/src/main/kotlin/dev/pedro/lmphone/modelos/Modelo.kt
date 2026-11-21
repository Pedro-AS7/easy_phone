package dev.pedro.lmphone.modelos

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * A tradução de `lmphone/modelo.py`, o que o treino e o servidor dos modelos pequenos têm em comum: os rótulos da
 * marcação, os blocos de trechos de tela, as entidades a partir dos rótulos de cada token e a pergunta da escolha.
 * Comprimentos em code points, como no Python (um emoji conta 1, não 2), para os blocos se cortarem nos mesmos lugares.
 */
object Modelo {
    val KINDS = listOf("pessoa", "usuario", "email", "telefone", "documento", "negocio", "instituicao", "lugar", "app",
        "negocio+", "instituicao+", "lugar+")
    val LABELS = listOf("O") + KINDS.flatMap { listOf("B-$it", "I-$it") }
    val INTENTS = listOf("acao", "pesquisa", "mista")
    const val BLOCK = 600
    const val SEPARATOR = " • "
    const val NONE_LABEL = "(none of these)"
    val PRIVATE = setOf("pessoa", "usuario", "email", "telefone", "documento")
    private val HANDLE = Regex("[._\\p{Nd}]")  // o \d do Python é qualquer dígito Unicode

    data class Span(val start: Int, val end: Int, val kind: String)

    fun length(text: String) = text.codePointCount(0, text.length)

    /** Junta trechos seguidos em blocos de até `size` caracteres (`blocks`, sem as entidades do treino). */
    fun blocks(fragments: List<String>, size: Int = BLOCK): List<String> {
        val out = ArrayList<String>()
        var text = ""
        for (fragment in fragments) {
            if (text.isNotEmpty() && length(text) + length(SEPARATOR) + length(fragment) > size) {
                out.add(text)
                text = ""
            }
            text = if (text.isNotEmpty()) text + SEPARATOR + fragment else fragment
        }
        if (text.isNotEmpty()) out.add(text)
        return out
    }

    /** Entidades (início, fim, tipo) a partir dos rótulos de cada token; posições em UTF-16 de `text`. */
    fun decode(starts: IntArray, ends: IntArray, predicted: IntArray, text: String): List<Span> {
        val spans = ArrayList<IntArray>()  // início, fim, tipo (índice em KINDS)
        val kinds = ArrayList<String>()
        var current = -1
        for (k in predicted.indices) {
            val name = if (starts[k] != ends[k]) LABELS[predicted[k]] else "O"
            if (name == "O") {
                current = -1
                continue
            }
            val prefix = name.substringBefore('-')
            val kind = name.substringAfter('-')
            if (current >= 0 && kinds[current] == kind && prefix == "I") {
                spans[current][1] = ends[k]
            } else {
                spans.add(intArrayOf(starts[k], ends[k]))
                kinds.add(kind)
                current = spans.size - 1
            }
        }
        val found = spans.indices.filter { strip(text.substring(spans[it][0], spans[it][1])).isNotEmpty() }
            .map { Span(spans[it][0], spans[it][1], kinds[it]) }
        return wholeWords(found, text)
    }

    /**
     * Estende cada entidade até as bordas da palavra e junta as que caem na mesma palavra (`whole_words`): na junção,
     * um tipo privado ganha de um público, e pedaços de tipos diferentes numa palavra com ponto, sublinhado ou dígito
     * viram usuário (ou e-mail, com @).
     */
    fun wholeWords(spans: List<Span>, text: String): List<Span> {
        val out = ArrayList<Span>()
        for (span in spans) {
            var s = span.start
            var e = span.end
            while (s > 0 && !isSpace(text[s - 1]) && text[s - 1] !in "•,;:()\"'“”") s--
            while (e < text.length && !isSpace(text[e]) && text[e] !in "•,;:()\"'“”?!") e++
            while (e > s && text[e - 1] in ".…") e--
            val last = out.lastOrNull()
            if (last != null && s < last.end) {
                val word = text.substring(minOf(last.start, s), maxOf(last.end, e))
                val kind = if (last.kind != span.kind && HANDLE.containsMatchIn(word) && ' ' !in word) {
                    if ('@' in word) "email" else "usuario"
                } else {
                    listOf(last.kind, span.kind).firstOrNull { it.trimEnd('+') in PRIVATE } ?: last.kind
                }
                out[out.size - 1] = Span(minOf(last.start, s), maxOf(last.end, e), kind)
            } else {
                out.add(Span(s, e, span.kind))
            }
        }
        return out
    }

    fun query(wanted: List<String>) = wanted.joinToString(" / ")

    /** `str.isspace()` do Python para um caractere: o `isWhitespace` do Kotlin mais o U+0085. */
    fun isSpace(c: Char) = c.isWhitespace() || c == '\u0085'

    /** `str.strip()` do Python. */
    fun strip(text: String): String {
        var s = 0
        var e = text.length
        while (s < e && isSpace(text[s])) s++
        while (e > s && isSpace(text[e - 1])) e--
        return text.substring(s, e)
    }

    /** `round(p, 3)` do Python: o valor exato do double, arredondado com empate para o par. */
    fun round3(p: Double) = BigDecimal(p).setScale(3, RoundingMode.HALF_EVEN).toDouble()
}
