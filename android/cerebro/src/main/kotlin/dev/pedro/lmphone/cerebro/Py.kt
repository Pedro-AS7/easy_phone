package dev.pedro.lmphone.cerebro

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode
import java.text.Normalizer
import java.util.regex.Matcher
import java.util.regex.Pattern

/**
 * O que o cérebro em Kotlin precisa do Python para dar as mesmas respostas: as expressões regulares com o `\w`, o `\d`,
 * o `\s` e o `\b` do Python (os do Java e os do Android, que usa o ICU, são outros), o `casefold`, o `plain` dos
 * módulos, o `strip`, o `split`, o `len` em code points, a verdade dos valores (`if x:`) e um JSON que escreve como o
 * `json.dumps(ensure_ascii=False)`, com as mesmas chaves na mesma ordem: o prompt tem de sair igual, letra a letra.
 */
object Py {
    private const val WORD = "\\p{L}\\p{N}_"
    // str.isspace() do Python: os espaços do Unicode e os separadores \x1c a \x1f.
    private const val SPACE = "\\t\\n\\x0B\\f\\r\\x1C-\\x20\\x85\\xA0\\u1680\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000"
    private val cache = HashMap<String, Pattern>()

    /** Uma expressão regular escrita como no Python (`re`), com as opções "i", "m" e "s". */
    fun re(pattern: String, flags: String = ""): Pattern = synchronized(cache) {
        cache.getOrPut("$flags/$pattern") {
            var options = 0
            if ('i' in flags) options = options or Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE
            if ('m' in flags) options = options or Pattern.MULTILINE
            if ('s' in flags) options = options or Pattern.DOTALL
            Pattern.compile(translate(pattern), options)
        }
    }

    /** A sintaxe do `re` do Python na do Java: classes de caracteres, grupos com nome, `\Z`, `(?i)`. */
    fun translate(pattern: String): String {
        val out = StringBuilder()
        var i = 0
        var inClass = false
        var classStart = -1
        while (i < pattern.length) {
            val c = pattern[i]
            if (c == '\\' && i + 1 < pattern.length) {
                val n = pattern[i + 1]
                if (n == 'Q') {
                    val end = pattern.indexOf("\\E", i + 2).let { if (it < 0) pattern.length else it + 2 }
                    out.append(pattern, i, end)
                    i = end
                    continue
                }
                out.append(
                    if (inClass) when (n) {
                        'w' -> WORD
                        'W' -> "[^$WORD]"
                        'd' -> "\\p{Nd}"
                        'D' -> "\\P{Nd}"
                        's' -> SPACE
                        'S' -> "[^$SPACE]"
                        else -> "\\$n"
                    } else when (n) {
                        'w' -> "[$WORD]"
                        'W' -> "[^$WORD]"
                        'd' -> "\\p{Nd}"
                        'D' -> "\\P{Nd}"
                        's' -> "[$SPACE]"
                        'S' -> "[^$SPACE]"
                        'b' -> "(?:(?<=[$WORD])(?![$WORD])|(?<![$WORD])(?=[$WORD]))"
                        'B' -> "(?:(?<=[$WORD])(?=[$WORD])|(?<![$WORD])(?![$WORD]))"
                        'Z' -> "\\z"
                        else -> "\\$n"
                    })
                i += 2
                continue
            }
            if (inClass) {
                when {
                    c == ']' && i > classStart -> {
                        inClass = false
                        out.append(c)
                    }
                    c == '[' || c == '&' -> out.append('\\').append(c)  // no Java, "[" abre outra classe e "&&" cruza
                    else -> out.append(c)
                }
                i++
                continue
            }
            when {
                c == '[' -> {
                    inClass = true
                    out.append(c)
                    i++
                    if (i < pattern.length && pattern[i] == '^') out.append(pattern[i++])
                    // Um "]" logo no começo é um caractere, como no Python.
                    if (i < pattern.length && pattern[i] == ']') {
                        out.append("\\]")
                        i++
                    }
                    classStart = i
                    continue
                }
                pattern.startsWith("(?P<", i) -> {
                    out.append("(?<")
                    i += 4
                    continue
                }
                pattern.startsWith("(?P=", i) -> {
                    val end = pattern.indexOf(')', i)
                    out.append("\\k<").append(pattern, i + 4, end).append(">")
                    i = end + 1
                    continue
                }
                pattern.startsWith("(?i)", i) -> {
                    out.append("(?iu)")
                    i += 4
                    continue
                }
                pattern.startsWith("(?i:", i) -> {
                    out.append("(?iu:")
                    i += 4
                    continue
                }
                else -> out.append(c)
            }
            i++
        }
        return out.toString()
    }

