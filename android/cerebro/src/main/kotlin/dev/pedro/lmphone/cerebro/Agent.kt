package dev.pedro.lmphone.cerebro

import java.io.File
import java.security.SecureRandom
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.thread

/** O aparelho, para o cérebro no celular: o app o implementa pelo `AgentService` e pelas APIs do Android. */
interface Phone {
    /** A tela no JSON do `state_full` (o `/state` do AgentService). */
    fun state(): Map<String, Any?>

    /** As ações devolvem o erro em texto, ou null se foram feitas. */
    fun tap(x: Long, y: Long): String?
    fun swipe(x1: Long, y1: Long, x2: Long, y2: Long, ms: Long): String?
    fun type(text: String, clear: Boolean): String?
    fun key(name: String): String?

    /** Os apps da tela inicial: [{label, packageName}]. */
    fun apps(): List<Map<String, Any?>>
    fun launch(packageName: String): Boolean
    fun openSettings(action: String): Boolean
    fun openUrl(url: String, packageName: String?): Boolean

    /** O estado do sistema, nas chaves de `facts.py` (o que toca vem como o pacote). */
    fun facts(): Map<String, Any?>
    fun foreground(): String?
    fun smsDefault(): String?

    /** Modelo, versão do Android, versão da One UI (90000 = 9.0) e idioma: o que o `getprop` dá no PC. */
    fun deviceInfo(): Map<String, String>

    /** Liga o próprio serviço de acessibilidade e espera ele responder; false se não deu. */
    fun accessibilityOn(): Boolean

    /**
     * Quem liga a acessibilidade é a pessoa, pelo atalho do Android (a `loja`): `accessibilityOn` pede a ela e espera.
     * O pedido vai antes ao provedor, e uma resposta que não precisa da tela não pede nada à pessoa.
     */
    val personSwitches: Boolean get() = false

    /** O serviço de acessibilidade já está no ar (sem esperar nem pedir). */
    fun accessibilityReady(): Boolean = false
    fun accessibilityOff()
    fun keyboardOn()
    fun keyboardBack()

    /** A faixa do live mode (com o serviço ligado), ou null. */
    fun strip(): Strip?
}

/** O caminho até o provedor (OpenRouter): (status, corpo da resposta). Só ele tem a chave. */
/**
 * O servidor do lm_phone recusou o pedido (o limite do mês, o teto de gasto; docs/plano-play-store.md, fase 2): a
 * mensagem dele, em português, vai à pessoa. Só o app da loja fala com esse servidor; o OpenRouter não manda "mensagem".
 */
class ProviderRefusal(message: String) : RuntimeException(message)

fun interface Upstream {
    fun post(path: String, body: String): Pair<Int, ByteArray>
}

/** Os arquivos do cérebro no aparelho, com os mesmos nomes dos do PC (logs/ e data/). */
class Storage(val root: File) {
    val log = File(root, "logs/proxy.jsonl")
    val detail = File(root, "logs/detalhe")
    val live = File(root, "logs/live")
    val vault = File(root, "data/vault.json")
    val stoplist = File(root, "data/stoplist.txt")
    val preferences = File(root, "data/preferencias.txt")
    val banks = File(root, "data/banks.txt")
    val apps = File(root, "data/apps.json")
    val data = File(root, "data")
}

/**
 * A tradução de `lmphone/proxy.py` e do ciclo de `lmphone/service.py` (os comentários de cada decisão estão lá): o
 * caminho até o provedor e o estado de uma tarefa, e o ciclo ler-decidir-agir. Mascara o que sai, desmascara o que
 * volta, registra tudo (só texto mascarado no `proxy.jsonl`; os valores reais em `detalhe/` e `live/`, que nunca vão ao
 * provedor). Uma tarefa por vez (`busy`). No celular não há adb: `set` vai pelas telas (`Executor.SCREENS`).
 */
