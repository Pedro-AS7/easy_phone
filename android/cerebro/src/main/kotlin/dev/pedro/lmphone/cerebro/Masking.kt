package dev.pedro.lmphone.cerebro

import java.io.File
import java.util.regex.Matcher
import java.util.regex.Pattern
import kotlin.random.Random

/**
 * A tradução de `lmphone/masking.py`: pseudonimização reversível. O cofre (`Vault`) guarda só os valores reais a
 * proteger; os falsos nascem a cada tarefa na `Session`, em memória; o `Masker` troca tudo num texto numa passada só (um
 * trecho nunca é mascarado duas vezes) e desfaz as trocas na resposta do provedor. As expressões regulares e as listas
 * vêm do Python (cerebro.json).
 */
object Masking {
    val EMAIL = Consts.pattern("masking", "EMAIL")
    val CARD = Consts.pattern("masking", "CARD")
    val CPF = Consts.pattern("masking", "CPF")
    val HANDLE = Consts.pattern("masking", "HANDLE")
    val PHONE = Consts.pattern("masking", "PHONE")
    val CNPJ = Consts.pattern("masking", "CNPJ")
    val CEP = Consts.pattern("masking", "CEP")
    val CARD16 = Consts.pattern("masking", "CARD16")
    val CPF11 = Consts.pattern("masking", "CPF11")
    val CNPJ14 = Consts.pattern("masking", "CNPJ14")
    val PLATE = Consts.pattern("masking", "PLATE")
    val LABELED = Consts.pattern("masking", "LABELED")
    val PLATE_SHAPE = Consts.re("masking", "_PLATE_SHAPE")
    val MIN_CODE_DIGITS = Consts.i("masking", "MIN_CODE_DIGITS")
    val STREET = Consts.re("masking", "STREET")
    val STREET_WORD = Consts.re("masking", "_STREET_WORD")
    val STREET_NUMBER = Consts.re("masking", "_STREET_NUMBER")
    val MAX_STREET_WORDS = Consts.i("masking", "MAX_STREET_WORDS")
    val CONNECTIVES = Consts.strings("masking", "_CONNECTIVES").toSet()
    val MAX_SURNAMES = Consts.i("masking", "MAX_SURNAMES")
    val FIRST_NAMES = Consts.strings("nomes", "FIRST_NAMES").toSet()
    val SURNAMES = Consts.strings("nomes", "SURNAMES").toSet()
    val AMBIGUOUS = Consts.strings("nomes", "AMBIGUOUS").toSet()
    /** O grupo da expressão -> o tipo que vai para as contagens e para a sessão. */
    val GROUP_KIND = mapOf("card16" to "card", "cpf11" to "cpf", "cnpj14" to "cnpj")
    // (expressão, só com cara de senha): depois de "é"/":"/"=", depois de "pra"/"para", logo depois de "senha".
    private val PASSWORDS = listOf(Consts.re("masking", "PASSWORD_IS") to false, Consts.re("masking", "PASSWORD_TO") to true,
        Consts.re("masking", "PASSWORD_NEXT") to true)
    private val NOT_PASSWORD = Consts.strings("masking", "_NOT_PASSWORD").toSet()
    val STOPLIST = Consts.strings("masking", "STOPLIST")
    val PREFIXES = Consts.strings("masking", "_PREFIXES")
    val SUFFIXES = Consts.strings("masking", "_SUFFIXES")
    private val WORDS = Py.re("[^\\W\\d_]+")
    private val NOT_DIGIT = Py.re("\\D")

    /** As senhas ditas em `text`, sem a pontuação que fecha a frase ("troca a senha do wifi" não tem senha). */
    fun passwords(text: String): List<String> {
        val found = ArrayList<String>()
        for ((pattern, needsShape) in PASSWORDS) {
            for (raw in Py.findallText(pattern, text)) {
                val value = Py.rstrip(raw, ".!?\"'):=")
                if (Py.len(value) < 3 || Py.casefold(value) in NOT_PASSWORD || value in found) continue
                if (needsShape && !shaped(value)) continue
                found.add(value)
            }
        }
        return found
    }

    /** Tem cara de senha: um dígito, um símbolo ou maiúsculas no meio ("Kz81!x", "abc12345", "aBcD"). */
    private fun shaped(value: String): Boolean =
        value.codePoints().anyMatch { Character.isDigit(it) } || value.codePoints().anyMatch { !Character.isLetterOrDigit(it) } ||
            (value != Py.lower(value) && value != Py.upper(value) && value != Py.capitalize(value))

