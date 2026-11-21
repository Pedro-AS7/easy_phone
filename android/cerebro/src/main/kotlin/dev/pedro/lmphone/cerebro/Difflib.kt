package dev.pedro.lmphone.cerebro

/**
 * O `difflib.get_close_matches` do Python (o `SequenceMatcher` de Ratcliff e Obershelp, sem lixo), que o
 * `proxy.find_package` usa para achar um app pelo nome com uma letra trocada. Em code points, como o Python.
 */
object Difflib {
    private class Matcher(private val a: IntArray, private val b: IntArray) {
        private val b2j = HashMap<Int, MutableList<Int>>().also { map ->
            b.forEachIndexed { j, c -> map.getOrPut(c) { ArrayList() }.add(j) }
            // autojunk: com 200 ou mais elementos, os que aparecem em mais de 1% são tirados (como no Python).
            if (b.size >= 200) {
                val popular = b.size / 100 + 1
                map.entries.removeIf { it.value.size > popular }
            }
        }

        fun longest(alo: Int, ahi: Int, blo: Int, bhi: Int): Triple<Int, Int, Int> {
            var besti = alo
            var bestj = blo
            var bestsize = 0
            var j2len = HashMap<Int, Int>()
            for (i in alo until ahi) {
                val next = HashMap<Int, Int>()
                for (j in b2j[a[i]] ?: emptyList<Int>()) {
                    if (j < blo) continue
                    if (j >= bhi) break
                    val k = (j2len[j - 1] ?: 0) + 1
                    next[j] = k
                    if (k > bestsize) {
                        besti = i - k + 1
                        bestj = j - k + 1
                        bestsize = k
                    }
                }
                j2len = next
            }
            // Sem lixo, a extensão do Python só alcança os elementos populares que o autojunk tirou de b2j.
            while (besti > alo && bestj > blo && a[besti - 1] == b[bestj - 1]) {
                besti--
                bestj--
                bestsize++
            }
            while (besti + bestsize < ahi && bestj + bestsize < bhi && a[besti + bestsize] == b[bestj + bestsize]) {
                bestsize++
            }
            return Triple(besti, bestj, bestsize)
        }

        fun matches(): Int {
            var total = 0
            val queue = ArrayDeque<IntArray>()
            queue.add(intArrayOf(0, a.size, 0, b.size))
            while (queue.isNotEmpty()) {
                val (alo, ahi, blo, bhi) = queue.removeLast()
                val (i, j, k) = longest(alo, ahi, blo, bhi)
                if (k > 0) {
                    total += k
                    if (alo < i && blo < j) queue.add(intArrayOf(alo, i, blo, j))
                    if (i + k < ahi && j + k < bhi) queue.add(intArrayOf(i + k, ahi, j + k, bhi))
                }
            }
            return total
        }

        fun ratio() = if (a.size + b.size == 0) 1.0 else 2.0 * matches() / (a.size + b.size)

        fun quickRatio(): Double {
            val counts = HashMap<Int, Int>()
            b.forEach { counts.merge(it, 1, Int::plus) }
            var matches = 0
            for (c in a) {
                val left = counts[c] ?: 0
                if (left > 0) matches++
                counts[c] = left - 1
            }
            return if (a.size + b.size == 0) 1.0 else 2.0 * matches / (a.size + b.size)
        }

        fun realQuickRatio() = if (a.size + b.size == 0) 1.0 else 2.0 * minOf(a.size, b.size) / (a.size + b.size)
    }

    /** As `n` melhores de `possibilities` com nota de semelhança a `word` de pelo menos `cutoff`, da melhor para a pior. */
    fun closeMatches(word: String, possibilities: List<String>, n: Int = 3, cutoff: Double = 0.6): List<String> {
        val b = word.codePoints().toArray()
        val scored = ArrayList<Pair<Double, String>>()
        for (x in possibilities) {
            val m = Matcher(x.codePoints().toArray(), b)
            if (m.realQuickRatio() >= cutoff && m.quickRatio() >= cutoff) {
                val ratio = m.ratio()
                if (ratio >= cutoff) scored.add(ratio to x)
            }
        }
        // heapq.nlargest: pela nota e, no empate, pelo texto (o maior primeiro).
        return scored.sortedWith(compareByDescending<Pair<Double, String>> { it.first }.thenComparator { p, q -> Py.ORDER.compare(q.second, p.second) })
            .take(n).map { it.second }
    }
}
