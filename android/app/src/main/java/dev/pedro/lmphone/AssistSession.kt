package dev.pedro.lmphone

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.Bitmap
import android.text.TextWatcher
import android.text.Editable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.service.voice.VoiceInteractionSession
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.util.Log
import kotlin.concurrent.thread

/**
 * O painel do assistente, aberto pelo toque longo na tecla lateral: a última resposta (inteira, rolando), o pedido
 * (falado ou escrito), o microfone para falar de novo, o alto-falante para ligar ou desligar a resposta em voz alta, e
 * enviar. Os ícones são vetoriais (res/drawable/ic_*.xml).
 *
 * Ao abrir, ele já ouve (Voice.kt: só o reconhecedor do aparelho). O que foi entendido aparece no campo e vai sozinho
 * depois de `AUTO_SEND_MS`, a menos que o dono toque no campo para corrigir: um nome ouvido errado pode escapar da
 * máscara do jeito que foi transcrito, e ver o texto antes é a chance de corrigir.
 *
 * Ao enviar, o painel sai da frente antes de o pedido chegar ao PC: o agente lê a janela ativa, e ele leria o painel
 * no lugar do app de baixo ("o que tem nessa tela?"). Enquanto o agente age, quem mostra o andamento é a faixa do live
 * mode; no fim o painel volta com a resposta (AssistService.answer), lida em voz alta, e fecha sozinho `ANSWER_MS`
 * depois da leitura (pedido do Pedro, 2026-10-24), a menos que o dono toque nele. Um toque fora do painel o fecha.
 *
 * O botão ∞ liga o live mode contínuo (Brain.live): o painel sai, e a faixa aparece como um círculo, já ouvindo; cada
 * fala vira um pedido, até "finalizar".
 */
class AssistSession(context: Context) : VoiceInteractionSession(context) {
    internal var previewOnly = false
    private val main = Handler(Looper.getMainLooper())
    private lateinit var answer: TextView
    private lateinit var answerScroll: CappedScroll
    private lateinit var report: TextView  // só na loja: denunciar a resposta (política de conteúdo gerado por IA da Play)
    private var reportArmed = false
    private lateinit var input: EditText
    private lateinit var mic: ImageView
    private lateinit var pause: ImageView
    private lateinit var heading: TextView
    private var floating: FloatingPanel? = null
    private var glass: FrostedGlass? = null
    private lateinit var card: LinearLayout
    private lateinit var bubble: View
    private var minimized = false
    private var refreshHeader: () -> Unit = {}
    private var awaitingOpen = true
    private var hasPendingScreenshot = false
    private var pendingScreenshot: Bitmap? = null
    private var reopenAfterHide = false
    private var visible = false
    private var screenshotState = "aguardando"
    private var shownFlags = 0
    private val voiceDraft = VoiceDraft()

    init { setTheme(R.style.Theme_LmPhone_Floating) }
    /** Conferência local sem expor o texto ou os pixels da conversa. */
    internal fun geometry(): org.json.JSONObject {
        val window = window.window
        return org.json.JSONObject().put("x", window?.attributes?.x).put("y", window?.attributes?.y)
            .put("width", window?.decorView?.width).put("height", window?.decorView?.height)
            .put("glass", glass?.hasSource == true).put("native", glass?.native == true)
            .put("blur_enabled", glass?.enabled)
            .put("alpha", window?.attributes?.alpha)
            .put("minimized", minimized).put("menu_in_handle", Ui.headerMenu(context))
            .put("screenshot", screenshotState).put("show_flags", shownFlags)
            .put("drag", floating?.diagnostics()).put("format", glass?.format)
            .put("listening", listener.listening).put("writing", input.hasFocus()).put("draft_length", input.length())
            .put("mic_visible", mic.visibility == View.VISIBLE)
    }
    private val autoSend = Runnable { send() }
    private val autoHide = Runnable { finish() }
    private val listener = Listener(context,
        onPartial = { text -> input.setText(voiceDraft.join(text)); input.setSelection(input.length()) },
        onFinal = { text -> heard(text) },
        onProblem = { message -> answer.text = message; showMic(false) })