    /** `re.escape`, para montar alternativas literais. */
    fun escape(text: String): String = Pattern.quote(text)

    fun search(pattern: Pattern, text: String): Matcher? = pattern.matcher(text).let { if (it.find()) it else null }

    fun match(pattern: Pattern, text: String): Matcher? = pattern.matcher(text).let { if (it.lookingAt()) it else null }

    fun fullmatch(pattern: Pattern, text: String): Matcher? = pattern.matcher(text).let { if (it.matches()) it else null }

    /** `re.findall`: o texto achado, o grupo 1 (com um grupo) ou a lista dos grupos ("" no que não casou). */
    fun findall(pattern: Pattern, text: String): List<Any> {
        val m = pattern.matcher(text)
        val out = ArrayList<Any>()
        while (m.find()) {
            out.add(when (m.groupCount()) {
                0 -> m.group()
                1 -> m.group(1) ?: ""
                else -> (1..m.groupCount()).map { m.group(it) ?: "" }
            })
        }
        return out
    }

    fun findallText(pattern: Pattern, text: String): List<String> = findall(pattern, text).map { it as String }

    /** `re.sub` com uma função. */
    fun sub(pattern: Pattern, text: String, replace: (Matcher) -> String): String {
        val m = pattern.matcher(text)
        val out = StringBuilder()
        var last = 0
        while (m.find()) {
            out.append(text, last, m.start()).append(replace(m))
            last = m.end()
        }
        return out.append(text, last, text.length).toString()
    }

    fun sub(pattern: Pattern, text: String, replacement: String): String = sub(pattern, text) { replacement }

    // --- texto ---

    // As tabelas do Unicode do Python (cerebro.json): o casefold de cada caractere que muda e as marcas combinantes, em
    // pares início, fim.
    private val folds: Map<Int, String> by lazy {
        (Consts.unicode["casefold"] as Map<*, *>).entries.associate { (k, v) -> (k as String).toInt() to v as String }
    }
    private val marks: IntArray by lazy {
        val ranges = Consts.unicode["combinantes"] as List<*>
        IntArray(ranges.size * 2).also { out ->
            ranges.forEachIndexed { k, r -> out[2 * k] = ((r as List<*>)[0] as Long).toInt(); out[2 * k + 1] = (r[1] as Long).toInt() }
        }
    }

    fun casefold(text: String): String {
        val out = StringBuilder(text.length)
        text.codePoints().forEach { cp -> folds[cp]?.let { out.append(it) } ?: out.appendCodePoint(cp) }
        return out.toString()
    }

    fun combining(cp: Int): Boolean {
        var lo = 0
        var hi = marks.size / 2 - 1
        while (lo <= hi) {
            val mid = (lo + hi) / 2
            when {
                cp < marks[2 * mid] -> hi = mid - 1
                cp > marks[2 * mid + 1] -> lo = mid + 1
                else -> return true
            }
        }
        return false
    }

    /** O `plain` dos módulos: sem acentos (NFKD sem as marcas), em `casefold`, sem espaços nas pontas. */
    fun plain(text: String): String = strip(casefold(withoutMarks(text)))

    /** NFKD sem as marcas combinantes (o `_plain` da IA local, antes do casefold). */
    fun withoutMarks(text: String): String {
        val out = StringBuilder(text.length)
        Normalizer.normalize(text, Normalizer.Form.NFKD).codePoints().forEach { if (!combining(it)) out.appendCodePoint(it) }
        return out.toString()
    }

    fun isSpace(cp: Int) = cp in 0x9..0xD || cp in 0x1C..0x20 || cp == 0x85 || cp == 0xA0 || cp == 0x1680 ||
        cp in 0x2000..0x200A || cp == 0x2028 || cp == 0x2029 || cp == 0x202F || cp == 0x205F || cp == 0x3000

    fun strip(text: String): String {
        var s = 0
        var e = text.length
        while (s < e && isSpace(text[s].code)) s++
        while (e > s && isSpace(text[e - 1].code)) e--
        return text.substring(s, e)
    }

