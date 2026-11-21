package dev.pedro.lmphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import dev.pedro.lmphone.cerebro.Json
import org.json.JSONObject
import java.io.File

/**
 * Só no build de depuração da `loja`: grava a tela atual como o cérebro a recebe (a árvore de `Screen.state`, a mesma
 * que vira o texto de `<device_state>`) e os fatos do aparelho (`PhoneImpl.facts`, o estado que vai no plano) em
 * `files/cerebro/varredura/<nome>.json` ({"tela": ..., "fatos": ...}), para a varredura das Configurações
 * (`tests/varredura.py`): `adb shell am broadcast -n dev.pedro.lmphone.guia/dev.pedro.lmphone.DebugTela --es nome x`.
 * Exportado só para o shell (a permissão DUMP). Não toca em nada: quem navega é o PC, pelo adb.
 */
class DebugTela : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val service = AgentService.instance
        val out = File(context.filesDir, "cerebro/varredura/${intent.getStringExtra("nome") ?: "tela"}.json")
        out.parentFile?.mkdirs()
        if (service == null) {
            out.writeText("{\"erro\": \"a acessibilidade do app está desligada\"}")
        } else {
            val facts = try { JSONObject(Json.dumps(PhoneImpl(context.applicationContext) { emptySet() }.facts())) } catch (e: Exception) { JSONObject().put("erro", e.toString()) }
            out.writeText(JSONObject().put("tela", Screen.state(service)).put("fatos", facts).toString())
        }
        Log.i("lmphone", "tela gravada: ${out.name}")
        resultCode = 1
    }
}