    /** Sem acentos e em minúsculas: a forma das listas de `nomes.py`. */
    fun plain(text: String): String = Py.casefold(Py.withoutMarks(text))

    fun hasLetter(text: String): Boolean = text.codePoints().anyMatch { Character.isLetter(it) }

    fun digitCount(text: String): Int = text.codePoints().filter { Character.isDigit(it) }.count().toInt()

    fun isDigits(text: String): Boolean = text.isNotEmpty() && text.codePoints().allMatch { Character.isDigit(it) }

    private fun checkDigit(digits: String, weights: List<Int>): Int {
        val total = digits.indices.sumOf { (digits[it] - '0') * weights[it] } % 11
        return if (total < 2) 0 else 11 - total
    }

    /** Os dígitos verificadores de um CPF, de um CNPJ ou de um cartão escritos sem pontuação. */
    fun valid(kind: String, digits: String): Boolean {
        if (digits.toSet().size == 1) return false
        if (kind == "cpf11") {
            return checkDigit(digits.substring(0, 9), (10 downTo 2).toList()) == digits[9] - '0' &&
                checkDigit(digits.substring(0, 10), (11 downTo 2).toList()) == digits[10] - '0'
        }
        if (kind == "cnpj14") {
            val first = listOf(5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
            return checkDigit(digits.substring(0, 12), first) == digits[12] - '0' &&
                checkDigit(digits.substring(0, 13), listOf(6) + first) == digits[13] - '0'
        }
        var total = 0  // Luhn
        for ((i, d) in digits.reversed().withIndex()) {
            val n = (d - '0') * (if (i % 2 == 1) 2 else 1)
            total += if (n > 9) n - 9 else n
        }
        return total % 10 == 0
    }

    fun words(text: String): List<String> = Py.findallText(WORDS, text)

    /** As palavras de `text` com a posição: (palavra, começo, fim). */
    fun wordSpans(text: String): List<Triple<String, Int, Int>> {
        val out = ArrayList<Triple<String, Int, Int>>()
        val m = WORDS.matcher(text)
        while (m.find()) out.add(Triple(m.group(), m.start(), m.end()))
        return out
    }

    fun digits(text: String): String = Py.sub(NOT_DIGIT, text, "")

    fun keepCase(source: String, replacement: String): String = when {
        Py.isUpper(source) && Py.len(source) > 1 -> Py.upper(replacement)
        Py.isLower(source) -> Py.lower(replacement)
        else -> replacement
    }

    /** Troca os dígitos de `text` pelos de `newDigits`, da direita para a esquerda. */
    fun swapDigits(text: String, newDigits: String): String {
        val pending = ArrayDeque(newDigits.toList())
        val out = StringBuilder()
        for (ch in text.reversed()) out.append(if (Character.isDigit(ch) && pending.isNotEmpty()) pending.removeLast() else ch)
        return out.reverse().toString()
    }
}

/** O que proteger: valores reais conhecidos, por tipo, num arquivo JSON. Não guarda valores falsos. */
class Vault(private val file: File? = null) {
    val reals: Map<String, MutableSet<String>> = KINDS.associateWith { HashSet<String>() }
    var version = 0
        private set

    init {
        if (file != null && file.exists()) {
            @Suppress("UNCHECKED_CAST")
            for ((kind, values) in Json.parse(file.readText()) as Map<String, Any?>) {
                reals[kind]?.let { set -> set.clear(); (values as List<*>).forEach { set.add(it as String) } }
            }
        }
    }

    @Synchronized
    fun add(kind: String, real: String) {
        if (reals.getValue(kind).add(real)) version++
    }

    @Synchronized
    fun save() {
        val target = file ?: return
        target.parentFile?.mkdirs()
        val temporary = File(target.path + ".tmp")
        temporary.writeText(Json.dumps(reals.mapValues { (_, v) -> v.sorted() }))
        temporary.setReadable(false, false)
        temporary.setReadable(true, true)
        if (!temporary.renameTo(target)) {
            target.delete()
            temporary.renameTo(target)
        }
    }

