package dev.pedro.lmphone.modelos

import java.io.BufferedInputStream
import java.io.DataInputStream
import java.io.File

/**
 * O tokenizador dos modelos pequenos, o do multilingual-e5-small (o do XLM-R: Unigram com 250 mil peças), escrito à
 * mão para dar no celular os mesmos tokens e as mesmas posições que a biblioteca `tokenizers` do Python (0.23.3), a
 * referência. Lê o `tokenizador.bin` que `tools/app/modelos.py preparar` grava a partir do `tokenizer.json`; a
 * conferência (`:modelos:conferir`) o compara com o Python nos textos da coleta e em casos difíceis.
 *
 * Os passos, como na biblioteca:
 * 1. Os tokens especiais escritos no texto ("<s>", "<mask>"...) saem antes de tudo, como estão.
 * 2. Normalização (`Precompiled`, a nmt_nfkc do SentencePiece), por grafema, e cada caractere novo guarda de onde veio
 *    no texto. Duas esquisitices da biblioteca ficam iguais aqui de propósito: num grafema curto (menos de 6 bytes) vale
 *    a regra do começo mais curto que tiver uma, e o resto do grafema some ("Ａ" mais um acento vira "A"); e um
 *    caractere apagado (os controles) no começo do texto desloca as posições dos caracteres seguintes.
 * 3. Separação nos espaços, "▁" na frente de cada palavra e nova separação antes de cada "▁" que segue outro caractere.
 * 4. Unigram: o caminho de maior nota pelas peças (Viterbi); caractere sem peça é <unk>, e <unk> seguidos se juntam.
 * 5. Corte (no par, o mais longo primeiro) e os tokens <s> e </s> em volta.
 *
 * As posições são em unidades UTF-16 do texto, as do Kotlin (as do Python são em code points).
 */