    fun strip(text: String, chars: String): String = text.trim { it in chars }
    fun rstrip(text: String, chars: String): String = text.trimEnd { it in chars }
    fun lstrip(text: String, chars: String): String = text.trimStart { it in chars }

    /** `str.split()`: nos espaços, sem pedaços vazios. */
    fun split(text: String): List<String> {
        val out = ArrayList<String>()
        var i = 0
        while (i < text.length) {
            while (i < text.length && isSpace(text[i].code)) i++
            val start = i
            while (i < text.length && !isSpace(text[i].code)) i++
            if (i > start) out.add(text.substring(start, i))
        }
        return out
    }

    /** `str.splitlines()`: quebra também em \v, \f, \x1c a \x1e, \x85,   e  . */
    fun splitlines(text: String): List<String> {
        val out = ArrayList<String>()
        var start = 0
        var i = 0
        while (i < text.length) {
            val c = text[i]
            if (c == '\r' || c == '\n' || c == '\u000B' || c == '\u000C' || c in '\u001C'..'\u001E' || c == '\u0085' ||
                c == ' ' || c == ' ') {
                out.add(text.substring(start, i))
                i += if (c == '\r' && i + 1 < text.length && text[i + 1] == '\n') 2 else 1
                start = i
            } else {
                i++
            }
        }
        if (start < text.length) out.add(text.substring(start))
        return out
    }

    /** A ordem do `sorted()` do Python para textos: por code point (a do Kotlin é por unidade UTF-16). */
    val ORDER: Comparator<String> = Comparator { a, b ->
        val x = a.codePoints().iterator()
        val y = b.codePoints().iterator()
        while (x.hasNext() && y.hasNext()) {
            val diff = x.nextInt() - y.nextInt()
            if (diff != 0) return@Comparator diff
        }
        (if (x.hasNext()) 1 else 0) - (if (y.hasNext()) 1 else 0)
    }

    /** `" ".join(text.split())`. */
    fun squeeze(text: String) = split(text).joinToString(" ")

    /** `len()` do Python: em code points. */
    fun len(text: String) = text.codePointCount(0, text.length)

    /** `text[:n]` do Python, em code points. */
    fun head(text: String, n: Int): String {
        if (n <= 0) return ""
        val count = len(text)
        return if (n >= count) text else text.substring(0, text.offsetByCodePoints(0, n))
    }

    fun upper(text: String) = text.uppercase(java.util.Locale.ROOT)
    fun lower(text: String) = text.lowercase(java.util.Locale.ROOT)

    /** `str.capitalize()`: a primeira letra em título, o resto em minúsculas. */
    fun capitalize(text: String): String {
        if (text.isEmpty()) return text
        val first = text.codePointAt(0)
        val rest = text.substring(Character.charCount(first))
        return String(Character.toChars(Character.toTitleCase(first))) + lower(rest)
    }

    private fun cased(cp: Int) = Character.isUpperCase(cp) || Character.isLowerCase(cp) || Character.isTitleCase(cp)

    fun isUpper(text: String): Boolean {
        var any = false
        for (cp in text.codePoints()) {
            if (Character.isLowerCase(cp) || Character.isTitleCase(cp)) return false
            if (cased(cp)) any = true
        }
        return any
    }

    fun isLower(text: String): Boolean {
        var any = false
        for (cp in text.codePoints()) {
            if (Character.isUpperCase(cp) || Character.isTitleCase(cp)) return false
            if (cased(cp)) any = true
        }
        return any
    }

    /** A verdade de um valor no Python (`if x:`). */
    fun truthy(value: Any?): Boolean = when (value) {
        null -> false
        is Boolean -> value
        is String -> value.isNotEmpty()
        is Collection<*> -> value.isNotEmpty()
        is Map<*, *> -> value.isNotEmpty()
        is Long -> value != 0L
        is Int -> value != 0
        is Double -> value != 0.0
        is Number -> value.toDouble() != 0.0
        else -> true
    }

    /** `a or b`. */
    fun <T> or(value: T?, other: T): T = if (truthy(value)) value!! else other

    /** `str(x)` do Python para os valores do JSON. */
    fun str(value: Any?): String = when (value) {
        null -> "None"
        is Boolean -> if (value) "True" else "False"
        is String -> value
        is Double -> Json.float(value)
        is List<*>, is Map<*, *> -> repr(value)
        else -> value.toString()
    }