    companion object {
        val KINDS = listOf("name", "email", "literal", "phone")
    }
}

/** Pares real ↔ falso de uma tarefa (ou de uma conversa). Vive só na memória. */
open class Session(val vault: Vault) {
    val forward: Map<String, MutableMap<String, String>> = KINDS.associateWith { LinkedHashMap<String, String>() }
    val reverse: Map<String, MutableMap<String, String>> = KINDS.associateWith { LinkedHashMap<String, String>() }
    var version = 0
        private set
    // Decisões da IA local, válidas só nesta tarefa.
    val extraNames = LinkedHashSet<String>()  // nomes fora do cofre a mascarar, em qualquer caixa
    val capNames = LinkedHashSet<String>()  // nomes que só valem capitalizados: os que também são palavra comum
    val words = HashSet<String>()  // palavras dos textos já mascarados: um falso novo nunca é igual a uma delas
    val extraLiterals = LinkedHashSet<String>()  // nomes de usuário vistos na tela
    val released = LinkedHashSet<String>()  // nomes do cofre que precisam sair reais (pesquisa)
    val seen = LinkedHashSet<String>()  // trechos de tela que a IA local já julgou
    var random: Random = Random.Default

    @Synchronized
    fun protectName(span: String, stop: Set<String> = emptySet(), keepReleased: Boolean = false) {
        for (token in Masking.words(span)) {
            val folded = Py.casefold(token)
            if (keepReleased && folded in released) continue
            if (Py.len(token) >= 3 && folded !in stop) {
                // Uma palavra comum que também é nome ("Rosa") só vale capitalizada, a menos que tenha sido apontada
                // em minúsculas ("manda pra rosa").
                val names = if (Masking.plain(token) in Masking.AMBIGUOUS && !Py.isLower(token)) capNames else extraNames
                names.add(folded)
                released.remove(folded)
            }
        }
        version++
    }

    @Synchronized
    fun protectLiteral(span: String) {
        val value = Py.casefold(Py.lstrip(Py.strip(span), "@"))
        // Só números, com menos de 4 dígitos: casaria com qualquer outro número do texto (uma coordenada da tela).
        val short = !Masking.hasLetter(value) && Masking.digitCount(value) < 4
        if (Py.len(Py.strip(span)) >= 3 && !short) {
            extraLiterals.add(value)
            version++
        }
    }

    /** As regras de `Masker.learn` mudaram os nomes da sessão. */
    @Synchronized
    fun changed() {
        version++
    }

    @Synchronized
    fun release(span: String) {
        for (token in Masking.words(span)) {
            val folded = Py.casefold(token)
            if (folded !in extraNames) released.add(folded)
        }
        version++
    }

    /** O falso de `real` nesta tarefa, criando um par novo se ainda não existe. */
    @Synchronized
    fun get(kind: String, real: String): String {
        forward.getValue(kind)[real]?.let { return it }
        val fake = newFake(kind, real)
        forward.getValue(kind)[real] = fake
        reverse.getValue(kind)[fake] = real
        version++
        return fake
    }

    fun real(kind: String, fake: String): String? = reverse.getValue(kind)[fake]

    protected open fun newFake(kind: String, real: String): String {
        val taken = reverse.getValue(kind)
        val known = vault.reals[kind] ?: emptySet<String>()
        repeat(10000) {
            val fake = when (kind) {
                "name" -> Py.casefold(Masking.PREFIXES.random(random) + Masking.SUFFIXES.random(random)) +
                    if (taken.size > 300) Masking.SUFFIXES.random(random) else ""
                "email" -> "contato${random.nextInt(1000, 1000000)}@exemplo.com"
                "literal" -> "usuario${random.nextInt(1000, 1000000)}"
                "handle" -> "@usuario${random.nextInt(1000, 1000000)}"
                // A mesma forma: letra por letra, dígito por dígito.
                "code" -> real.map { c ->
                    if (Character.isDigit(c)) "0123456789"[random.nextInt(10)]
                    else if (Character.isLetter(c)) "ABCDEFGHJKLMNPQRSTUVWXYZ"[random.nextInt(24)] else c
                }.joinToString("")
                else -> real.map { "0123456789"[random.nextInt(10)] }.joinToString("")  // mesma quantidade de dígitos
            }
            // Um falso igual a uma palavra já vista (um "Alberto" de verdade na tela) voltaria como o real de outro.
            if (kind == "name" && (fake in words || fake in Masking.FIRST_NAMES || fake in Masking.SURNAMES)) return@repeat
            if (fake !in taken && fake !in known && fake != real) return fake
        }
        throw IllegalStateException("sem valores falsos livres para o tipo $kind")
    }