class Tokenizer private constructor(
    private val unkId: Int,
    val bosId: Int,
    val eosId: Int,
    val padId: Int,
    private val specials: List<Pair<String, Int>>,
    private val charsmap: Charsmap,
    private val pieces: HashMap<String, Int>,
    private val scores: DoubleArray,
) {
    /** Os tokens de um texto ou de um par: o id e o trecho do texto (no par, do texto de onde o token veio). */
    class Encoding(val ids: IntArray, val starts: IntArray, val ends: IntArray)

    private val maxPiece = pieces.keys.maxOf { it.codePointCount(0, it.length) }
    private val unkScore = scores.min() - UNK_PENALTY

    /** Um texto, cortado em `maxTokens` contando <s> e </s> (0: sem corte). */
    fun encode(text: String, maxTokens: Int = 0): Encoding {
        val tokens = tokens(text)
        if (maxTokens > 0) tokens.truncate(maxTokens - 2)
        val out = Tokens()
        out.add(bosId, 0, 0)
        out.addAll(tokens)
        out.add(eosId, 0, 0)
        return out.encoding()
    }

    /** Um par, `<s> A </s></s> B </s>`, como a escolha monta pedido e rótulo. */
    fun encodePair(a: String, b: String, maxTokens: Int = 0): Encoding {
        val first = tokens(a)
        val second = tokens(b)
        if (maxTokens > 0) longestFirst(first, second, maxTokens - 4)
        val out = Tokens()
        out.add(bosId, 0, 0)
        out.addAll(first)
        out.add(eosId, 0, 0)
        out.add(eosId, 0, 0)
        out.addAll(second)
        out.add(eosId, 0, 0)
        return out.encoding()
    }

    /** O corte `LongestFirst` da biblioteca: só o mais longo, se bastar; senão os dois perto da metade. */
    private fun longestFirst(first: Tokens, second: Tokens, max: Int) {
        if (first.size + second.size <= max) return
        var n1 = first.size
        var n2 = second.size
        val swap = n1 > n2
        if (swap) n1 = n2.also { n2 = n1 }
        n2 = if (n1 > max) n1 else maxOf(n1, max - n1)
        if (n1 + n2 > max) {
            n1 = max / 2
            n2 = n1 + max % 2
        }
        if (swap) n1 = n2.also { n2 = n1 }
        first.truncate(n1)
        second.truncate(n2)
    }

    private fun tokens(text: String): Tokens {
        val out = Tokens()
        var start = 0
        var i = 0
        while (i < text.length) {
            // O especial mais longo que começa aqui (o mais à esquerda ganha).
            val special = if (text[i] == '<') specials.filter { text.startsWith(it.first, i) }.maxByOrNull { it.first.length } else null
            if (special == null) {
                i++
                continue
            }
            if (start < i) piece(text, start, i, out)
            out.add(special.second, i, i + special.first.length)
            i += special.first.length
            start = i
        }
        if (start < text.length) piece(text, start, text.length, out)
        return out
    }

    /** Um trecho sem tokens especiais: normaliza, separa as palavras e passa cada uma pelo Unigram. */
    private fun piece(text: String, from: Int, to: Int, out: Tokens) {
        val normalized = normalize(text, from, to)
        var k = 0
        while (k < normalized.size) {
            if (isWhitespace(normalized.cps[k])) {
                k++
                continue
            }
            var end = k
            while (end < normalized.size && !isWhitespace(normalized.cps[end])) end++
            word(normalized, k, end, out)
            k = end
        }
    }

    private fun word(chars: Chars, from: Int, to: Int, out: Tokens) {
        // Metaspace: "▁" na frente, com a posição do primeiro caractere, a menos que a palavra já comece por um.
        val word = Chars()
        if (chars.cps[from] != METASPACE) word.add(METASPACE, chars.starts[from], chars.ends[from])
        for (k in from until to) word.add(chars.cps[k], chars.starts[k], chars.ends[k])
        var start = 0
        for (k in 1..word.size) {
            if (k == word.size || (word.cps[k] == METASPACE && word.cps[k - 1] != METASPACE)) {
                unigram(word, start, k, out)
                start = k
            }
        }
    }

    /** O Viterbi do Unigram (`encode_optimized`), em code points. */
    private fun unigram(chars: Chars, from: Int, to: Int, out: Tokens) {
        val size = to - from
        val text = String(chars.cps, from, size)
        val at = IntArray(size + 1)  // posição UTF-16 de cada code point em `text`
        for (k in 0 until size) at[k + 1] = at[k] + Character.charCount(chars.cps[from + k])
        val score = DoubleArray(size + 1)
        val startsAt = IntArray(size + 1) { -1 }
        val id = IntArray(size + 1)
        for (start in 0 until size) {
            val base = score[start]
            var single = false
            for (length in 1..minOf(maxPiece, size - start)) {
                val piece = pieces[text.substring(at[start], at[start + length])] ?: continue
                val end = start + length
                val candidate = scores[piece] + base
                if (startsAt[end] < 0 || candidate > score[end]) {
                    score[end] = candidate
                    startsAt[end] = start
                    id[end] = piece
                }
                if (length == 1) single = true
            }
            if (!single) {
                val candidate = unkScore + base
                if (startsAt[start + 1] < 0 || candidate > score[start + 1]) {
                    score[start + 1] = candidate
                    startsAt[start + 1] = start
                    id[start + 1] = unkId
                }
            }
        }
        // De trás para a frente; <unk> seguidos viram um token só.
        val found = ArrayList<IntArray>()  // início e fim em code points
        var end = size
        var unkEnd = -1
        var unkStart = -1
        while (end > 0) {
            val start = startsAt[end]
            if (id[end] == unkId) {
                if (unkEnd < 0) unkEnd = end
                unkStart = start
            } else {
                if (unkEnd >= 0) found.add(intArrayOf(unkStart, unkEnd))
                unkEnd = -1
                found.add(intArrayOf(start, end))
            }
            end = start
        }
        if (unkEnd >= 0) found.add(intArrayOf(unkStart, unkEnd))
        for (k in found.indices.reversed()) {
            val (start, stop) = found[k]
            // Como a biblioteca, o id vem do texto do token: <unk> juntos que formem uma peça viram a peça.
            val piece = pieces[text.substring(at[start], at[stop])] ?: unkId
            out.add(piece, chars.starts[from + start], chars.ends[from + stop - 1])
        }
    }

    /**
     * A normalização `Precompiled` e as posições (`NormalizedString::transform`): cada caractere novo fica com a posição
     * do original que ele troca, e um acrescentado, com a do anterior. Um apagado soma -1 à mudança do caractere
     * anterior; sem anterior (no começo do trecho), a biblioteca não o desconta, e as posições seguintes andam uma.
     */
    private fun normalize(text: String, from: Int, to: Int): Chars {
        val original = Chars()
        var i = from
        while (i < to) {
            val cp = text.codePointAt(i)
            val n = Character.charCount(cp)
            original.add(cp, i, i + n)
            i += n
        }
        val chars = IntList()
        val changes = IntList()
        var modified = false
        var g = 0
        while (g < original.size) {
            val end = graphemeEnd(original.cps, g, original.size)
            val whole = if (utf8Length(original.cps, g, end) < 6) charsmap.transform(original.cps, g, end) else null
            if (whole != null) {
                modified = true
                replace(chars, changes, end - g, whole)
            } else {
                for (k in g until end) {
                    val one = charsmap.transform(original.cps, k, k + 1)
                    if (one != null) {
                        modified = true
                        replace(chars, changes, 1, one)
                    } else {
                        chars.add(original.cps[k])
                        changes.add(0)
                    }
                }
            }
            g = end
        }
        if (!modified) return original
        val out = Chars()
        var consumed = 0
        for (k in 0 until chars.size) {
            val change = changes[k]
            val source = if (change > 0) consumed - 1 else consumed
            if (source < 0) out.add(chars[k], from, from)
            else out.add(chars[k], original.starts[minOf(source, original.size - 1)], original.ends[minOf(source, original.size - 1)])
            if (change <= 0) consumed += 1 - change
        }
        return out
    }

    private fun replace(chars: IntList, changes: IntList, old: Int, new: IntArray) {
        for (c in new) {
            chars.add(c)
            changes.add(0)
        }
        val diff = new.size - old
        if (diff > 0) for (k in chars.size - diff until chars.size) changes[k] = 1
        else if (diff < 0 && changes.size > 0) changes[changes.size - 1] = changes[changes.size - 1] + diff
    }

    companion object {
        private const val UNK_PENALTY = 10.0
        private const val METASPACE = 0x2581  // ▁
        private val MAGIC = "LMTK".toByteArray()

        fun load(file: File): Tokenizer = DataInputStream(BufferedInputStream(file.inputStream(), 1 shl 16)).use { input ->
            val magic = ByteArray(4).also { input.readFully(it) }
            require(magic.contentEquals(MAGIC) && input.readInt() == 1) { "${file.name} não é um tokenizador do lm_phone" }
            val unk = input.readInt()
            val bos = input.readInt()
            val eos = input.readInt()
            val pad = input.readInt()
            val specials = List(input.readInt()) {
                val id = input.readInt()
                val content = ByteArray(input.readShort().toInt()).also { bytes -> input.readFully(bytes) }
                String(content, Charsets.UTF_8) to id
            }
            val charsmap = Charsmap(ByteArray(input.readInt()).also { input.readFully(it) })
            val count = input.readInt()
            val pieces = HashMap<String, Int>(count * 2)
            val scores = DoubleArray(count)
            val buffer = ByteArray(1 shl 12)
            for (id in 0 until count) {
                val length = input.readShort().toInt()
                input.readFully(buffer, 0, length)
                pieces[String(buffer, 0, length, Charsets.UTF_8)] = id  // repetida: vale a última, como na biblioteca
                scores[id] = input.readDouble()
            }
            Tokenizer(unk, bos, eos, pad, specials, charsmap, pieces, scores)
        }

        /** `char::is_whitespace` do Rust (a propriedade White_Space do Unicode). */
        fun isWhitespace(cp: Int) = cp in 0x9..0xD || cp == 0x20 || cp == 0x85 || cp == 0xA0 || cp == 0x1680 ||
            cp in 0x2000..0x200A || cp == 0x2028 || cp == 0x2029 || cp == 0x202F || cp == 0x205F || cp == 0x3000

        fun utf8Length(cp: Int) = when {
            cp < 0x80 -> 1
            cp < 0x800 -> 2
            cp < 0x10000 -> 3
            else -> 4
        }

        private fun utf8Length(cps: IntArray, from: Int, to: Int): Int {
            var total = 0
            for (k in from until to) total += utf8Length(cps[k])
            return total
        }

        /**
         * O fim do grafema que começa em `start` (os grafemas estendidos do Unicode, só no que muda o resultado: CR LF
         * juntos, controle sozinho, e a base com as marcas e junções que vêm depois). Um grafema que esta regra parte
         * diferente da biblioteca só muda algo se o pedaço tiver menos de 6 bytes e uma regra própria na normalização.
         */
        fun graphemeEnd(cps: IntArray, start: Int, size: Int): Int {
            val c = cps[start]
            if (c == '\r'.code) return if (start + 1 < size && cps[start + 1] == '\n'.code) start + 2 else start + 1
            if (isControl(c)) return start + 1
            var end = start + 1
            while (end < size && isExtend(cps[end])) end++
            return end
        }

        private fun isControl(cp: Int): Boolean {
            if (cp == 0x200C || cp == 0x200D || cp in 0xE0020..0xE007F) return false
            return when (Character.getType(cp)) {
                Character.CONTROL.toInt(), Character.LINE_SEPARATOR.toInt(), Character.PARAGRAPH_SEPARATOR.toInt(),
                Character.FORMAT.toInt() -> true
                else -> false
            }
        }

        private fun isExtend(cp: Int): Boolean {
            if (cp == 0x200C || cp == 0x200D || cp in 0x1F3FB..0x1F3FF || cp in 0xE0020..0xE007F || cp == 0xFF9E || cp == 0xFF9F) return true
            return when (Character.getType(cp)) {
                Character.NON_SPACING_MARK.toInt(), Character.ENCLOSING_MARK.toInt(), Character.COMBINING_SPACING_MARK.toInt() -> true
                else -> false
            }
        }
    }
}