@Suppress("UNCHECKED_CAST")
class Agent(
    private val phone: Phone,
    private val upstream: Upstream,
    private val ai: LocalAi,
    private val store: Storage,
    var model: String = DEFAULT_MODEL,
) {
    val busy = ReentrantLock()
    @Volatile var continuous = false

    // --- o estado do proxy ---
    var task = ""
    var session = token()
    var cacheOn = true
    var ask = false
    var owner = false
    /** `proxy.ACTS`: false é o app da loja, que só guia (docs/plano-play-store.md); o agente nunca age nem abre o app antes. */
    var acts = true
    private var conversation: MutableMap<String, Any?>? = null
    private var history: List<Map<String, Any?>> = emptyList()
    var masker = newMasker()
        private set
    private var judged = CountDownLatch(1)
    private val screenLock = Any()
    private var requests = AtomicInteger(1)
    @Volatile var executor: Executor? = null
        private set
    private val executorLock = ReentrantLock()
    private var packages: Map<String, String?> = emptyMap()
    private var rivals: Map<String, List<String>> = emptyMap()
    private val packagesReady = CountDownLatch(1)
    private var packagesAt = 0.0
    private var began = 0.0
    private var opened: String? = null
    private val cache = Cache(store.data)
    private var device: String? = null
    private var elements: List<Map<String, Any?>> = emptyList()
    private var size: Pair<Long?, Long?> = null to null
    private var foreground: String? = null
    /** O build de depuração liga (OnDevice): cada rodada vai a `logs/gravacoes/` (`Gravacao`), com valores reais. */
    var recording = false
    private var rec: Gravacao? = null

    private fun now() = System.currentTimeMillis() / 1000.0
    private fun round3(x: Double) = Math.round(x * 1000) / 1000.0
    private fun round1(x: Double) = Math.round(x * 10) / 10.0

    private fun newMasker(): Masker {
        val masker = Masker(Vault(store.vault), loadStoplist())
        masker.session.seen.add(X.HIDDEN)
        return masker
    }

    private fun loadStoplist(): List<String> = try {
        Py.split(store.stoplist.readText())
    } catch (e: Exception) {
        emptyList()
    }

    fun banks(): Set<String> {
        val extra = try {
            store.banks.readLines().map { Py.strip(it) }.filter { it.isNotEmpty() && !it.startsWith("#") }
        } catch (e: Exception) {
            emptyList()
        }
        return BANKS + extra
    }

    fun isBank(pkg: String?) = !pkg.isNullOrEmpty() && pkg in banks()

    // --- registro ---

    fun log(entry: Map<String, Any?>) {
        try {
            store.log.parentFile?.mkdirs()
            val line = linkedMapOf<String, Any?>("time" to SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT).format(Date()),
                "ts" to round3(now()), "session" to session) + entry
            store.log.appendText(Json.dumps(line) + "\n")
        } catch (e: Exception) {
            // o registro não pode parar a tarefa
        }
    }

    fun detail(session: String, kind: String, fields: Map<String, Any?>) {
        try {
            store.detail.mkdirs()
            File(store.detail, "$session.jsonl").appendText(Json.dumps(linkedMapOf<String, Any?>("ts" to round3(now()), "tipo" to kind) + fields) + "\n")
        } catch (e: Exception) {
        }
    }

    // --- o começo de um pedido ---

    fun begin(task: String, useCache: Boolean = true, conversation: String? = null) {
        executorLock.lock()
        try {
            val current = this.conversation
            val alive = conversation != null && current != null && current["id"] == conversation &&
                now() - (current["at"] as Double) < CONVERSATION_TTL
            if (!alive) {
                this.conversation = linkedMapOf("id" to conversation, "turnos" to ArrayList<Map<String, Any?>>(), "at" to now())
                masker = newMasker()
            }
            val turns = this.conversation!!["turnos"] as List<Map<String, Any?>>
            history = turns.takeLast(MAX_TURNS).toList()
            this.task = task
            session = token()
            cacheOn = useCache
            judged = CountDownLatch(1)
            requests = AtomicInteger(1)
            executor = null
            opened = null
            began = now()
            for (password in Masking.passwords(task)) masker.session.protectLiteral(password)
        } finally {
            executorLock.unlock()
        }
    }

    fun loadPackages() {
        val started = System.nanoTime()
        var fresh = true
        var listed: List<Map<String, Any?>> = try {
            phone.apps().also { store.apps.parentFile?.mkdirs(); store.apps.writeText(Json.dumps(it)) }
        } catch (e: Exception) {
            log(linkedMapOf("apps" to linkedMapOf("erro" to e.toString())))
            fresh = false
            try {
                (Json.parse(store.apps.readText()) as List<*>).map { it as Map<String, Any?> }
            } catch (e: Exception) {
                emptyList()
            }
        }
        val found = LinkedHashMap<String, String?>()
        val same = LinkedHashMap<String, MutableList<String>>()
        for (app in listed) {
            val name = X.plain(Py.str(app["label"] ?: ""))
            same.getOrPut(name) { ArrayList() }.add(app["packageName"] as String)
            found[name] = if (name in found) null else app["packageName"] as String
        }
        if (found.isNotEmpty()) {
            packages = found
            rivals = same.filterValues { it.size > 1 }
            if (fresh) packagesAt = now()
        }
        packagesReady.countDown()
        log(linkedMapOf("apps" to linkedMapOf("seconds" to round1((System.nanoTime() - started) / 1e9), "total" to packages.size)))
    }

    private fun pickRival(candidates: List<String>): String {
        val default = try {
            phone.smsDefault()
        } catch (e: Exception) {
            null
        }
        return if (default != null && default in candidates) default else candidates.last()
    }

    fun findPackage(name: String): String? {
        val wanted = X.plain(name)
        val short = Py.sub(SHORT, wanted, "")
        for (candidate in listOf(wanted, short, APP_ALIASES[wanted], APP_ALIASES[short]).distinct()) {
            if (candidate.isNullOrEmpty()) continue
            val pkg = packages[candidate] ?: rivals[candidate]?.let { pickRival(it) }
            if (pkg != null) return pkg
        }
        val squeezed = packages.keys.associateBy { Py.sub(NOT_WORD, it, "") }
        var label = squeezed[Py.sub(NOT_WORD, wanted, "")]
        if (label == null && Py.len(wanted) >= 5) label = Difflib.closeMatches(wanted, packages.keys.toList(), 1, 0.85).firstOrNull()
        if (label != null) return packages[label] ?: rivals[label]?.let { pickRival(it) }
        return null
    }

    fun webSearch(query: String): Boolean {
        val real = Py.strip(masker.unmask(query))
        if (real.isEmpty()) return false
        val ok = try {
            phone.openUrl(WEB_SEARCH + quotePlus(real), "com.android.chrome")
        } catch (e: Exception) {
            false
        }
        log(linkedMapOf("pesquisa" to linkedMapOf("ok" to ok)))
        return ok
    }

    /** No celular nenhum ajuste muda direto (sem o adb): o executor o leva pelas telas. */
    fun setDirect(name: String, value: Any?): Any {
        val key = Py.lower(Py.strip(name))
        if (key !in X.DIRECT) return false
        log(linkedMapOf("ajuste_direto" to linkedMapOf("ajuste" to key, "valor" to value, "pelas_telas" to true)))
        return X.SCREENS
    }

    fun openSettings(page: String): Boolean {
        val action = SETTINGS[Py.lower(Py.strip(page)).replace(" ", "_")] as String? ?: return false
        return try {
            phone.openSettings(action)
        } catch (e: Exception) {
            false
        }
    }

    /** O botão da faixa no só guia (`Executor.button`), com o que o app abre quando a pessoa o toca, como `proxy.button`. */
    fun button(offer: Map<String, Any?>?): Map<String, Any?>? {
        if (offer == null) return null
        if (offer["open_settings"] != null) {
            val action = SETTINGS[Py.lower(Py.strip(Py.str(offer["open_settings"]))).replace(" ", "_")] as String? ?: return null
            return linkedMapOf("texto" to offer["text"], "acao" to action)
        }
        val pkg = findPackage(Py.str(offer["open_app"] ?: "")) ?: return null
        return linkedMapOf("texto" to offer["text"], "pacote" to pkg)
    }

    fun launch(name: String): Boolean {
        packagesReady.await(10, TimeUnit.SECONDS)
        var pkg = findPackage(name)
        if (pkg == null && packagesAt < began) {
            loadPackages()
            pkg = findPackage(name)
        }
        if (pkg == null) return false
        if (isBank(pkg)) {
            log(linkedMapOf("banco" to "abertura recusada"))
            return false
        }
        return try {
            phone.launch(pkg)
        } catch (e: Exception) {
            false
        }
    }

    // --- a IA local ---

    fun judgeTask() {
        val task = this.task
        val session = this.session
        val mine = masker
        val done = judged
        try {
            if (task.isNotEmpty()) {
                val (judgment, _, seconds) = ai.judgeRequest(task)
                if (session != this.session) return
                val decisions = LocalAi.applyRequest(judgment, mine, task)
                detail(session, "pedido", linkedMapOf("texto" to task, "julgamento" to judgment, "decisoes" to decisions, "segundos" to seconds))
                val counts = LinkedHashMap<String, Int>()
                decisions.forEach { counts.merge(it["decisao"] as String, 1, Int::plus) }
                log(linkedMapOf("local_ai" to linkedMapOf("intencao" to judgment["intencao"], "seconds" to round1(seconds), "decisoes" to counts)))
                prelaunch(judgment)
            }
        } catch (e: Exception) {
            if (session == this.session) log(linkedMapOf("local_ai" to linkedMapOf("erro" to e.toString())))
        } finally {
            done.countDown()
        }
        try {
            if (session == this.session) log(linkedMapOf("task" to mine.mask(task)))
        } catch (e: Exception) {
        }
    }

    private fun prelaunch(judgment: Map<String, Any?>) {
        val names = (judgment["entidades"] as List<*>? ?: emptyList<Any?>()).map { it as Map<String, Any?> }
            .filter { it["tipo"] == "app" }.map { it["texto"] as String }
        val started = System.nanoTime()
        if (owner || !acts || names.size != 1 || !executorLock.tryLock()) return
        try {
            if (executor == null && launch(names[0])) {
                opened = names[0]
                log(linkedMapOf("abriu_antes" to linkedMapOf("seconds" to round1((System.nanoTime() - started) / 1e9))))
            }
        } finally {
            executorLock.unlock()
        }
    }

    fun judgeScreen(messages: List<Map<String, Any?>>) {
        val texts = ArrayList<String>()
        masker.walk(messages) { texts.add(it); it }
        synchronized(screenLock) {
            val seen = masker.session.seen
            val new = texts.flatMap { LocalAi.screenFragments(it) }.distinct().filter { it !in seen }
            if (new.isEmpty()) return
            // Os modelos pequenos julgam todos os trechos (o filtro do Laya, /private, devolve 1 para todos).
            val entry = linkedMapOf<String, Any?>("trechos" to new.size, "seconds" to 0.0, "mascarar" to 0, "filtrados" to 0, "laya_seconds" to 0.0)
            val judgment = linkedMapOf<String, Any?>("trechos" to new, "laya" to new.map { 1.0 }, "gemma" to ArrayList<Any?>())
            for (batch in LocalAi.batches(new)) {
                val source = batch.joinToString(" • ")
                try {
                    val (found, _, seconds) = ai.findPrivate(source)
                    val record = linkedMapOf<String, Any?>("trechos" to batch, "achou" to found)
                    (judgment["gemma"] as MutableList<Any?>).add(record)
                    val applied = LocalAi.applyScreen(found, masker, source)
                    record["mascarados"] = applied
                    entry["mascarar"] = (entry["mascarar"] as Int) + applied.size
                    entry["seconds"] = round1((entry["seconds"] as Double) + seconds)
                    seen.addAll(batch)
                } catch (e: Exception) {
                    entry["erro"] = e.toString()
                }
            }
            log(linkedMapOf("local_ai_tela" to entry))
            detail(session, "tela", entry + linkedMapOf("julgamento" to judgment))
        }
    }

    // --- o provedor ---

    fun askProvider(prompt: String, reasoning: Boolean = true): String {
        val number = requests.getAndIncrement()
        val arrived = round3(now())
        val split = prompt.indexOf(X.SPLIT)
        val raw = if (split >= 0) listOf(prompt.substring(0, split), prompt.substring(split + X.SPLIT.length)) else listOf(prompt)
        judged.await()
        judgeScreen(raw.map { linkedMapOf<String, Any?>("content" to it) })
        val counts = LinkedHashMap<String, Int>()
        // As instruções fixas passam só pelo cofre e pelas regras de sempre (ver `proxy.ask_provider`).
        val parts = raw.mapIndexed { i, part -> masker.mask(part, counts, learn = !(split >= 0 && i == 0)) }
        val messages: List<Map<String, Any?>> = if (split >= 0) listOf(
            linkedMapOf("role" to "system", "content" to listOf(linkedMapOf("type" to "text", "text" to parts[0], "cache_control" to linkedMapOf("type" to "ephemeral")))),
            linkedMapOf("role" to "user", "content" to parts[1]))
        else listOf(linkedMapOf("role" to "user", "content" to parts[0]))
        log(linkedMapOf("request" to number, "arrived" to arrived, "model" to model, "messages" to messages.size, "masked" to counts, "sent" to messages))
        val started = System.nanoTime()
        val body = linkedMapOf<String, Any?>("model" to model, "messages" to messages)
        if (!reasoning) body["reasoning"] = linkedMapOf("enabled" to false)
        val (status, data) = upstream.post("/chat/completions", Json.dumps(body))
        val answered = linkedMapOf<String, Any?>("request" to number, "status" to status, "seconds" to round1((System.nanoTime() - started) / 1e9))
        val text = String(data, Charsets.UTF_8)
        if (status != 200) {
            log(answered + linkedMapOf("received" to Py.head(text, 2000)))
            val said = try { (Json.parse(text) as? Map<*, *>)?.get("mensagem") as? String } catch (e: Exception) { null }
            if (!said.isNullOrBlank()) throw ProviderRefusal(said)
            throw RuntimeException("o provedor respondeu $status")
        }
        val answer = Json.parse(text) as Map<String, Any?>
        val choices = (answer["choices"] as List<*>? ?: emptyList<Any?>()).map { (it as Map<String, Any?>)["message"] }
        log(answered + linkedMapOf("usage" to answer["usage"], "received" to choices))
        return masker.unmask(((answer["choices"] as List<*>)[0] as Map<String, Any?>).let { (it["message"] as Map<String, Any?>)["content"] as String })
    }

    // --- a conversa e o executor ---

    fun cachedPath() = cacheOn && acts && history.isEmpty() && masker.mask(task) == task && cache.load(task) != null

    fun historyText(): String {
        val lines = ArrayList<String>()
        for (turn in history) {
            lines.add("Owner: ${Py.str(turn["dono"])}")
            lines.add("You: ${Py.str(turn["assistente"])}")
            val done = turn["feito"] as List<*>
            if (done.isNotEmpty()) lines.add("  (on the phone: ${done.joinToString("; ")}; result: ${Py.str(turn["resultado"])})")
        }
        return if (lines.isNotEmpty()) "\n" + lines.joinToString("\n") else ""
    }

    fun rememberTurn(message: String, result: String?) {
        val done = ArrayList<String>()
        for (step in executor?.trail ?: emptyList()) {
            val target = Py.str((Py.or(step["target"] as List<Any?>?, listOf<Any?>("")))[0])
            done.add(listOf(Py.str(step["action"]), if (target.isNotEmpty()) "“$target”" else "",
                if (Py.truthy(step["text"])) "text “${Py.str(step["text"])}”" else "").filter { it.isNotEmpty() }.joinToString(" "))
        }
        (conversation!!["turnos"] as MutableList<Map<String, Any?>>).add(linkedMapOf("dono" to task, "assistente" to message,
            "feito" to done.takeLast(12), "resultado" to result))
        conversation!!["at"] = now()
    }

    fun deviceName(): String {
        device?.let { return it }
        return try {
            val info = phone.deviceInfo()
            val model = Py.strip(info["model"] ?: "")
            val android = Py.strip(info["android"] ?: "")
            val oneui = Py.strip(info["oneui"] ?: "")
            val locale = Py.strip(info["locale"] ?: "")
            if (model.isEmpty() || android.isEmpty()) return DEVICE
            var name = "Samsung ${MODELS[model] ?: model}, Android $android"
            if (oneui.isNotEmpty() && oneui.all { it.isDigit() }) name += ", One UI ${oneui.toInt() / 10000}.${oneui.toInt() / 100 % 100 / 10}"
            val language = LANGUAGES[locale.split("-")[0]] as String? ?: locale.ifEmpty { "English" }
            "$name. Interface language: $language".also { device = it }
        } catch (e: Exception) {
            DEVICE
        }
    }

    fun deviceDescription(): String {
        val lines = try {
            store.preferences.readLines().map { Py.strip(it) }.filter { it.isNotEmpty() && !it.startsWith("#") }
        } catch (e: Exception) {
            emptyList()
        }
        return deviceName() + if (lines.isNotEmpty()) ". The owner's preferred apps (use them when the task does not name one): " + lines.joinToString("; ") else ""
    }

    fun readFacts(): Map<String, Any?> {
        val names = packages.entries.filter { it.value != null }.associate { it.value!! to it.key }
        val state = LinkedHashMap(phone.facts())
        state["media_playing"]?.let { playing -> if (playing is String && playing != "nothing") state["media_playing"] = names[playing] ?: playing }
        detail(session, "estado", linkedMapOf("estado" to state))
        return state
    }

    private fun makeExecutor() {
        if (executor == null) {
            val made = Executor(task, null, null, deviceDescription(), { launch(it) }, opened, { readFacts() }, historyText(), { openSettings(it) })
            made.assistant = true
            made.actsOnPhone = acts
            made.setter = { name, value -> setDirect(name, value) }
            made.searcher = { webSearch(it) }
            made.canAsk = ask
            made.mayAsk = ask
            if (history.isNotEmpty() && history.last()["resultado"] == "a confirmar" && X.yesNo(task) == true) made.preapproved = true
            val saved = if (cachedPath()) cache.load(task) else null
            made.cached = saved != null
            if (saved != null) made.use(saved.first, saved.second)
            made.map = if (cacheOn) cache.maps() else LinkedHashMap()
            executor = made
            rec?.let { record(it, made) }
            if (made.cached) log(linkedMapOf("cache" to linkedMapOf("usado" to true, "passos" to made.plan!!.size)))
        }
        val current = executor!!
        val r = rec
        current.provider = if (r == null) { prompt -> askProvider(prompt, reasoning = current.plan != null && !current.quick) } else { prompt ->
            val reasoning = current.plan != null && !current.quick
            val started = System.nanoTime()
            try {
                askProvider(prompt, reasoning).also {
                    r.cb("provider", it, linkedMapOf("pergunta" to prompt, "raciocinio" to reasoning, "segundos" to round1((System.nanoTime() - started) / 1e9)))
                }
            } catch (e: Exception) {
                r.cb("provider", null, linkedMapOf("pergunta" to prompt, "raciocinio" to reasoning, "erro" to e.toString(),
                    "recusa" to (e as? ProviderRefusal)?.message, "segundos" to round1((System.nanoTime() - started) / 1e9)))
                throw e
            }
        }
    }

    /** Grava o executor novo e tudo o que ele pede de fora, com o que voltou (`Gravacao`). */
    private fun record(r: Gravacao, made: Executor) {
        r.write("executor", linkedMapOf("pedido" to made.task, "aparelho" to made.device, "aberto" to made.opened, "historia" to made.history,
            "acts" to made.actsOnPhone, "ask" to made.canAsk, "preaprovado" to made.preapproved, "cache" to made.cached, "mapa" to made.map))
        val clock = made.clock
        made.clock = { clock().also { r.cb("clock", it) } }
        made.facts?.let { f -> made.facts = { f().also { r.cb("facts", it) } } }
        made.launch?.let { f -> made.launch = { name -> f(name).also { r.cb("launch", it, linkedMapOf("args" to listOf(name))) } } }
        made.settings?.let { f -> made.settings = { page -> f(page).also { r.cb("settings", it, linkedMapOf("args" to listOf(page))) } } }
        made.setter?.let { f -> made.setter = { name, value -> f(name, value).also { r.cb("setter", it, linkedMapOf("args" to listOf(name, value))) } } }
        made.searcher?.let { f -> made.searcher = { q -> f(q).also { r.cb("searcher", it, linkedMapOf("args" to listOf(q))) } } }
    }

    fun instruct(text: String) {
        for (password in Masking.passwords(text)) masker.session.protectLiteral(password)
        try {
            val (judgment, _, seconds) = ai.judgeRequest(text)
            val decisions = LocalAi.applyRequest(judgment, masker, text)
            detail(session, "instrucao", linkedMapOf("texto" to text, "julgamento" to judgment, "decisoes" to decisions, "segundos" to seconds))
        } catch (e: Exception) {
            log(linkedMapOf("local_ai" to linkedMapOf("erro_instrucao" to e.toString())))
        }
        executorLock.lock()
        try {
            executor?.instructions?.add(text)
            rec?.write("instrucao", linkedMapOf("texto" to text, "aplicada" to (executor != null)))
        } finally {
            executorLock.unlock()
        }
        log(linkedMapOf("instrucao" to linkedMapOf("texto" to masker.mask(text))))
    }

    fun answered(question: String, answer: String, secret: Boolean) {
        if (secret) {
            masker.session.protectLiteral(answer)
            detail(session, "resposta", linkedMapOf("pergunta" to question, "resposta" to "[segredo]"))
        } else {
            for (password in Masking.passwords(answer)) masker.session.protectLiteral(password)
            try {
                val (judgment, _, _) = ai.judgeRequest(answer)
                val decisions = LocalAi.applyRequest(judgment, masker, answer)
                detail(session, "resposta", linkedMapOf("pergunta" to question, "resposta" to answer, "julgamento" to judgment, "decisoes" to decisions))
            } catch (e: Exception) {
                log(linkedMapOf("local_ai" to linkedMapOf("erro_resposta" to e.toString())))
            }
        }
        executorLock.lock()
        try {
            executor?.answers?.add(listOf(question, answer))
            rec?.write("resposta", linkedMapOf("pergunta" to question, "resposta" to answer, "aplicada" to (executor != null)))
        } finally {
            executorLock.unlock()
        }
        log(linkedMapOf("resposta" to linkedMapOf("pergunta" to masker.mask(question), "texto" to masker.mask(answer))))
    }

    fun confirmed(question: String, answer: String): Boolean? {
        executorLock.lock()
        val verdict = try {
            executor?.confirmAnswer(answer).also { rec?.write("confirmacao", linkedMapOf("resposta" to answer, "liberou" to it)) }
        } finally {
            executorLock.unlock()
        }
        detail(session, "confirmacao", linkedMapOf("pergunta" to question, "resposta" to answer, "liberou" to verdict))
        log(linkedMapOf("confirmacao" to linkedMapOf("pergunta" to masker.mask(question), "resposta" to masker.mask(answer), "liberou" to verdict)))
        if (verdict == null) answered(question, answer, false)
        return verdict
    }

    fun stoppedByUser(why: String) {
        executorLock.lock()
        try {
            executor?.result = "interrompida"
            rec?.write("parada", linkedMapOf("motivo" to why))
            rememberTurn("(o dono interrompeu)", "interrompida")
        } finally {
            executorLock.unlock()
        }
        log(linkedMapOf("exec" to linkedMapOf("por" to "usuário", "decisao" to "Tarefa interrompida pelo usuário ($why).", "acao" to "",
            "resultado" to "interrompida"), "arrived" to round3(now())))
    }

    fun planAhead() {
        if (executor == null && !cachedPath()) judged.await()
        executorLock.lock()
        try {
            makeExecutor()
            rec?.write("preparar")
            executor!!.prepare()
        } finally {
            executorLock.unlock()
        }
    }

    /** A próxima ação para a tela em `message`: explicação e chamada de ferramenta, em texto. */
    fun localStep(message: String, arrived: Double): String {
        if (executor == null && !cachedPath()) judged.await()
        executorLock.lock()
        try {
            var seconds = 0.0
            val picks = ArrayList<Boolean>()
            makeExecutor()
            val current = executor!!
            current.pick = { wanted, labels ->
                val answer = ai.pick(wanted, labels)
                val label = answer["label"] as String?
                seconds += answer["seconds"] as Double
                detail(session, "escolha_ia", linkedMapOf("pedido" to wanted, "rotulos" to labels, "resposta" to answer))
                picks.add(label != null)
                val ranked = (answer["ranking"] as List<*>).map { it as List<*> }.filter { it[0] != null }
                val chosen = if (label == null && ranked.size >= 2 && (ranked[0][1] as Double) + (ranked[1][1] as Double) >= PICK_SPLIT) {
                    listOf("dividido", listOf(ranked[0][0], ranked[1][0]))
                } else {
                    label
                }
                rec?.cb("pick", chosen, linkedMapOf("args" to listOf(wanted, labels), "ranking" to answer["ranking"]))
                chosen
            }
            val app = Py.search(APP, message)
            current.app = app?.group(1)
            rec?.write("passo", linkedMapOf("mensagem" to message, "app" to current.app))
            var (why, tool) = try {
                current.step(message)
            } catch (e: Exception) {
                rec?.write("erro", linkedMapOf("erro" to e.toString()))
                "O executor falhou: $e" to ("<function_calls>\n<invoke name=\"complete\">\n<parameter name=\"success\">false</parameter>\n" +
                    "<parameter name=\"message\">O executor falhou; veja logs/proxy.jsonl.</parameter>\n</invoke>\n</function_calls>")
            }
            rec?.write("decisao", linkedMapOf("decisao" to why, "acao" to tool, "destaque" to current.highlight, "gesto" to current.gesture,
                "botao" to current.button, "fala" to current.announce, "esperando" to (current.waiting != null), "passo" to current.i,
                "por" to current.by, "resultado" to current.result))
            val complete = "name=\"complete\"" in tool
            if (complete && cacheOn) remember()
            val value = current.readValue
            val public: (String) -> String = if (value != null) { text -> text.replace(value, READ_HIDDEN) } else { text -> text }
            if (complete) {
                rememberTurn(public(current.final ?: ""), current.result)
                val s = masker.session
                detail(session, "fim", linkedMapOf("resultado" to current.result, "ajudas" to current.helps, "escolhas" to current.choices,
                    "trocas" to s.forward.filterValues { it.isNotEmpty() }, "nomes_extra" to s.extraNames.sortedWith(Py.ORDER),
                    "usuarios_extra" to s.extraLiterals.sortedWith(Py.ORDER), "liberados" to s.released.sortedWith(Py.ORDER)))
            }
            val exec = linkedMapOf<String, Any?>("por" to current.by, "passo" to current.i, "de" to (current.plan?.size ?: 0),
                "ajudas" to current.helps, "ia_seconds" to Math.round(seconds * 100) / 100.0, "ia" to if (picks.isNotEmpty()) "laya" else null,
                "ia_achou" to picks.any { it }, "decisao" to masker.mask(public(why)), "acao" to masker.mask(public(tool)))
            current.toolError?.let { exec["erro_ferramenta"] = masker.mask(it) }
            if (complete) exec["resultado"] = current.result
            log(linkedMapOf("exec" to exec, "arrived" to arrived))
            return "$why\n\n$tool"
        } finally {
            executorLock.unlock()
        }
    }

    private fun remember() {
        val current = executor ?: return
        try {
            val texts = current.trail.flatMap { (it["target"] as List<*>? ?: emptyList<Any?>()).map { t -> Py.str(t) } } +
                (current.goal ?: emptyMap<String, Any?>()).values.flatMap { labels ->
                    (if (labels is Map<*, *>) labels.values.toList() else Py.iter(labels)).map { Py.str(it) }
                }
            val clean = texts.all { masker.mask(it) == it }
            if (current.result in setOf("confirmado", "já estava") && clean && current.trail.isNotEmpty()) {
                // O mapa aprende também com os guias e no só guia (como no Python).
                cache.learn(current.trail) { label -> masker.mask(label) == label }
            }
            if (current.result in setOf("confirmado", "já estava") && current.cacheable && clean && current.trail.isNotEmpty() && acts) {
                val replay = current.cached && current.helps == 0
                if (current.result == "já estava" && !current.cached) {
                    log(linkedMapOf("cache" to linkedMapOf("gravado" to false, "passos" to current.trail.size)))
                } else if (masker.mask(task) == task && !replay && history.isEmpty()) {
                    cache.save(task, current.trail, current.goal)
                    log(linkedMapOf("cache" to linkedMapOf("gravado" to true, "passos" to current.trail.size)))
                } else if (replay) {
                    cache.worked(task)
                }
            } else if (current.cached) {
                log(linkedMapOf("cache" to linkedMapOf("falhou" to true, "apagado" to cache.failed(task))))
            }
        } catch (e: Exception) {
            log(linkedMapOf("cache" to linkedMapOf("erro" to e.toString())))
        }
    }

    // --- o ciclo da tarefa (service.py) ---

    /** A tela lida agora, em texto; os elementos ficam para os toques por índice. */
    private fun readOnce(): String {
        var last: Exception? = null
        repeat(READ_TRIES) { attempt ->
            try {
                val state = phone.state()
                val missing = listOf("a11y_tree", "phone_state", "device_context").filter { it !in state }
                if (missing.isNotEmpty()) throw IllegalStateException("o app não devolveu ${missing.joinToString(", ")}")
                val screen = (state["device_context"] as Map<String, Any?>)["screen_bounds"] as Map<String, Any?>? ?: emptyMap()
                elements = DeviceText.elementsOf(state)
                size = (screen["width"] as Number?)?.toLong() to (screen["height"] as Number?)?.toLong()
                foreground = (state["phone_state"] as Map<String, Any?>)["packageName"] as String?
                return DeviceText.render(state, elements).also { rec?.screen(it, foreground) }
            } catch (e: Exception) {
                last = e
                if (attempt < READ_TRIES - 1) Thread.sleep(500)
            }
        }
        throw last!!
    }

    /** A tela parada: lê até duas leituras seguidas saírem iguais. */
    private fun readScreen(): String {
        var screen = readOnce()
        val limit = System.nanoTime() + (STILL_LIMIT * 1e9).toLong()
        while (System.nanoTime() < limit) {
            Thread.sleep((STILL_GAP * 1000).toLong())
            val again = readOnce()
            if (again == screen) break
            screen = again
        }
        return screen
    }

    private fun act(name: String?, params: Map<String, String>): String? = try {
        if (name !in setOf("click", "swipe", "type", "system_button", "wait")) "Unknown tool: $name" else when (name) {
            "click" -> {
                val index = params.getValue("index").toLong()
                val element = elements.firstOrNull { Py.eq(it["index"], index) } ?: throw IllegalArgumentException("No element with index $index on the current screen")
                val (x, y) = DeviceText.point(element, size.first, size.second)
                phone.tap(x, y)
            }
            "swipe" -> {
                val (x1, y1) = (Json.parse(params.getValue("coordinate")) as List<*>).map { (it as Number).toLong() }
                val (x2, y2) = (Json.parse(params.getValue("coordinate2")) as List<*>).map { (it as Number).toLong() }
                phone.swipe(x1, y1, x2, y2, ((params["duration"]?.toDouble() ?: 1.0) * 1000).toLong())
            }
            "type" -> phone.type(params["text"] ?: "", params["clear"] == "true")
            "system_button" -> phone.key(Py.lower(params.getValue("button")))
            else -> {
                Thread.sleep(((params["duration"]?.toDouble() ?: 1.0) * 1000).toLong())
                null
            }
        }?.let { "Failed to $name: $it" }
    } catch (e: Exception) {
        "Failed to $name: ${e.message ?: e}"
    }

    private fun switchOn(result: MutableList<Any>) {
        val started = System.nanoTime()
        try {
            if (isBank(phone.foreground())) {
                result.add("bank")
                return
            }
            if (!phone.accessibilityOn()) {
                result.add(IllegalStateException("o serviço de acessibilidade não ligou"))
                return
            }
        } catch (e: Exception) {
            result.add(e)
            return
        }
        try {
            phone.keyboardOn()
        } catch (e: Exception) {
            log(linkedMapOf("teclado" to linkedMapOf("erro" to e.toString())))
        }
        log(linkedMapOf("acessibilidade" to linkedMapOf("ligou_em" to Math.round((System.nanoTime() - started) / 1e7) / 100.0)))
        if (now() - packagesAt > APPS_TTL) loadPackages()
    }

    fun switchOff() {
        try {
            phone.keyboardBack()
            phone.accessibilityOff()
        } catch (e: Exception) {
            log(linkedMapOf("acessibilidade" to linkedMapOf("erro_ao_desligar" to e.toString())))
        }
    }

    fun keyboardBack() {
        try {
            phone.keyboardBack()
        } catch (e: Exception) {
            log(linkedMapOf("teclado" to linkedMapOf("erro_ao_devolver" to e.toString())))
        }
    }

    private fun fail(why: String, message: String): Pair<Boolean, String> {
        log(linkedMapOf("exec" to linkedMapOf("por" to "código", "decisao" to "O serviço falhou: ${masker.mask(why)}", "acao" to "", "resultado" to "falhou"),
            "arrived" to round3(now())))
        return false to message
    }

    /**
     * Roda um pedido do começo ao fim. Devolve (concluída, mensagem), ou null se foi cancelado. `owner`: começa na vez
     * do dono; `continuous`: o pedido veio do live mode contínuo, e a acessibilidade fica ligada depois.
     */
    fun run(task: String, emit: (String) -> Unit, cancelled: AtomicBoolean, useCache: Boolean = true, ask: Boolean = false,
            conversation: String? = null, owner: Boolean = false, continuous: Boolean = false): Pair<Boolean, String>? {
        val result = try {
            runTask(task, emit, cancelled, useCache, ask, conversation, owner, continuous)
        } catch (e: Throwable) {
            rec?.write("fim", linkedMapOf("erro" to e.toString()))
            rec = null
            throw e
        }
        rec?.write("fim", linkedMapOf("ok" to result?.first, "mensagem" to result?.second, "resultado" to executor?.result))
        rec = null
        return result
    }

    private fun runTask(task: String, emit: (String) -> Unit, cancelled: AtomicBoolean, useCache: Boolean, ask: Boolean,
                        conversation: String?, owner: Boolean, continuous: Boolean): Pair<Boolean, String>? {
        begin(task, useCache, conversation)  // só guia: o caminho gravado não vale (`cachedPath`, `remember`), o mapa vale
        this.ask = ask
        this.owner = owner
        rec = if (recording) Gravacao(File(store.root, "logs/gravacoes/$session.jsonl")).also {
            it.write("inicio", linkedMapOf("pedido" to task, "sessao" to session, "modelo" to model, "acts" to acts, "ask" to ask,
                "owner" to owner, "continuo" to continuous))
        } else null
        emit("lmphone (sessão $session)")
        thread(isDaemon = true, name = "lmphone-julgamento") { judgeTask() }
        val ready = java.util.Collections.synchronizedList(ArrayList<Any>())
        // Na `loja`, a pessoa liga a acessibilidade pelo atalho: o pedido vai antes ao provedor, e só um plano que precisa
        // da tela pede o atalho a ela (uma resposta direta não pede).
        val starting = if (phone.personSwitches) null else thread(isDaemon = true, name = "lmphone-acessibilidade") { switchOn(ready) }
        try {
            planAhead()
        } catch (e: Exception) {
            starting?.join(30000)
            return fail(e.toString(), if (e is ProviderRefusal) e.message ?: "" else "O cérebro falhou ao pedir o plano; veja o registro.")
        }
        if (starting == null) {
            if (executor?.replied != null && !phone.accessibilityReady()) return answerOnly()
            switchOn(ready)
        }
        starting?.join(30000)
        if (starting == null && ready.isNotEmpty() && ready != listOf("bank")) {
            return fail("a pessoa não ligou a acessibilidade: ${ready.first()}", PERSON_DID_NOT_SWITCH)
        }
        if (executor?.replied != null && (ready.isNotEmpty() || starting?.isAlive == true)) return answerOnly()
        if (ready == listOf("bank")) return fail("app de banco em primeiro plano no começo", BANK_MESSAGE)
        if (ready.isNotEmpty() || starting?.isAlive == true) {
            return fail("a acessibilidade não ligou: ${ready.firstOrNull() ?: "demorou demais"}", "Não consegui ligar a acessibilidade do app.")
        }
        val strip = phone.strip()
        val live = if (strip != null) LiveMode(strip, session, store.live, { banks() }, { null }).also {
            it.start(task, continuous, guide = Py.search(X.HOW_TO, X.plain(task)) != null)
        } else null
        if (live != null && owner) live.passTurn(true)
        return try {
            loop(emit, cancelled, live)
        } catch (e: Stopped) {
            live?.record("fim", linkedMapOf("resultado" to "interrompida", "motivo" to e.message))
            stoppedByUser(e.message ?: "")
            if (e.message == LiveMode.NEW_REQUEST) return false to ""
            live?.show("Interrompido.")
            false to STOPPED_MESSAGE
        }
    }

    private fun answerOnly(): Pair<Boolean, String> {
        val answer = localStep("<device_state>\n</device_state>\n", round3(now()))
        val (_, params) = DeviceText.parseCall(answer.substringAfter("\n\n"))
        return (params["success"] == "true") to (params["message"] ?: "")
    }

    private fun loop(emit: (String) -> Unit, cancelled: AtomicBoolean, live: LiveMode?): Pair<Boolean, String>? {
        var error: String? = null
        var steps = 0
        var ownerWaits = 0
        var marked: List<Long>? = null
        var gestured: String? = null
        var offered: Map<String, Any?>? = null
        var rerouted = false
        while (steps < MAX_STEPS && ownerWaits < OWNER_WAIT_LIMIT) {
            if (cancelled.get()) return null
            if (live != null) {
                for (instruction in live.gate()) {
                    live.show("Entendi, mudando o plano…")
                    instruct(instruction)
                }
                executor?.let {
                    it.owner = live.owner
                    it.speaking = live.speaking
                    it.touchedAt = live.touchedAt
                    it.pressedAt = live.pressedAt
                    it.touchedText = live.touchedText
                    it.touchedTextAt = live.touchedTextAt
                    it.touchedBox = live.touchedBox
                    it.guideAgent = live.guideAgent
                    rec?.turn(linkedMapOf("owner" to it.owner, "speaking" to it.speaking, "touched_at" to it.touchedAt, "pressed_at" to it.pressedAt,
                        "touched_text" to it.touchedText, "touched_text_at" to it.touchedTextAt, "touched_box" to it.touchedBox, "guide_agent" to it.guideAgent))
                }
                if (live.continuous) continuous = true
            }
            val screen = try {
                readScreen()
            } catch (e: Exception) {
                return fail("a tela não pôde ser lida: $e", "Não consegui ler a tela do celular.")
            }
            if (isBank(foreground)) {
                continuous = false
                switchOff()
                return fail("app de banco em primeiro plano", BANK_MESSAGE)
            }
            val results = if (error != null) "<function_results>\n<result>\n<error>$error</error>\n</result>\n</function_results>\n" else ""
            val thinking = live?.thinking()
            val answer = try {
                localStep("$results\n<device_state>\n$screen\n</device_state>\n", round3(now()))
            } finally {
                thinking?.cancel()
            }
            val why = answer.substringBefore("\n\n")
            val tool = answer.substringAfter("\n\n", "")
            val (name, params) = DeviceText.parseCall(tool)
            val current = executor
            val waitingOwner = current?.waiting != null
            val rolling = current?.rolling != null
            if (waitingOwner || rolling) ownerWaits++ else steps++
            if (live != null && current != null && current.highlight != marked) {
                marked = current.highlight
                live.highlight(marked, owner = waitingOwner)
            }
            if (live != null && current != null && current.gesture != gestured) {
                gestured = current.gesture
                live.gesture(gestured)
            }
            if (live != null && current != null && current.offNames.isNotEmpty()) {
                live.record("nome_fora_da_tela", linkedMapOf("nomes" to current.offNames))  // a conferência "nomes"
                current.offNames = emptyList()
            }
            if (live != null && current != null && current.rerouting != rerouted) {
                rerouted = current.rerouting
                live.reroute(rerouted)  // a pessoa saiu do caminho: "recalculando" na faixa até a instrução nova
            }
            if (live != null && current != null && current.button != offered) {
                offered = current.button
                live.button(button(offered))  // só guia: o botão da faixa que abre o app ou a página
            }
            if (live != null && current != null && current.plan != null && current.guide != live.guiding) live.guide(current.guide)
            if (name == "ask_user") {
                val question = masker.unmask(params["question"] ?: "")
                val options = (Json.parse(params["options"]?.ifEmpty { "[]" } ?: "[]") as List<*>).map { masker.unmask(it as String) }
                val secret = params["secret"] == "true"
                emit("Pergunta ao dono: ${params["question"] ?: ""}")
                val reply = live!!.ask(question, options, secret)
                live.show("Entendi, continuando…")
                answered(params["question"] ?: "", reply, secret)
                error = null
                continue
            }
            if (name == "confirm_user") {
                val question = masker.unmask(params["question"] ?: "")
                emit("Confirmação: ${params["question"] ?: ""}")
                val reply = live!!.ask(question, listOf("Sim", "Não"), false)
                if (confirmed(question, reply) != false) live.show("Entendi, continuando…")
                error = null
                continue
            }
            if (name == "complete") {
                val done = params["success"] == "true"
                val message = params["message"] ?: ""
                if (live != null) {
                    live.record("fim", linkedMapOf("resultado" to current?.result, "mensagem" to message))
                    live.show(message)
                }
                return done to message
            }
            emit(why)
            val said = current?.announce
            if (said != null) {
                current.announce = null
                emit("Assistente: $said")
            }
            if (live != null) {
                live.record("acao", linkedMapOf<String, Any?>("ferramenta" to name, "parametros" to params, "por" to current?.by, "passo" to current?.i)
                    .apply { if (said != null) put("disse", said) })
                if (said != null) {
                    live.show(said, speak = true, open = waitingOwner)
                    if (current.guide && !waitingOwner && name != "wait") Thread.sleep((GUIDE_PAUSE * 1000).toLong())
                } else if (!waitingOwner) {
                    live.show(LiveMode.describe(name, params, elements))
                }
            }
            if (cancelled.get()) return null
            error = if (name == "open_app") {
                val opened = launch(params["text"] ?: "")
                Thread.sleep(1000)
                if (opened) null else "Could not open the app “${params["text"] ?: ""}”: no installed app has this exact name"
            } else {
                act(name, params)
            }
            if (error != null && USER_BLOCKS.any { it in error!! }) error = "$error: the action was not done"
            if (name != "wait") Thread.sleep((AFTER_ACTION * 1000).toLong())
        }
        return fail("passou de $MAX_STEPS passos", "Não consegui terminar: passei de $MAX_STEPS passos.")
    }

    companion object {
        const val DEFAULT_MODEL = "anthropic/claude-haiku-5.5"  // o padrão do service.py (MODEL no PC)
        private const val P = "proxy"
        private const val S = "service"
        val PICK_SPLIT = Consts.d(P, "PICK_SPLIT")
        val DEVICE = Consts.s(P, "DEVICE")
        val MODELS = Consts.map(P, "MODELS")
        val LANGUAGES = Consts.map(P, "LANGUAGES")
        val APP_ALIASES = Consts.map(P, "APP_ALIASES").mapValues { it.value as String }
        val WEB_SEARCH = Consts.s(P, "WEB_SEARCH")
        val READ_HIDDEN = Consts.s(P, "READ_HIDDEN")
        val CONVERSATION_TTL = Consts.d(P, "CONVERSATION_TTL")
        val MAX_TURNS = Consts.i(P, "MAX_TURNS")
        val SETTINGS = Consts.map(P, "SETTINGS")
        val UPSTREAM = Consts.s(P, "UPSTREAM")
        val MAX_STEPS = Consts.i(S, "MAX_STEPS")
        val AFTER_ACTION = Consts.d(S, "AFTER_ACTION")
        val STILL_GAP = Consts.d(S, "STILL_GAP")
        val STILL_LIMIT = Consts.d(S, "STILL_LIMIT")
        val APPS_TTL = Consts.d(S, "APPS_TTL")
        val READ_TRIES = Consts.i(S, "READ_TRIES")
        val BANK_MESSAGE = Consts.s(S, "BANK_MESSAGE")
        /** A pessoa não ligou a acessibilidade pelo atalho a tempo (a `loja`). */
        const val PERSON_DID_NOT_SWITCH = "Não consegui ver a tela. Quando quiser, segure os dois botões de volume juntos por 3 segundos e peça de novo."
        val STOPPED_MESSAGE = Consts.s(S, "STOPPED_MESSAGE")
        val USER_BLOCKS = Consts.strings(S, "USER_BLOCKS")
        val GUIDE_PAUSE = Consts.d(S, "GUIDE_PAUSE")
        val OWNER_WAIT_LIMIT = Consts.i(S, "OWNER_WAIT_LIMIT")
        val BANKS = Consts.strings("access", "BANKS").toSet()
        private val SHORT = Py.re("^(google|samsung|galaxy|microsoft)\\s+")
        private val NOT_WORD = Py.re("\\W")
        private val APP = Py.re("• \\*\\*App:\\*\\* .*?\\(?([\\w.]+)\\)?$", "m")

        fun token(): String = ByteArray(4).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }

        /** `urllib.parse.quote_plus`: letras, dígitos e "_.-~" ficam; espaço vira "+"; o resto, %XX dos bytes UTF-8. */
        fun quotePlus(text: String): String {
            val out = StringBuilder()
            for (b in text.toByteArray(Charsets.UTF_8)) {
                val c = b.toInt() and 0xFF
                when {
                    c in 'a'.code..'z'.code || c in 'A'.code..'Z'.code || c in '0'.code..'9'.code || c.toChar() in "_.-~" -> out.append(c.toChar())
                    c == ' '.code -> out.append('+')
                    else -> out.append("%%%02X".format(c))
                }
            }
            return out.toString()
        }
    }
}