    companion object {
        val KINDS = Vault.KINDS + listOf("digits", "handle", "code")
    }
}

class Masker(val vault: Vault, stoplist: Collection<String> = emptyList(), session: Session? = null) {
    val session: Session = session ?: Session(vault)
    val stop: Set<String> = (Masking.STOPLIST + stoplist).map { Py.casefold(it) }.toSet()
    private var built: Triple<Pair<Int, Int>, Pattern, Pattern>? = null
    private var known: Pair<Int, Set<String>>? = null

    // --- cadastro de dados conhecidos (vindos do aparelho) ---

    fun addName(fullName: String) {
        for (token in Masking.words(fullName)) {
            if (Py.len(token) >= 3 && Py.casefold(token) !in stop) vault.add("name", Py.casefold(token))
        }
    }

    fun addLiteral(value: String) {
        val stripped = Py.strip(value)
        if (Py.len(stripped) >= 4 && Py.casefold(stripped) !in stop) vault.add("literal", Py.casefold(stripped))
    }

    /** Algum pedaço de `span` está no cofre? */
    fun knows(span: String): Boolean {
        val tokens = Masking.words(span).map { Py.casefold(it) }.toSet()
        return tokens.any { it in vault.reals.getValue("name") } || Py.casefold(span) in vault.reals.getValue("literal")
    }

    fun addPhone(number: String) {
        val digits = Masking.digits(number)
        if (digits.length >= 8) vault.add("phone", digits.substring(digits.length - 8))
    }

    // --- nomes e logradouros por regra (valem sem a IA local) ---

    /** Os nomes do cofre sem acento: "Livia" no texto é a "Lívia" dos contatos. */
    private fun vaultPlain(): Set<String> {
        known?.let { if (it.first == vault.version) return it.second }
        val names = vault.reals.getValue("name").map { Masking.plain(it) }.toSet()
        known = vault.version to names
        return names
    }

    /**
     * Os nomes que a forma do texto denuncia viram nomes da sessão, antes da troca (`Masker.learn` do Python): um prenome
     * de `nomes.FIRST_NAMES` em qualquer caixa e o que vem colado depois dele; um nome do cofre sem acento ou em
     * minúsculas, se a palavra só é nome; o nome de um logradouro; uma palavra igual a um falso já sorteado.
     */
    fun learn(text: String) = synchronized(vault) {
        synchronized(session) {
            val vaultNames = vault.reals.getValue("name")
            val known = vaultPlain()
            val before = session.extraNames.size + session.capNames.size
            val tokens = Masking.wordSpans(text)
            for ((i, span) in tokens.withIndex()) {
                val token = span.first
                val folded = Py.casefold(token)
                val key = Masking.plain(token)
                session.words.add(folded)
                if (Py.len(token) < 3 || folded in stop || folded in session.released) continue
                if (folded in session.reverse.getValue("name") && folded !in vaultNames) session.extraNames.add(folded)
                if (key in known && folded !in vaultNames && !Py.isLower(token)) session.capNames.add(folded)
                val listed = key in Masking.FIRST_NAMES || key in Masking.SURNAMES
                if (Py.isLower(token) && key in known && listed && key !in Masking.AMBIGUOUS) session.extraNames.add(folded)
                if (key in Masking.FIRST_NAMES && key !in Masking.AMBIGUOUS) {
                    session.extraNames.add(folded)
                    surnames(text, tokens, i, known, strict = false)
                } else if (key in Masking.FIRST_NAMES && !Py.isLower(token) && surnames(text, tokens, i, known, strict = true) > 0) {
                    session.capNames.add(folded)
                }
            }
            val streets = Masking.STREET.matcher(text)
            while (streets.find()) street(text, streets.end())
            if (session.extraNames.size + session.capNames.size != before) session.changed()
        }
    }