/**
 * O mapa da normalização do SentencePiece (`precompiled_charsmap`): uma árvore em vetor duplo (Darts) dos textos que
 * mudam, e os textos novos, terminados em zero. Como a biblioteca, vale o começo mais curto que tem regra.
 */
internal class Charsmap(blob: ByteArray) {
    private val array: IntArray
    private val normalized: ByteArray
    private val cache = HashMap<Int, IntArray>()

    init {
        val trieSize = littleEndian(blob, 0)
        array = IntArray(trieSize / 4) { littleEndian(blob, 4 + it * 4) }
        normalized = blob.copyOfRange(4 + trieSize, blob.size)
    }

    fun transform(cps: IntArray, from: Int, to: Int): IntArray? {
        val key = String(cps, from, to - from).toByteArray(Charsets.UTF_8)
        var pos = 0
        var unit = array[pos]
        pos = pos xor offset(unit)
        for (b in key) {
            val c = b.toInt() and 0xFF
            if (c == 0) break
            pos = pos xor c
            if (pos !in array.indices) return null
            unit = array[pos]
            if (label(unit) != c) return null
            pos = pos xor offset(unit)
            if (hasLeaf(unit)) return text(value(array[pos]))
        }
        return null
    }

    private fun text(index: Int): IntArray = synchronized(cache) {
        cache.getOrPut(index) {
            var end = index
            while (end < normalized.size && normalized[end] != 0.toByte()) end++
            String(normalized, index, end - index, Charsets.UTF_8).codePoints().toArray()
        }
    }

