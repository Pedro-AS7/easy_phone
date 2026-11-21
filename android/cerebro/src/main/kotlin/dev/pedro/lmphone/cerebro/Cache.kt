package dev.pedro.lmphone.cerebro

import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * A tradução de `lmphone/cache.py`: o caminho de uma tarefa concluída, para repetir sem o provedor (`paths.json`), e o
 * mapa dos apps (`maps.json`), em `directory`. Guarda só rótulos de interface; quem grava (o Agent) recusa tarefas que
 * digitam, leem um valor ou em que a máscara mudaria o pedido ou um rótulo. Os arquivos têm o formato dos do PC.
 */
@Suppress("UNCHECKED_CAST")
class Cache(directory: File) {
    private val paths = File(directory, "paths.json")
    private val maps = File(directory, "maps.json")

    private fun read(file: File): MutableMap<String, Any?> = try {
        Json.parse(file.readText()) as? MutableMap<String, Any?> ?: LinkedHashMap()
    } catch (e: Exception) {
        LinkedHashMap()
    }

    private fun write(file: File, entries: Map<String, Any?>) {
        file.parentFile?.mkdirs()
        file.writeText(Json.dumps(entries))
    }

    /** (passos, objetivo) guardados para este pedido, ou null. */
    fun load(task: String): Pair<List<Any?>, Any?>? {
        val entry = read(paths)[key(task)] as Map<String, Any?>? ?: return null
        if (!Py.eq(entry["v"], VERSION)) return null
        return (entry["steps"] as List<*>).map { LinkedHashMap(it as Map<String, Any?>) } to entry["goal"]
    }

    fun save(task: String, steps: List<Map<String, Any?>>, goal: Any? = null) {
        val kept = steps.filter { !Py.truthy(it["noop"]) }.map { step -> step.filterKeys { it !in setOf("noop", "via", "seen") } }
        val entries = read(paths)
        entries[key(task)] = linkedMapOf("v" to VERSION.toLong(), "steps" to kept, "goal" to goal, "fails" to 0L,
            "saved" to SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(Date()))
        write(paths, entries)
    }

    fun worked(task: String) {
        val entries = read(paths)
        val entry = entries[key(task)] as MutableMap<String, Any?>? ?: return
        if (Py.truthy(entry["fails"])) {
            entry["fails"] = 0L
            write(paths, entries)
        }
    }

    /** Uma tarefa que partiu do cache não concluiu. true se a entrada foi apagada. */
    fun failed(task: String): Boolean {
        val entries = read(paths)
        val entry = entries[key(task)] as MutableMap<String, Any?>? ?: return false
        entry["fails"] = ((entry["fails"] as Number?)?.toLong() ?: 0L) + 1
        if ((entry["fails"] as Long) >= MAX_FAILS) entries.remove(key(task))
        write(paths, entries)
        return key(task) !in entries
    }

    /** O mapa dos apps: {app: {"children": {rótulo: nó}, "controls": [chaves desta tela]}}. */
    fun maps(): Map<String, Any?> {
        val tree = read(maps)
        return if (Py.eq(tree["v"], VERSION)) tree["apps"] as Map<String, Any?>? ?: LinkedHashMap() else LinkedHashMap()
    }

    /** Acrescenta ao mapa o caminho de uma tarefa concluída. */
    fun learn(trail: List<Map<String, Any?>>, keep: ((String) -> Boolean)? = null) {
        val tree = LinkedHashMap(maps()) as MutableMap<String, Any?>
        for (n in 1..trail.size) {
            val step = trail[n - 1]
            // Os nomes curtos da tela em que o passo foi feito (só os que `keep` aceita), como no Python.
            val screen = if (Py.truthy(step["seen"])) X.position(trail.subList(0, n - 1)) else null
            if (screen != null && screen.second.toSet().size == screen.second.size) {
                var here = tree.getOrPut(screen.first) { linkedMapOf("children" to LinkedHashMap<String, Any?>(), "controls" to ArrayList<Any?>()) }
                    as MutableMap<String, Any?>
                for (label in screen.second) {
                    here = (here["children"] as MutableMap<String, Any?>).getOrPut(label as String) {
                        linkedMapOf("children" to LinkedHashMap<String, Any?>(), "controls" to ArrayList<Any?>())
                    } as MutableMap<String, Any?>
                }
                val seen = here.getOrPut("seen") { ArrayList<Any?>() } as MutableList<Any?>
                for (label in step["seen"] as List<*>) {
                    if (label !in seen && seen.size < X.SCREEN_NAMES && (keep == null || keep(label as String))) seen.add(label)
                }
            }
            val place = X.position(trail.subList(0, n)) ?: continue
            if (place.second.toSet().size < place.second.size) continue
            var node = tree.getOrPut(place.first) { linkedMapOf("children" to LinkedHashMap<String, Any?>(), "controls" to ArrayList<Any?>()) }
                as MutableMap<String, Any?>
            for (label in place.second) {
                node = (node["children"] as MutableMap<String, Any?>).getOrPut(label as String) {
                    linkedMapOf("children" to LinkedHashMap<String, Any?>(), "controls" to ArrayList<Any?>())
                } as MutableMap<String, Any?>
            }
            val target = (step["target"] as List<*>?)?.firstOrNull()
            val controls = node["controls"] as MutableList<Any?>
            if (step["action"] in setOf("turn_on", "turn_off") && target !in controls) controls.add(target)
        }
        write(maps, linkedMapOf("v" to VERSION.toLong(), "apps" to tree))
    }

    companion object {
        val MAX_FAILS = Consts.i("cache", "MAX_FAILS")
        val VERSION = Consts.i("cache", "VERSION")

        fun key(task: String) = X.words(X.plain(task)).joinToString(" ")
    }
}