    /** Aprende as palavras que continuam o nome começado em `tokens[i]`. `strict`: só sobrenomes das listas ou do cofre, capitalizados. */
    private fun surnames(text: String, tokens: List<Triple<String, Int, Int>>, i: Int, known: Set<String>, strict: Boolean): Int {
        val first = tokens[i].first
        var learned = 0
        var byForm = 0
        var j = i + 1
        while (j < tokens.size && learned < Masking.MAX_SURNAMES) {
            val token = tokens[j].first
            val folded = Py.casefold(token)
            val key = Masking.plain(token)
            if (text.substring(tokens[j - 1].third, tokens[j].second) != " ") break
            if (folded in Masking.CONNECTIVES) {
                j++
                continue
            }
            if (Py.len(token) < 3 || folded in stop || folded in session.released) break
            val listed = key in Masking.SURNAMES || key in Masking.FIRST_NAMES || key in known
            if (Py.isLower(token)) {
                // Em minúsculas, só o que é nome e nada mais: em "fala pro lucas dias atrás", "dias" fica.
                if (strict || !listed || key in Masking.AMBIGUOUS) break
                session.extraNames.add(folded)
            } else if (listed) {
                (if (key in Masking.AMBIGUOUS) session.capNames else session.extraNames).add(folded)
            } else if (!strict && !Py.isLower(first) && byForm < 2) {  // "Henrique Albuquerque"
                session.capNames.add(folded)
                byForm++
            } else {
                break
            }
            learned++
            j++
        }
        return learned
    }

    /** O nome do logradouro que começa em `at`: capitalizado, com ou sem número; em minúsculas, só com o número depois. */
    private fun street(text: String, start: Int) {
        val words = ArrayList<Pair<String, Int>>()
        var at = start
        while (words.size < Masking.MAX_STREET_WORDS) {
            val m = Masking.STREET_WORD.matcher(text).region(at, text.length)
            if (!m.lookingAt()) break
            words.add(m.group(2) to m.end(2))
            at = m.end()
        }
        val capitalized = ArrayList<String>()
        for ((word, _) in words) {
            val head = String(Character.toChars(word.codePointAt(0)))
            if (!(Py.isUpper(head) || Masking.isDigits(word))) break
            capitalized.add(word)
        }
        var chosen: List<String> = capitalized
        var names = session.capNames
        if (capitalized.none { !Masking.isDigits(it) }) {
            chosen = emptyList()
            names = session.extraNames
            for ((k, word) in words.withIndex()) {
                if (Masking.STREET_NUMBER.matcher(text).region(word.second, text.length).lookingAt()) {
                    chosen = words.take(k + 1).map { it.first }
                    break
                }
            }
        }
        for (word in chosen) {
            val folded = Py.casefold(word)
            if (Py.len(word) >= 3 && !Masking.isDigits(word) && folded !in stop && folded !in session.released) names.add(folded)
        }
    }

    // --- a expressão de passada única ---

    private fun patterns(): Pair<Pattern, Pattern> = synchronized(vault) {
        synchronized(session) {
            val version = vault.version to session.version
            built?.let { if (it.first == version) return it.second to it.third }

            fun alternation(values: Collection<String>): String =
                values.sortedWith(compareByDescending<String> { Py.len(it) }.thenBy { it }).joinToString("|") { Py.escape(it) }
                    .ifEmpty { "(?!)" }

            // Um literal só de números não casa dentro da lista de coordenadas de um elemento da tela nem colado a um
            // decimal; a borda do nome é a letra, não a palavra ("livia_bastos" tem o nome dentro).
            fun build(names: Collection<String>, literals: Collection<String>, code: String): Pattern {
                val words = literals.filter { Masking.hasLetter(it) }
                val numbers = literals.filter { !Masking.hasLetter(it) }
                return Py.re(
                    "(?P<email>${Masking.EMAIL})|(?P<handle>${Masking.HANDLE})|(?P<card>${Masking.CARD})|(?P<card16>${Masking.CARD16})" +
                        "|(?P<cnpj>${Masking.CNPJ})|(?P<cpf>${Masking.CPF})|(?P<cep>${Masking.CEP})|(?P<code>$code)" +
                        "|(?P<literal>(?<!\\w)(?i:${alternation(words)})(?!\\w)" +
                        "|(?<!\\w)(?:(?<![(,])(?<!, )|(?!\\d+(?:, ?\\d+){0,3}\\)))(?:${alternation(numbers)})(?!\\w|[.,]\\d))" +
                        "|(?P<phone>${Masking.PHONE})|(?P<cpf11>${Masking.CPF11})|(?P<cnpj14>${Masking.CNPJ14})" +
                        "|(?P<name>(?<![^\\W\\d_])(?:${alternation(names)})(?![^\\W\\d_]))")
            }

            // Minúsculas ficam de fora: "casa" não é o contato "Casa". Só valem para o que a IA local apontou como nome.
            fun variants(tokens: Collection<String>, anyCase: Collection<String> = emptyList()): Set<String> =
                tokens.flatMap { listOf(Py.capitalize(it), Py.upper(it)) }.toSet() + anyCase

            val names = (vault.reals.getValue("name") + session.extraNames + session.capNames) - session.released
            val fakesAnyCase = session.extraNames.mapNotNull { session.forward.getValue("name")[it] }
            val mask = build(variants(names, session.extraNames), vault.reals.getValue("literal") + session.extraLiterals,
                "${Masking.PLATE}|${Masking.LABELED}")
            val unmask = build(variants(session.reverse.getValue("name").keys, fakesAnyCase), session.reverse.getValue("literal").keys,
                "(?<![\\w-])(?i:${alternation(session.reverse.getValue("code").keys)})(?![\\w-])")
            built = Triple(version, mask, unmask)
            mask to unmask
        }
    }