    private fun hasLeaf(unit: Int) = ((unit ushr 8) and 1) == 1
    private fun value(unit: Int) = unit and 0x7FFFFFFF
    private fun label(unit: Int) = unit and (Int.MIN_VALUE or 0xFF)
    private fun offset(unit: Int) = (unit ushr 10) shl ((unit and (1 shl 9)) ushr 6)

    private fun littleEndian(bytes: ByteArray, at: Int) = (bytes[at].toInt() and 0xFF) or
        ((bytes[at + 1].toInt() and 0xFF) shl 8) or ((bytes[at + 2].toInt() and 0xFF) shl 16) or
        ((bytes[at + 3].toInt() and 0xFF) shl 24)
}

/** Caracteres (code points) e o trecho do texto original de cada um. */
internal class Chars {
    var cps = IntArray(16)
    var starts = IntArray(16)
    var ends = IntArray(16)
    var size = 0

    fun add(cp: Int, start: Int, end: Int) {
        if (size == cps.size) {
            cps = cps.copyOf(size * 2)
            starts = starts.copyOf(size * 2)
            ends = ends.copyOf(size * 2)
        }
        cps[size] = cp
        starts[size] = start
        ends[size] = end
        size++
    }
}

internal class Tokens {
    private val ids = IntList()
    private val starts = IntList()
    private val ends = IntList()
    val size get() = ids.size

    fun add(id: Int, start: Int, end: Int) {
        ids.add(id)
        starts.add(start)
        ends.add(end)
    }

    fun addAll(other: Tokens) {
        for (k in 0 until other.size) add(other.ids[k], other.starts[k], other.ends[k])
    }

    fun truncate(count: Int) {
        val n = maxOf(0, count)
        ids.size = minOf(ids.size, n)
        starts.size = minOf(starts.size, n)
        ends.size = minOf(ends.size, n)
    }

    fun encoding() = Tokenizer.Encoding(ids.toArray(), starts.toArray(), ends.toArray())
}

internal class IntList {
    private var data = IntArray(16)
    var size = 0

    fun add(value: Int) {
        if (size == data.size) data = data.copyOf(size * 2)
        data[size++] = value
    }

    operator fun get(index: Int) = data[index]
    operator fun set(index: Int, value: Int) {
        data[index] = value
    }

    fun toArray() = data.copyOf(size)
}
