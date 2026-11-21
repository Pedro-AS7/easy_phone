package dev.pedro.lmphone.cerebro

import java.util.regex.Pattern

/**
 * O que o cérebro lê do Python pelo cerebro.json (tools/app/cerebro.py exportar): os prompts, os limites, as listas e as
 * expressões regulares de cada módulo, com os mesmos nomes (`Consts.s("executor", "PLAN_PROMPT")`).
 */
@Suppress("UNCHECKED_CAST")
object Consts {
    private val data: Map<String, Any?> by lazy {
        val stream = Consts::class.java.getResourceAsStream("/cerebro.json") ?: error("cerebro.json não está no app")
        Json.parse(stream.use { it.readBytes().toString(Charsets.UTF_8) }) as Map<String, Any?>
    }

    val unicode: Map<String, Any?> get() = data["unicode"] as Map<String, Any?>

    fun get(module: String, name: String): Any? {
        val values = data[module] as? Map<String, Any?> ?: error("módulo $module fora do cerebro.json")
        require(name in values) { "$module.$name fora do cerebro.json" }
        return values[name]
    }

    fun s(module: String, name: String) = get(module, name) as String
    fun i(module: String, name: String) = (get(module, name) as Number).toInt()
    fun d(module: String, name: String) = (get(module, name) as Number).toDouble()
    fun strings(module: String, name: String) = (get(module, name) as List<*>).map { it as String }
    fun map(module: String, name: String) = get(module, name) as Map<String, Any?>

    /** Uma expressão regular do Python: exportada com as opções, ou um texto (as do masking são textos). */
    fun re(module: String, name: String): Pattern = when (val value = get(module, name)) {
        is String -> Py.re(value)
        is Map<*, *> -> Py.re(value["\$re"] as String, value["flags"] as String)
        else -> error("$module.$name não é uma expressão regular")
    }

    /** O texto de uma expressão regular, para compor outra (como as do masking). */
    fun pattern(module: String, name: String): String = when (val value = get(module, name)) {
        is String -> value
        is Map<*, *> -> value["\$re"] as String
        else -> error("$module.$name não é uma expressão regular")
    }
}
