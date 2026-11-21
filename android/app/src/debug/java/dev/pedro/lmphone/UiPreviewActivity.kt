package dev.pedro.lmphone

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.os.Bundle
import android.view.View
import org.json.JSONObject

/** Fundo fictício para conferir o vidro sem capturar os dados de outro app. Só entra no APK debug; só o adb abre. */
class UiPreviewActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(object : View(this) {
            init { contentDescription = "lmphone-preview-ficticio" }
            val paint = Paint(Paint.ANTI_ALIAS_FLAG)
            val colors = intArrayOf(0xFF7B3B8C.toInt(), 0xFF4A78C2.toInt(), 0xFF489479.toInt(), 0xFFD99B49.toInt())
            override fun onDraw(canvas: Canvas) {
                canvas.drawColor(0xFF181820.toInt())
                for (row in 0..12) for (column in 0..3) {
                    paint.color = colors[(row + column) % colors.size]
                    val x = width * (column + .5f) / 4
                    val y = Ui.dp(context, 110 + row * 55).toFloat()
                    canvas.drawCircle(x, y, Ui.dp(context, 19).toFloat(), paint)
                    paint.color = Color.WHITE
                    paint.textSize = Ui.dp(context, 14).toFloat()
                    canvas.drawText("${row + 1}", x - Ui.dp(context, 5), y + Ui.dp(context, 5), paint)
                }
                paint.color = Color.WHITE
                paint.textSize = Ui.dp(context, 20).toFloat()
                canvas.drawText("Prévia • dados fictícios", Ui.dp(context, 24).toFloat(), Ui.dp(context, 50).toFloat(), paint)
            }
        })
        window.decorView.windowInsetsController?.hide(android.view.WindowInsets.Type.systemBars())
    }
}

class UiPreviewReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.hasExtra("menu_na_barra")) Ui.setHeaderMenu(context, intent.getBooleanExtra("menu_na_barra", false))
        if (intent.hasExtra("blur")) Ui.setBlurEnabled(context, intent.getBooleanExtra("blur", true))
        AgentService.instance?.previewControls()
        AssistSession.current?.previewOnly = true
        when (intent.getStringExtra("modo")) {
            "capturar" -> {
                // Exporta só o próprio painel sobre a Activity fictícia, sem screenshot de outros apps ou PiP.
                val service = AgentService.instance
                val marker = service?.rootInActiveWindow?.findAccessibilityNodeInfosByText("lmphone-preview-ficticio")
                if (!marker.isNullOrEmpty()) service.previewBitmap()?.let { bitmap ->
                    java.io.File(context.cacheDir, "interface-preview.png").outputStream().use {
                        bitmap.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
                    }
                    bitmap.recycle()
                }
            }
            "faixa" -> AgentService.instance?.handle("/live", JSONObject().put("abrir", true).put("status", "Entendendo o pedido…"))
            "texto" -> AgentService.instance?.handle("/live", JSONObject().put("abrir", true).put("status",
                "Texto fictício para conferir a resposta do assistente. O painel cresce para mostrar o conteúdo e mantém os controles na base."))
            "assistente" -> AssistService.answer(context, "Ouvindo…")
            "fechar" -> AssistService.close()
        }
        resultData = if (intent.getStringExtra("modo") in setOf("assistente", "estado_assistente"))
            AssistSession.current?.geometry()?.toString() ?: "{}"
        else AgentService.instance?.panelGeometry()?.toString() ?: "{}"
    }
}
