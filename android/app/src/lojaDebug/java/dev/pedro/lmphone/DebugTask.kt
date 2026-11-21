package dev.pedro.lmphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import kotlin.concurrent.thread

/**
 * Só no build de depuração da `loja`: um pedido mandado pelo adb, para testar o guia sem o painel do assistente
 * (`adb shell am broadcast -n dev.pedro.lmphone.guia/dev.pedro.lmphone.DebugTask --es pedido "..."`). Exportado só para o
 * shell (a permissão DUMP). A resposta vai ao logcat (tag lmphone) e à faixa, como num pedido de verdade.
 */
class DebugTask : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val text = intent.getStringExtra("pedido")?.trim().orEmpty()
        if (text.isEmpty()) return
        val app = context.applicationContext
        thread(name = "lmphone-pedido-depuracao") {
            val result = OnDevice.send(app, text, { Log.i("lmphone", "andamento: $it") }, false, Brain.conversation(app))
            Log.i("lmphone", "pedido de depuração: ${if (result.ok) "concluído" else "não concluído"}: ${result.message}")
        }
    }
}