    private fun dp(value: Int) = Ui.dp(context, value)

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreateContentView(): View {
        Speaker.init(context)
        heading = TextView(context).apply {
            setTextColor(Color.WHITE)
            textSize = 13f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            gravity = Gravity.CENTER_VERTICAL
        }
        answer = TextView(context).apply {
            setTextColor(Color.WHITE)
            textSize = 13f
        }
        report = TextView(context).apply {
            setTextColor(Color.parseColor("#B0FFFFFF"))
            textSize = 12f
            paintFlags = paintFlags or android.graphics.Paint.UNDERLINE_TEXT_FLAG
            visibility = View.GONE
            setOnClickListener { reportAnswer() }
        }
        answerScroll = CappedScroll(context, dp(240)).apply {
            addView(answer)
            // Rolar a resposta é estar lendo: o painel não fecha sozinho.
            setOnTouchListener { _, _ -> main.removeCallbacks(autoHide); false }
        }
        input = EditText(context).apply {
            hint = "Fale ou digite algo…"
            setHintTextColor(Color.parseColor("#B0FFFFFF"))
            setTextColor(Color.WHITE)
            textSize = 12f
            isSingleLine = true
            imeOptions = EditorInfo.IME_ACTION_SEND
            background = Ui.rounded(context, Ui.INPUT, 24)
            setPadding(dp(12), 0, dp(12), 0)
            layoutParams = LinearLayout.LayoutParams(0, dp(34), 1f).apply { leftMargin = dp(4) }
            setOnEditorActionListener { _, _, _ -> send(); true }
            // Tocar no campo é corrigir: para de ouvir e não manda sozinho.
            setOnTouchListener { _, event ->
                if (event.action == MotionEvent.ACTION_DOWN) {
                    stopVoice()
                    main.removeCallbacks(autoHide)
                }
                false
            }
        }
        val live = Ui.icon(context, R.drawable.ic_live, "Modo contínuo") { startLive() }
        pause = Ui.icon(context, R.drawable.ic_pause, "Pausar escuta") { if (listener.listening) stopVoice() else listen() }
        Ui.setActive(pause, true)
        mic = Ui.icon(context, R.drawable.ic_mic, "Falar") { if (listener.listening) stopVoice() else listen(keepText = true) }
        mic.setOnLongClickListener { view ->
            android.widget.PopupMenu(context, view).apply {
                menu.add(if (Speaker.enabled(context)) "Silenciar respostas" else "Ler respostas em voz alta")
                setOnMenuItemClickListener { Speaker.setEnabled(context, !Speaker.enabled(context)); true }
                show()
            }
            true
        }
        val sendButton = Ui.icon(context, R.drawable.ic_send, "Enviar") { send() }.apply { visibility = View.GONE }
        val row = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(pause)
            addView(input)
            addView(Ui.margin(mic, 4))
            addView(Ui.margin(live, 4))
            addView(Ui.margin(sendButton, 4))
        }
        val actions = Ui.headerActions(context,
            Ui.icon(context, R.drawable.ic_swap_vert, "Mudar de lado", 22) { floating?.moveTo(!(floating?.atTop ?: false)) },
            Ui.icon(context, R.drawable.ic_minimize, "Minimizar", 22) { minimize() },
            Ui.icon(context, R.drawable.ic_close, "Fechar", 22) { finish() })
        val header = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(heading, LinearLayout.LayoutParams(0, dp(24), 1f))
            addView(actions)
        }
        val handle = Ui.handle(context)
        refreshHeader = Ui.configureHeader(context, handle, actions,
            { floating?.moveTo(!(floating?.atTop ?: false)) }, { minimize() }, { finish() })
        card = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), 0, dp(10), dp(10))
            isClickable = true  // o toque no painel não fecha o painel
            addView(handle)
            addView(header)
            addView(answerScroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = dp(6) })
            addView(report, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = dp(4) })
            addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = dp(8) })
        }
        bubble = Ui.icon(context, R.drawable.ic_assistant, "Abrir o assistente", 56) {
            // Uma sessão já visível pode não receber nova captura. Esconde o círculo antes de pedi-la.
            reopenAfterHide = true
            hide()
        }.apply {
            background = android.graphics.drawable.GradientDrawable().apply {
                shape = android.graphics.drawable.GradientDrawable.OVAL
                setColor(Color.parseColor("#E6202124"))
                setStroke(dp(3), Color.parseColor(Ui.ACTIVE))
            }
            visibility = View.GONE
        }
        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            addView(card)
            addView(bubble)
        }
        window.window?.let { window ->
            window.clearFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            window.addFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH)
            window.decorView.setOnTouchListener { _, event ->
                if (event.actionMasked == MotionEvent.ACTION_OUTSIDE && !minimized) { finish(); true } else false
            }
            glass = Ui.glass(window)
            floating = FloatingPanel(window, content, handle,
                onDrag = { main.removeCallbacks(autoHide); glass?.setDragging(it) },
                onMinimizeGesture = { minimize() }, onCloseGesture = { finish() })
                .also { it.bind(bubble) }
        }
        answer.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val body = (s?.length ?: 0) > 60 || s?.contains('\n') == true
                heading.text = if (body) "Assistente" else s
                answerScroll.visibility = if (body) View.VISIBLE else View.GONE
            }
            override fun afterTextChanged(s: Editable?) {}
        })
        input.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val text = !s.isNullOrBlank()
                sendButton.visibility = if (text) View.VISIBLE else View.GONE
                live.visibility = if (text) View.GONE else View.VISIBLE
            }
            override fun afterTextChanged(s: Editable?) {}
        })
        return FrameLayout(context).apply {
            addView(content, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        visible = true
        shownFlags = showFlags
        current = this
        minimized = false
        card.visibility = View.VISIBLE
        bubble.visibility = View.GONE
        refreshHeader()
        glass?.showBackground(true)
        glass?.beginOpening()
        awaitingOpen = false
        screenshotState = "aguardando"
        if (hasPendingScreenshot) {
            val screenshot = pendingScreenshot
            hasPendingScreenshot = false
            pendingScreenshot = null
            applyScreenshot(screenshot)
        }
        floating?.compact = false
        window.window?.let { window ->
            window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING or
                WindowManager.LayoutParams.SOFT_INPUT_STATE_HIDDEN)
        }
        floating?.restore()
        answerScroll.scrollTo(0, 0)
        val said = args?.getString(ANSWER)
        Log.i("lmphone", "painel: aberto (${if (said != null) "resposta" else if (busy) "ocupado" else "pedido"})")
        when {
            args?.getBoolean("restaurar") == true -> listen(keepText = true)
            said != null -> {
                answer.text = said
                if (args?.getBoolean(NOTICE) == true) {
                    report.visibility = View.GONE  // um aviso do app, não uma resposta do assistente
                } else {
                    lastAnswer = said
                    offerReport()
                }
                // A resposta é lida em voz alta (o microfone fica para o pedido seguinte), e o painel fecha depois.
                Speaker.speak(context, said) { main.postDelayed(autoHide, ANSWER_MS) }
            }
            else -> {
                answer.text = "Oi! O que você quer que eu faça?"
                listen()
            }
        }
    }

    override fun onHide() {
        visible = false
        awaitingOpen = false
        hasPendingScreenshot = false
        pendingScreenshot = null
        glass?.clear()
        floating?.cancelDrag()
        main.removeCallbacks(autoHide)
        stopVoice()
        super.onHide()
        if (reopenAfterHide) {
            reopenAfterHide = false
            main.post {
                awaitingOpen = true
                show(Bundle().apply { putBoolean("restaurar", true) }, AssistService.CONTEXT_FLAGS)
            }
        }
    }

    private fun minimize() {
        main.removeCallbacks(autoHide)
        stopVoice()
        Speaker.stop()
        context.getSystemService(InputMethodManager::class.java).hideSoftInputFromWindow(input.windowToken, 0)
        input.clearFocus()
        minimized = true
        glass?.clear()
        glass?.showBackground(false)
        window.window?.let { it.attributes = it.attributes.apply { alpha = 1f } }
        card.visibility = View.GONE
        bubble.visibility = View.VISIBLE
        floating?.compact = true
    }

    override fun onDestroy() {
        pendingScreenshot = null
        glass?.clear()
        floating?.cancelDrag()
        if (current == this) current = null
        listener.destroy()
        Speaker.stop()  // o dono fechou o painel: para de falar
        super.onDestroy()
    }

    override fun onHandleScreenshot(screenshot: Bitmap?) {
        if (!Ui.blurEnabled(context)) return
        screenshotState = when { !visible -> "antes_de_abrir"; screenshot == null -> "bloqueada"; else -> "recebida" }
        if (awaitingOpen) {
            hasPendingScreenshot = true
            pendingScreenshot = screenshot
            return
        }
        if (!visible || minimized) return
        applyScreenshot(screenshot)
    }

    private fun applyScreenshot(screenshot: Bitmap?) {
        screenshotState = if (screenshot == null) "bloqueada" else "recebida"
        if (screenshot == null) { glass?.unavailable(); return }
        val frame = context.getSystemService(WindowManager::class.java).maximumWindowMetrics.bounds
        glass?.source(screenshot, frame)
    }

    /** O Android exige pedir contexto para entregar a imagem. Não lemos nem encaminhamos a estrutura recebida. */
    override fun onHandleAssist(state: AssistState) = Unit

    private fun listen(keepText: Boolean = false) {
        Speaker.stop()
        main.removeCallbacks(autoSend)
        main.removeCallbacks(autoHide)
        context.getSystemService(InputMethodManager::class.java).hideSoftInputFromWindow(input.windowToken, 0)
        input.clearFocus()
        voiceDraft.begin(if (keepText) input.text.toString() else "")
        if (!keepText) input.setText("")
        answer.text = "Ouvindo…"
        showMic(true)
        listener.start(Wake.takeStream())  // chamado por "Alexa": o que veio logo depois dela já está no cano
    }

    private fun stopVoice() {
        main.removeCallbacks(autoSend)
        listener.stop()
        showMic(false)
        if (answer.text.toString() == "Ouvindo…") answer.text = "Escuta pausada"
    }

    private fun showMic(on: Boolean) {
        Ui.setActive(mic, on)
        mic.contentDescription = if (on) "Parar de ouvir" else "Falar"
        pause.setImageResource(if (on) R.drawable.ic_pause else R.drawable.ic_play)
        pause.contentDescription = if (on) "Pausar escuta" else "Continuar escuta"
    }

    /**
     * O que o reconhecedor entendeu: um comando (Commands.kt) vale na hora; um pedido aparece e vai sozinho logo
     * depois, se o dono não tocar no campo. Só a palavra de ativação ("Alexa" e uma pausa): ouve de novo.
     */
    private fun heard(text: String) {
        showMic(false)
        if (previewOnly) { input.setText(voiceDraft.join(text)); return }
        val command = Commands.parse(text)
        Wake.report("painel", text, command)
        if (command != null && act(command)) return
        if (Commands.onlyWake(text)) return listen()
        val said = voiceDraft.join(Commands.withoutWake(text))
        input.setText(said)
        input.setSelection(said.length)
        answer.text = "Entendi: «$said». Toca no campo para corrigir."
        main.postDelayed(autoSend, AUTO_SEND_MS)
    }

    /**
     * Um comando falado no painel. false: não vale aqui, e a fala vai como pedido (sem tarefa em curso, "pausa" e
     * "para" são pedir ao assistente para pausar ou parar a música).
     */
    private fun act(command: Command): Boolean {
        when (command) {
            Command.LIVE -> startLive()
            Command.MINIMIZE -> minimize()
            Command.CLOSE, Command.FINISH -> finish()
            Command.MUTE -> {
                Speaker.setEnabled(context, false)
                reply("Voz desligada: as respostas ficam só escritas.")
            }
            Command.UNMUTE -> {
                Speaker.setEnabled(context, true)
                reply("Voz ligada.")
            }
            Command.REPEAT -> reply(lastAnswer ?: "Ainda não respondi nada.")
            Command.SLOWER, Command.FASTER -> {
                Speaker.changeRate(context, command == Command.SLOWER)
                reply(lastAnswer ?: if (command == Command.SLOWER) "Combinado, vou falar mais devagar." else "Combinado, vou falar mais rápido.")
            }
            Command.WRITE -> {
                stopVoice()
                input.requestFocus()
                context.getSystemService(InputMethodManager::class.java).showSoftInput(input, 0)
                answer.text = "Pode escrever."
            }
            else -> return false
        }
        return true
    }

    private fun reply(text: String) {
        answer.text = text
        Speaker.speak(context, text) { main.postDelayed(autoHide, ANSWER_MS) }
    }

    private fun send() {
        if (previewOnly) return
        main.removeCallbacks(autoSend)
        val text = input.text.toString().trim()
        if (text.isEmpty()) return
        val id = ++requests
        busy = true
        listener.stop()
        Speaker.stop()
        input.setText("")
        context.getSystemService(InputMethodManager::class.java).hideSoftInputFromWindow(input.windowToken, 0)
        hide()  // sai da frente antes de o agente ler a tela
        val app = context.applicationContext
        thread(name = "lmphone-pedido") {
            stopPrevious()
            val result = Brain.send(app, text)
            if (id != requests) return@thread  // um pedido mais novo tomou o lugar deste
            busy = false
            // Com o modo contínuo ligado na faixa durante o pedido, a resposta aparece nela, e não no painel.
            main.post { if (!(Live.continuous && AgentService.showAnswer(result.message))) AssistService.answer(app, result.message) }
        }
    }

    /** Liga o live mode contínuo no PC: o painel sai, e a faixa aparece como um círculo, já ouvindo. */
    private fun startLive() {
        if (previewOnly) return
        main.removeCallbacks(autoHide)
        stopVoice()
        Speaker.stop()
        hide()
        val app = context.applicationContext
        thread(name = "lmphone-live") {
            stopPrevious()
            val result = Brain.live(app, "iniciar")
            if (!result.ok) main.post { AssistService.answer(app, result.message) }
        }
    }

    /**
     * Na loja, a resposta do assistente pode ser denunciada sem sair do app (política "AI-Generated Content" da Play,
     * docs/plano-play-store.md fase 4). O primeiro toque mostra o que vai ser enviado; o segundo envia. Vai só esta
     * resposta, como a pessoa a leu, ao servidor do app.
     */
    private fun offerReport() {
        reportArmed = false
        report.visibility = if (Flavor.ACTS) View.GONE else View.VISIBLE
        report.text = "Denunciar esta resposta"
    }

    private fun reportAnswer() {
        val said = lastAnswer ?: return
        main.removeCallbacks(autoHide)
        if (!reportArmed) {
            reportArmed = true
            report.text = "Toque de novo para enviar esta resposta à equipe do Guia, para análise."
            return
        }
        report.text = "Enviando…"
        val app = context.applicationContext
        thread(name = "lmphone-denuncia") {
            val sent = Flavor.report(app, said)
            main.post { report.text = if (sent) "Obrigado. A equipe do Guia vai olhar esta resposta." else "Não consegui enviar agora. Tente de novo mais tarde." }
        }
    }

    companion object {
        const val ANSWER = "resposta"
        const val NOTICE = "aviso"
        private const val AUTO_SEND_MS = 1500L
        private const val ANSWER_MS = 7000L  // o painel com a resposta fecha este tempo depois da leitura
        @Volatile private var busy = false  // um pedido do painel em curso
        @Volatile private var requests = 0  // o último pedido mandado pelo painel; a resposta de um anterior é ignorada

        /**
         * Um pedido em curso (o anterior, que o dono talvez já tenha encerrado no X) para antes do novo: a pausa e a
         * interrupção da faixa valem na hora, e o cérebro termina o anterior na volta seguinte. Espera até 30 s.
         */
        private fun stopPrevious() {
            if (Brain.running.get() == 0) return
            Live.stopped = true
            Live.event("fechou")
            val limit = System.currentTimeMillis() + 30_000
            while (Brain.running.get() > 0 && System.currentTimeMillis() < limit) Thread.sleep(100)
            Live.stopped = false
        }
        @Volatile private var lastAnswer: String? = null  // para "Alexa, repete"
        @Volatile var current: AssistSession? = null  // o painel aberto
            private set
    }
}
