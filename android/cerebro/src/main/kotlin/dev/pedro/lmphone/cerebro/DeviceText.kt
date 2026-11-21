package dev.pedro.lmphone.cerebro

/**
 * As funções de tela de `lmphone/device.py`: da árvore de acessibilidade no JSON do `state_full` (o que o `AgentService`
 * devolve) para os elementos numerados e o texto que o executor, a IA local e a máscara leem; o ponto livre de um toque;
 * e a leitura de uma chamada de ferramenta. Os elementos são mapas como os do Python (index, id, cls, checked, text,
 * bounds, blockers).
 */
@Suppress("UNCHECKED_CAST")
object DeviceText {
    private const val M = "device"
    val GBOARD = Consts.s(M, "GBOARD")
    val MIN_VISIBLE = Consts.d(M, "MIN_VISIBLE")
    val HEADER = Consts.s(M, "HEADER")
    private val LINE_BREAK = Py.re("\\s*[\\r\\n]+\\s*")
    private val INVOKE = Py.re("<invoke name=\"([\\w-]+)\">")
    private val PARAMETER = Py.re("<parameter name=\"(\\w+)\">(.*?)</parameter>", "s")

    private fun box(node: Map<String, Any?>): List<Long> {
        val bounds = node["boundsInScreen"] as Map<String, Any?>? ?: emptyMap()
        return listOf("left", "top", "right", "bottom").map { (bounds[it] as Number?)?.toLong() ?: 0L }
    }

    private fun visible(node: Map<String, Any?>, width: Long, height: Long): Double {
        if (node["boundsInScreen"] == null) return 0.0
        val (left, top, right, bottom) = box(node)
        if (right - left == 0L && bottom - top == 0L) return 0.0
        if (left <= 0 && top <= 0 && right >= width && bottom >= height) return 1.0
        val area = (right - left) * (bottom - top)
        val seen = maxOf(0L, minOf(right, width) - maxOf(left, 0L)) * maxOf(0L, minOf(bottom, height) - maxOf(top, 0L))
        return if (area > 0) seen.toDouble() / area else 0.0
    }

    private fun children(node: Map<String, Any?>) = (Py.or(node["children"], emptyList<Any?>()) as List<*>).map { it as Map<String, Any?> }

    private fun withoutKeyboard(node: Map<String, Any?>): Map<String, Any?>? {
        val kept = children(node).mapNotNull { withoutKeyboard(it) }
        if (Py.str(Py.or(node["resourceId"], "")).startsWith(GBOARD)) return null
        return LinkedHashMap(node).apply { put("children", kept) }
    }

    private fun onScreen(node: Map<String, Any?>, width: Long, height: Long): Map<String, Any?>? {
        if (node["ignoreBoundsFiltering"] == "true") return node
        val kept = children(node).mapNotNull { onScreen(it, width, height) }
        if (visible(node, width, height) < MIN_VISIBLE && kept.isEmpty()) return null
        return LinkedHashMap(node).apply { put("children", kept) }
    }

    private fun overlap(a: List<Long>, b: List<Long>) = !(a[2] <= b[0] || b[2] <= a[0] || a[3] <= b[1] || b[3] <= a[1])

    private fun isInt(value: Any?) = value is Long || value is Int || value is Boolean

    private fun flatten(node: Map<String, Any?>, counter: IntArray, out: MutableList<MutableMap<String, Any?>>): MutableMap<String, Any?> {
        val cls = Py.str(Py.or(node["className"], ""))
        val element = linkedMapOf<String, Any?>(
            "index" to counter[0].toLong(),
            "id" to Py.or(node["resourceId"], ""),
            "cls" to if (cls.isNotEmpty()) cls.split(".").last() else "",
            "checked" to if (Py.truthy(node["isCheckable"])) (if (Py.truthy(node["isChecked"])) "isChecked=True" else "isChecked=False") else "",
            "text" to listOf(node["text"], node["contentDescription"], node["resourceId"]).firstOrNull { Py.truthy(it) }.let { it ?: cls },
            "bounds" to box(node), "blockers" to ArrayList<Any?>())
        out.add(element)
        counter[0]++
        val siblings = children(node).map { it to flatten(it, counter, out) }
        for ((raw, mine) in siblings) {
            val order = raw["drawingOrder"]
            val window = raw["windowId"]
            if (!isInt(order) || !isInt(window) || (window as Number).toLong() < 0) continue
            for ((other, theirs) in siblings) {
                val above = other["drawingOrder"]
                if (Py.eq(other["windowId"], window) && isInt(above) && (above as Number).toLong() > (order as Number).toLong() &&
                    other["isVisibleToUser"] != false && (Py.truthy(other["isClickable"]) || Py.truthy(other["isLongClickable"])) &&
                    overlap(mine["bounds"] as List<Long>, theirs["bounds"] as List<Long>)) {
                    (mine["blockers"] as MutableList<Any?>).add(theirs["bounds"])
                }
            }
        }
        return element
    }