    /** `repr(x)` do Python para os valores do JSON (listas e dicionários com aspas simples). */
    fun repr(value: Any?): String = when (value) {
        null -> "None"
        is Boolean -> if (value) "True" else "False"
        is String -> reprString(value)
        is Double -> Json.float(value)
        is List<*> -> value.joinToString(", ", "[", "]") { repr(it) }
        is Set<*> -> if (value.isEmpty()) "set()" else value.joinToString(", ", "{", "}") { repr(it) }
        is Map<*, *> -> value.entries.joinToString(", ", "{", "}") { "${repr(it.key)}: ${repr(it.value)}" }
        else -> value.toString()
    }

    private fun reprString(text: String): String {
        val quote = if ('\'' in text && '"' !in text) '"' else '\''
        val out = StringBuilder().append(quote)
        for (c in text) {
            when {
                c == quote || c == '\\' -> out.append('\\').append(c)
                c == '\n' -> out.append("\\n")
                c == '\r' -> out.append("\\r")
                c == '\t' -> out.append("\\t")
                c.code < 0x20 || c.code == 0x7F -> out.append("\\x%02x".format(c.code))
                else -> out.append(c)
            }
        }
        return out.append(quote).toString()
    }

    /** Igualdade do Python entre valores do JSON (1 == 1.0). */
    fun eq(a: Any?, b: Any?): Boolean = when {
        a is Number && b is Number && a !is Double && b !is Double -> a.toLong() == b.toLong()
        a is Number && b is Number -> a.toDouble() == b.toDouble()
        else -> a == b
    }
}

/**
 * JSON como o do Python: objetos em `LinkedHashMap` (a ordem das chaves fica), listas em `ArrayList`, inteiros em
 * `Long`, reais em `Double`; `dumps` escreve como `json.dumps(ensure_ascii=False)` (", " e ": ", o real mais curto).
 */
object Json {
    fun parse(text: String): Any? = Parser(text).run {
        val value = value()
        space()
        if (at < text.length) throw IllegalArgumentException("Extra data: line 1 column ${at + 1} (char $at)")
        value
    }

    fun dumps(value: Any?): String = StringBuilder().also { write(it, value) }.toString()

    private fun write(out: StringBuilder, value: Any?) {
        when (value) {
            null -> out.append("null")
            is Boolean -> out.append(if (value) "true" else "false")
            is String -> string(out, value)
            is Double -> out.append(float(value))
            is Float -> out.append(float(value.toDouble()))
            is Number -> out.append(value.toLong())
            is Map<*, *> -> {
                out.append('{')
                var first = true
                for ((k, v) in value) {
                    if (!first) out.append(", ")
                    first = false
                    string(out, k.toString())
                    out.append(": ")
                    write(out, v)
                }
                out.append('}')
            }
            is Iterable<*> -> {
                out.append('[')
                var first = true
                for (v in value) {
                    if (!first) out.append(", ")
                    first = false
                    write(out, v)
                }
                out.append(']')
            }
            is Array<*> -> write(out, value.toList())
            else -> string(out, value.toString())
        }
    }

    private fun string(out: StringBuilder, text: String) {
        out.append('"')
        for (c in text) {
            when (c) {
                '"' -> out.append("\\\"")
                '\\' -> out.append("\\\\")
                '\n' -> out.append("\\n")
                '\r' -> out.append("\\r")
                '\t' -> out.append("\\t")
                '\b' -> out.append("\\b")
                '\u000C' -> out.append("\\f")
                else -> if (c.code < 0x20) out.append("\\u%04x".format(c.code)) else out.append(c)
            }
        }
        out.append('"')
    }