    private fun group(match: Matcher): String = GROUPS.first { match.group(it) != null }

    private fun replace(match: Matcher, lookup: (String, String) -> String?): String {
        val kind = group(match)
        val text = match.group()
        when (kind) {
            "email" -> return lookup("email", Py.lower(text)) ?: text
            // Com maiúsculas, o par é do texto como foi escrito (uma senha "Kz81!x" voltava "kz81!x"); o falso volta em
            // qualquer caixa.
            "literal" -> return lookup("literal", if (text != Py.lower(text)) text else Py.casefold(text))
                ?: lookup("literal", Py.casefold(text)) ?: text
            "handle" -> return lookup("handle", Py.casefold(text)) ?: text
            "name" -> return lookup("name", Py.casefold(text))?.let { Masking.keepCase(text, Py.capitalize(it)) } ?: text
            "code" -> return lookup("code", Py.upper(text))?.let { if (Py.isLower(text)) Py.lower(it) else it } ?: text
        }
        val digits = Masking.digits(text)
        val other = if (kind == "phone") lookup("phone", digits.substring(maxOf(0, digits.length - 8))) else lookup("digits", digits)
        return if (other != null) Masking.swapDigits(text, other) else text
    }

    /** `trace`, se dado, recebe (tipo, real, falso) por troca feita. `learn = false`: sem as regras de nome de `learn`. */
    fun mask(text: String, counts: MutableMap<String, Int>? = null, trace: MutableList<Triple<String, String, String>>? = null,
             learn: Boolean = true): String {
        if (learn) learn(text)
        val pattern = patterns().first
        return Py.sub(pattern, text) { match ->
            val group = group(match)
            val found = match.group()
            if (group == "handle" && Py.casefold(found.substring(1)) in session.released) return@sub found
            if (group in Masking.GROUP_KIND && !Masking.valid(group, Masking.digits(found))) return@sub found
            if (group == "code" && !(Py.fullmatch(Masking.PLATE_SHAPE, found) != null || Masking.digitCount(found) >= Masking.MIN_CODE_DIGITS)) {
                return@sub found
            }
            val kind = Masking.GROUP_KIND[group] ?: group
            val new = replace(match) { k, real -> session.get(k, real) }
            if (new != found) {
                counts?.merge(kind, 1, Int::plus)
                trace?.add(Triple(kind, match.group(), new))
            }
            new
        }
    }

    fun unmask(text: String): String = Py.sub(patterns().second, text) { match -> replace(match) { k, fake -> session.real(k, fake) } }

    /** Aplica `fn` a todas as strings de uma estrutura JSON. */
    fun walk(value: Any?, fn: (String) -> Any?): Any? = when (value) {
        is String -> fn(value)
        is List<*> -> value.map { walk(it, fn) }
        is Map<*, *> -> value.entries.associateTo(LinkedHashMap()) { (k, v) -> k to walk(v, fn) }
        else -> value
    }

    companion object {
        private val GROUPS = listOf("email", "handle", "card", "card16", "cnpj", "cpf", "cep", "code", "literal", "phone", "cpf11",
            "cnpj14", "name")
    }
}