    /** Os elementos da tela, já filtrados e numerados, a partir do `state_full`. */
    fun elementsOf(state: Map<String, Any?>): List<MutableMap<String, Any?>> {
        val screen = ((state["device_context"] as Map<String, Any?>?)?.let { Py.or(it, emptyMap<String, Any?>()) }
            ?.get("screen_bounds") as Map<String, Any?>?) ?: emptyMap()
        val width = (screen["width"] as Number?)?.toLong() ?: 1080L
        val height = (screen["height"] as Number?)?.toLong() ?: 2400L
        var tree = withoutKeyboard(state["a11y_tree"] as Map<String, Any?>)
        tree = if (tree != null) onScreen(tree, width, height) else null
        val out = ArrayList<MutableMap<String, Any?>>()
        if (tree != null) flatten(tree, intArrayOf(1), out)
        return out
    }

    /** Um elemento é uma linha do texto da tela. */
    fun oneLine(text: String) = Py.sub(LINE_BREAK, text, " ")

    /** A tela como texto, no formato do Mobilerun: o que vai dentro de `<device_state>`. */
    fun render(state: Map<String, Any?>, elements: List<Map<String, Any?>>): String {
        val phone = Py.or(state["phone_state"] as Map<String, Any?>?, emptyMap())
        val app = if ("currentApp" in phone) phone["currentApp"] else ""
        val pkg = if ("packageName" in phone) phone["packageName"] else ""
        val focused = oneLine(Py.str(Py.or((Py.or(phone["focusedElement"] as Map<String, Any?>?, emptyMap()))["text"], "")))
        val lines = mutableListOf("**Current Phone State:**")
        if (Py.truthy(app) || Py.truthy(pkg)) {
            lines.add(if (Py.truthy(app) && Py.truthy(pkg)) "• **App:** ${Py.str(app)} (${Py.str(pkg)})" else "• **App:** ${Py.str(Py.or(app, pkg))}")
        }
        lines.add("• **Keyboard:** ${if (Py.truthy(phone["isEditable"])) "Visible" else "Hidden"}")
        lines.add("• **Focused Element:** '$focused'")
        val rows = elements.map { e ->
            val details = listOf(e["id"], e["text"]).filter { Py.truthy(it) }.joinToString(", ") { "\"${oneLine(Py.str(it))}\"" }
            val bounds = e["bounds"] as List<*>
            listOf("${Py.str(e["index"])}.", if (Py.truthy(e["cls"])) "${Py.str(e["cls"])}:" else "", details,
                if (Py.truthy(e["checked"])) "; ${Py.str(e["checked"])}" else "",
                "- (${bounds.joinToString(",") { Py.str(it) }})").filter { it.isNotEmpty() }.joinToString(" ")
        }
        return Py.strip(lines.joinToString("\n") + "\n\n" + HEADER + if (rows.isNotEmpty()) rows.joinToString("\n") else "No UI elements found")
    }

    /** Centro do maior retângulo de `bounds` que nenhum obstáculo cobre, ou null. */
    fun uncovered(bounds: List<Long>, blockers: List<List<Long>>): List<Long>? {
        var regions = if (bounds[0] < bounds[2] && bounds[1] < bounds[3]) listOf(bounds) else emptyList()
        for (blocker in blockers) {
            val remaining = ArrayList<List<Long>>()
            for ((left, top, right, bottom) in regions) {
                val bl = maxOf(left, blocker[0])
                val bt = maxOf(top, blocker[1])
                val br = minOf(right, blocker[2])
                val bb = minOf(bottom, blocker[3])
                if (bl >= br || bt >= bb) {
                    remaining.add(listOf(left, top, right, bottom))
                    continue
                }
                remaining.addAll(listOf(listOf(left, top, right, bt), listOf(left, bb, right, bottom), listOf(left, bt, bl, bb), listOf(br, bt, right, bb))
                    .filter { it[0] < it[2] && it[1] < it[3] })
            }
            regions = remaining
        }
        if (regions.isEmpty()) return null
        val (left, top, right, bottom) = regions.maxByOrNull { (it[2] - it[0]) * (it[3] - it[1]) }!!
        return listOf(Math.floorDiv(left + right, 2L), Math.floorDiv(top + bottom, 2L))
    }

    /** Onde tocar no elemento: o centro, ou um ponto livre se o centro está coberto por outro controle. */
    fun point(element: Map<String, Any?>, width: Long? = null, height: Long? = null): List<Long> {
        var (left, top, right, bottom) = (element["bounds"] as List<*>).map { (it as Number).toLong() }
        val x = Math.floorDiv(left + right, 2L)
        val y = Math.floorDiv(top + bottom, 2L)
        val blockers = (element["blockers"] as List<*>).map { b -> (b as List<*>).map { (it as Number).toLong() } }
        if (blockers.none { (l, t, r, b) -> l <= x && x < r && t <= y && y < b }) return listOf(x, y)
        if (width != null && width != 0L && height != null && height != 0L) {
            left = maxOf(0L, left)
            top = maxOf(0L, top)
            right = minOf(width, right)
            bottom = minOf(height, bottom)
        }
        return uncovered(listOf(left, top, right, bottom), blockers)
            ?: throw IllegalArgumentException("No clear tap point for element ${Py.str(element["index"])}")
    }

    /** (nome, parâmetros) da chamada de ferramenta que o executor escreve. */
    fun parseCall(text: String): Pair<String?, Map<String, String>> {
        val name = INVOKE.matcher(text)
        if (!name.find()) return null to emptyMap()
        val params = LinkedHashMap<String, String>()
        Py.findall(PARAMETER, text.substring(name.end())).forEach { (it as List<*>).let { (k, v) -> params[k as String] = v as String } }
        return name.group(1) to params
    }
}