    /** O `repr` de um real no Python: os menos dígitos que voltam ao mesmo número; expoente fora de 1e-4 a 1e16. */
    fun float(value: Double): String {
        if (value.isNaN()) return "NaN"
        if (value.isInfinite()) return if (value > 0) "Infinity" else "-Infinity"
        if (value == 0.0) return if (1.0 / value < 0) "-0.0" else "0.0"
        var shortest = BigDecimal(value)
        for (precision in 1..17) {
            val rounded = BigDecimal(value).round(MathContext(precision, RoundingMode.HALF_EVEN))
            if (rounded.toDouble() == value) {
                shortest = rounded
                break
            }
        }
        val stripped = shortest.stripTrailingZeros()
        val digits = stripped.unscaledValue().abs().toString()
        val point = digits.length - stripped.scale()  // o valor é 0.<digits> × 10^point
        val sign = if (value < 0) "-" else ""
        return sign + if (point <= -4 || point > 16) {
            val exponent = point - 1
            val mantissa = if (digits.length > 1) digits[0] + "." + digits.substring(1) else digits
            mantissa + "e" + (if (exponent < 0) "-" else "+") + "%02d".format(kotlin.math.abs(exponent))
        } else when {
            point <= 0 -> "0." + "0".repeat(-point) + digits
            point >= digits.length -> digits + "0".repeat(point - digits.length) + ".0"
            else -> digits.substring(0, point) + "." + digits.substring(point)
        }
    }

    private class Parser(val text: String) {
        var at = 0

        fun space() {
            while (at < text.length && text[at] in " \t\n\r") at++
        }

        fun fail(what: String): Nothing = throw IllegalArgumentException("$what: char $at")

        fun value(): Any? {
            space()
            if (at >= text.length) fail("Expecting value")
            return when (val c = text[at]) {
                '{' -> obj()
                '[' -> list()
                '"' -> string()
                't' -> literal("true", true)
                'f' -> literal("false", false)
                'n' -> literal("null", null)
                'N' -> literal("NaN", Double.NaN)
                'I' -> literal("Infinity", Double.POSITIVE_INFINITY)
                else -> if (c == '-' || c.isDigit()) number() else fail("Expecting value")
            }
        }

        fun literal(word: String, value: Any?): Any? {
            if (!text.startsWith(word, at)) fail("Expecting value")
            at += word.length
            return value
        }

        fun obj(): Map<String, Any?> {
            val out = LinkedHashMap<String, Any?>()
            at++
            space()
            if (at < text.length && text[at] == '}') {
                at++
                return out
            }
            while (true) {
                space()
                if (at >= text.length || text[at] != '"') fail("Expecting property name enclosed in double quotes")
                val key = string()
                space()
                if (at >= text.length || text[at] != ':') fail("Expecting ':' delimiter")
                at++
                out[key] = value()
                space()
                if (at < text.length && text[at] == ',') {
                    at++
                    continue
                }
                if (at < text.length && text[at] == '}') {
                    at++
                    return out
                }
                fail("Expecting ',' delimiter")
            }
        }

        fun list(): List<Any?> {
            val out = ArrayList<Any?>()
            at++
            space()
            if (at < text.length && text[at] == ']') {
                at++
                return out
            }
            while (true) {
                out.add(value())
                space()
                if (at < text.length && text[at] == ',') {
                    at++
                    continue
                }
                if (at < text.length && text[at] == ']') {
                    at++
                    return out
                }
                fail("Expecting ',' delimiter")
            }
        }

        fun string(): String {
            val out = StringBuilder()
            at++
            while (true) {
                if (at >= text.length) fail("Unterminated string starting at")
                val c = text[at++]
                when {
                    c == '"' -> return out.toString()
                    c == '\\' -> {
                        if (at >= text.length) fail("Unterminated string")
                        when (val e = text[at++]) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (at + 4 > text.length) fail("Invalid \\uXXXX escape")
                                out.append(text.substring(at, at + 4).toInt(16).toChar())
                                at += 4
                            }
                            else -> fail("Invalid \\escape: $e")
                        }
                    }
                    c.code < 0x20 -> fail("Invalid control character at")
                    else -> out.append(c)
                }
            }
        }

        fun number(): Any {
            val start = at
            if (text[at] == '-') at++
            if (at < text.length && text.startsWith("Infinity", at)) {
                at += 8
                return Double.NEGATIVE_INFINITY
            }
            while (at < text.length && text[at].isDigit()) at++
            var real = false
            if (at < text.length && text[at] == '.') {
                real = true
                at++
                while (at < text.length && text[at].isDigit()) at++
            }
            if (at < text.length && (text[at] == 'e' || text[at] == 'E')) {
                real = true
                at++
                if (at < text.length && (text[at] == '+' || text[at] == '-')) at++
                while (at < text.length && text[at].isDigit()) at++
            }
            val raw = text.substring(start, at)
            return if (real) raw.toDouble() else raw.toLongOrNull() ?: raw.toDouble()
        }
    }
}
