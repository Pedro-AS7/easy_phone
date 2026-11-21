package dev.pedro.lmphone

import android.accessibilityservice.AccessibilityService
import android.annotation.SuppressLint
import android.app.Dialog
import android.content.Intent
import android.content.Context
import android.graphics.Color
import android.graphics.Bitmap
import android.graphics.Rect
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.text.TextWatcher
import android.text.Editable
import android.util.Log
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.Window
import android.view.WindowManager
import android.view.accessibility.AccessibilityWindowInfo
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import kotlin.math.abs

/**
 * A faixa flutuante do live mode, como a do Bixby: o que o agente está fazendo (texto inteiro, rolando), a vez do dono,
 * pausar, mudar de lado, minimizar, fechar, e um campo para falar ou escrever com o agente. Quando o agente pergunta, a
 * pergunta e as opções aparecem; a pergunta é lida em voz alta e a faixa ouve a resposta (Voice.kt, só o reconhecedor
 * do aparelho), com o teclado como alternativa. Pergunta de senha ou código vai direto para o campo, escondido.
 *
 * Minimizada, a faixa vira um círculo que dá para arrastar; um toque nele a abre. Ela começa assim (pedido do Pedro,
 * 2026-10-24); uma pergunta do agente e a vez do dono a abrem sozinhas. O X tira a faixa da tela e encerra a tarefa.
 *
 * Modo contínuo (o botão ∞ da faixa, o do painel do assistente, ou o PC avisando): o microfone fica aberto e cada fala
 * é um pedido novo da mesma conversa (Brain.send com "continuo"), até o dono dizer "finalizar" ou tocar no X. Uma fala
 * no meio de um pedido vira o seguinte ("novo_pedido": o PC encerra o que estava em curso); "pausa" e "continua" valem
 * como os botões. O microfone fecha enquanto o agente fala, para não ouvir a si mesmo. A resposta de cada pedido
 * aparece na faixa, é lida e, 7 s depois, a faixa volta a ser o círculo.
 *
 * São janelas do próprio serviço de acessibilidade (TYPE_ACCESSIBILITY_OVERLAY, montadas por Dialog para ter o desfoque
 * do Android 12+): não precisam da permissão de sobreposição e ficam fora da leitura da tela (Screen lê só a janela
 * ativa, e o campo de digitação do agente ignora as sobreposições). Elas somem no fim da tarefa, com o serviço.
 *
 * Os botões também valem falados (Commands.kt): "Alexa, pausa", "Alexa, para" (encerra a tarefa, como o X), "Alexa,
 * live mode", "Alexa, deixa que eu faço"... A palavra de ativação abre a faixa e ela ouve (`wake`); no modo contínuo,
 * que já ouve tudo, basta o comando. Uma fala que não é comando vai ao agente como instrução, como antes.
 *
 * O agente nunca toca nelas: antes de um gesto que cairia na faixa ou no círculo, eles mudam de lado, e um toque no
 * campo logo depois de um gesto do agente é ignorado. A faixa fica sem foco (o teclado vai para o app de baixo) até o
 * dono tocar no campo; o ícone de esconder o teclado e o Voltar fecham a escrita sem mandar nada. Enquanto o dono fala
 * ou escreve, o agente espera (Live.typing).
 *
 * Todo botão da faixa e do círculo ignora um toque durante um gesto do agente e até `AGENT_GUARD_MS` depois dele
 * (`owner`): em 2026-10-22 um toque do agente no Instagram caiu no X e encerrou a tarefa, mesmo com a faixa sem receber
 * toques durante o gesto. O X ainda pede um segundo toque em 3 s para encerrar.
 *
 * A alça superior move a janela e guarda sua posição. Um toque fora pausa e passa a vez ao dono; Continuar devolve
 * o controle ao agente. O destaque é uma moldura no controle em que ele vai tocar (no guia) ou em que o dono deve tocar.
 */
class Overlay(private val service: AccessibilityService) {
    internal var previewOnly = false
    internal fun previewBitmap(): Bitmap? {
        if (!previewOnly || input.length() != 0 || questionId != null || !status.text.startsWith("Texto fictício")) return null
        val view = dialog?.window?.decorView ?: return null
        return Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888).also { view.draw(android.graphics.Canvas(it)) }
    }
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var dialog: Dialog? = null  // a faixa
    private var bubble: Dialog? = null  // a faixa minimizada
    private var frame: Dialog? = null  // o destaque
    private var hint: Dialog? = null  // o gesto animado (puxar o painel, rolar)
    private lateinit var panel: LinearLayout
    private lateinit var status: TextView
    private lateinit var heading: TextView
    private lateinit var statusScroll: CappedScroll
    private lateinit var question: TextView
    private lateinit var questionScroll: CappedScroll
    private lateinit var options: LinearLayout
    private lateinit var optionsScroll: HorizontalScrollView
    private lateinit var pause: ImageView
    private lateinit var move: ImageView
    private lateinit var voice: ImageView
    private lateinit var input: EditText
    private lateinit var ring: GradientDrawable
    private lateinit var bubbleIcon: ImageView
    private lateinit var liveButton: ImageView
    private lateinit var sendButton: ImageView
    private lateinit var actionButton: TextView  // só guia: o botão que a pessoa toca para abrir um app ou uma página
    private lateinit var rerouting: LinearLayout  // "Recalculando o caminho…": a pessoa saiu do caminho e o agente acha a volta
    private var floating: FloatingPanel? = null
    private var glass: FrostedGlass? = null
    private var refreshHeader: () -> Unit = {}
    private val refreshGlass = Runnable { captureGlass() }
    private var writing = false
    private var textMode = false
    private val voiceDraft = VoiceDraft()
    private var listening = false
    private var passive = false  // ouvindo no modo contínuo, sem o dono ter pedido: o agente segue agindo
    private var minimized = false
    private var questionId: String? = null
    private var secret = false
    private var closeArmed = 0L  // quando o X foi tocado a primeira vez
    private var requestId = 0  // o último pedido mandado pela faixa; a resposta de um anterior é ignorada
    private lateinit var closeButton: ImageView
    private val autoSend = Runnable { send() }
    private val relisten = Runnable { loop() }
    private val collapse = Runnable { if (questionId == null && !writing) minimize() }
    private val listener by lazy {
        Listener(service,
            onPartial = { text -> if (!textMode) { input.setText(voiceDraft.join(text)); input.setSelection(input.length()) } },
            onFinal = { text -> heard(text) },
            onProblem = { message ->
                stopListening()
                status.text = message
                if (Live.continuous) main.postDelayed(relisten, RETRY_MS)
            },
            onSilence = { silence() })
    }

    private fun dp(value: Int) = Ui.dp(service, value)

    /** A faixa está na tela (aberta ou como o círculo). */
    val shown get() = dialog != null

    /** Só geometria e estado do vidro, usados pela conferência local; nunca texto ou pixels. */
    internal fun geometry(): JSONObject {
        val attributes = dialog?.window?.attributes
        return JSONObject().put("x", attributes?.x).put("y", attributes?.y).put("width", panel.width)
            .put("height", panel.height).put("glass", glass?.hasSource == true).put("native", glass?.native == true)
            .put("blur_enabled", glass?.enabled)
            .put("alpha", attributes?.alpha)
            .put("minimized", minimized).put("menu_in_handle", Ui.headerMenu(service))
            .put("paused", Live.paused).put("dragging", Live.dragging)
            .put("drag", floating?.diagnostics()).put("format", glass?.format)
            .put("listening", listener.listening).put("writing", writing).put("text_mode", textMode)
            .put("mic_visible", voice.visibility == View.VISIBLE).put("draft_length", input.length())
    }

    /** Um toque que pode ser do agente: durante um gesto dele ou logo depois. */
    private fun agentJustActed() = Live.gesturing || System.currentTimeMillis() - Live.agentActedAt < AGENT_GUARD_MS

    /** A ação de um botão, só se o toque for do dono. */
    private fun owner(action: () -> Unit): () -> Unit = {
        if (agentJustActed()) Log.i("lmphone", "faixa: toque ignorado (gesto do agente)") else action()
    }

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        val done = CountDownLatch(1)
        main.post { try { block() } finally { done.countDown() } }
        done.await(2, TimeUnit.SECONDS)
    }

    private fun chip(text: String, onClick: () -> Unit) = TextView(service).apply {
        this.text = text
        setTextColor(Color.WHITE)
        textSize = 14f
        gravity = Gravity.CENTER
        setPadding(dp(14), dp(8), dp(14), dp(8))
        background = Ui.rounded(service, Ui.BUTTON, 18)
        setOnClickListener { owner(onClick)() }
    }

    private fun full(top: Int) =
        LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top }

    @SuppressLint("ClickableViewAccessibility") // ACTION_OUTSIDE observa o toque em outra janela; não é um clique desta View.
    private fun overlayWindow(window: Window, touchable: Boolean = true) {
        window.setType(WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY)
        window.clearFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
        window.addFlags(WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or (if (touchable) WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH else WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE))
        // A tela não apaga enquanto a faixa ou o círculo estão na tela (pedido do Pedro, 2026-11-16): os gestos do agente
        // pela acessibilidade não contam como uso, e no guia a pessoa pode demorar. A faixa só existe durante a tarefa
        // (ou no modo contínuo); fechada, o tempo de tela volta a valer.
        if (touchable) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (touchable) window.decorView.setOnTouchListener { _, event ->
            if (event.actionMasked == MotionEvent.ACTION_OUTSIDE) { outsideTouch(); true } else false
        }
    }

    fun show() = onMain {
        if (dialog != null) return@onMain
        heading = TextView(service).apply {
            setTextColor(Color.WHITE)
            textSize = 13f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            gravity = Gravity.CENTER_VERTICAL
        }
        status = TextView(service).apply {
            text = "Entendendo o pedido…"
            setTextColor(Color.WHITE)
            textSize = 13f
        }
        statusScroll = CappedScroll(service, dp(224)).apply { addView(status); visibility = View.GONE }
        rerouting = LinearLayout(service).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(10), dp(14), dp(10))
            background = Ui.rounded(service, "#FDD663", 20)
            visibility = View.GONE
            addView(android.widget.ProgressBar(service).apply {
                isIndeterminate = true
                indeterminateTintList = android.content.res.ColorStateList.valueOf(Color.parseColor("#202124"))
            }, LinearLayout.LayoutParams(dp(26), dp(26)))
            addView(TextView(service).apply {
                text = "Recalculando o caminho…"
                setTextColor(Color.parseColor("#202124"))
                textSize = 17f
                setTypeface(typeface, Typeface.BOLD)
                setPadding(dp(12), 0, 0, 0)
            })
        }
        actionButton = TextView(service).apply {
            setTextColor(Color.WHITE)
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
            minHeight = dp(52)
            setPadding(dp(16), dp(10), dp(16), dp(10))
            background = Ui.rounded(service, "#305CDE", 26)
            visibility = View.GONE
        }
        // Mudar de lado fica no alto, com minimizar e fechar: a linha de baixo sobra para o campo.
        move = Ui.icon(service, R.drawable.ic_swap_vert, "Mudar a faixa de lado", 22, owner { moveTo(!(floating?.atTop ?: false)) })
        liveButton = Ui.icon(service, R.drawable.ic_live, "Modo contínuo",
            owner { if (Live.continuous) stopContinuous() else startContinuous(fromButton = true) })
        closeButton = Ui.icon(service, R.drawable.ic_close, "Fechar e encerrar a tarefa", 22, owner { close() })
        val actions = Ui.headerActions(service, move,
            Ui.icon(service, R.drawable.ic_minimize, "Minimizar", 22, owner { minimize() }), closeButton)
        val header = LinearLayout(service).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(heading, LinearLayout.LayoutParams(0, dp(24), 1f))
            addView(actions)
        }
        question = TextView(service).apply {
            setTextColor(Color.parseColor("#FDD663"))
            textSize = 13f
            setTypeface(typeface, Typeface.BOLD)
        }
        questionScroll = CappedScroll(service, dp(120)).apply { addView(question); visibility = View.GONE }
        options = LinearLayout(service).apply { orientation = LinearLayout.HORIZONTAL }
        optionsScroll = HorizontalScrollView(service).apply {
            isHorizontalScrollBarEnabled = false
            addView(options)
            visibility = View.GONE
        }
        pause = Ui.icon(service, R.drawable.ic_pause, "Pausar", owner { togglePause() })
        Ui.setActive(pause, true)
        voice = Ui.icon(service, R.drawable.ic_mic, "Falar", owner { microphone() })
        input = EditText(service).apply {
            hint = "Fale ou digite algo…"
            setHintTextColor(Color.parseColor("#B0FFFFFF"))
            setTextColor(Color.WHITE)
            textSize = 12f
            isSingleLine = true
            imeOptions = EditorInfo.IME_ACTION_SEND
            background = Ui.rounded(service, Ui.INPUT, 24)
            setPadding(dp(12), 0, dp(12), 0)
            layoutParams = LinearLayout.LayoutParams(0, dp(34), 1f).apply { leftMargin = dp(4) }
            isFocusable = false  // só o toque do dono abre a escrita (startWriting)
            setOnClickListener { startWriting() }
            setOnEditorActionListener { _, _, _ -> send(); true }
        }
        sendButton = Ui.icon(service, R.drawable.ic_send, "Enviar", owner { send() }).apply { visibility = View.GONE }
        val controls = LinearLayout(service).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(pause)
            addView(input)
            addView(Ui.margin(voice, 4))
            addView(Ui.margin(liveButton, 4))
            addView(Ui.margin(sendButton, 4))
        }
        val handle = Ui.handle(service)
        refreshHeader = Ui.configureHeader(service, handle, actions,
            owner { moveTo(!(floating?.atTop ?: false)) }, owner { minimize() }, owner { close() })
        panel = LinearLayout(service).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), 0, dp(10), dp(10))
            addView(handle)
            addView(header)
            addView(statusScroll, full(dp(6)))
            addView(rerouting, full(dp(10)))
            addView(actionButton, full(dp(10)))
            addView(questionScroll, full(dp(8)))
            addView(optionsScroll, full(dp(6)))
            addView(controls, full(dp(8)))
            // Mudou de tamanho ou de lugar (um texto maior, a faixa aberta): confere se não cobriu o destaque.
            addOnLayoutChangeListener { view, _, _, _, _, _, _, _, _ -> if (highlightBox != null) view.post { keepClear() } }
        }
        dialog = Dialog(service, R.style.Theme_LmPhone_Floating).apply {
            requestWindowFeature(Window.FEATURE_NO_TITLE)
            setContentView(panel)
            setCancelable(false)
            setOnKeyListener { _, keyCode, event ->
                // Voltar durante a escrita só fecha a escrita.
                if (keyCode == KeyEvent.KEYCODE_BACK && writing) {
                    if (event.action == KeyEvent.ACTION_UP) stopWriting()
                    true
                } else false
            }
            window?.let { window ->
                overlayWindow(window)
                // Fundo translúcido com desfoque do que está atrás; sem desfoque no aparelho, um fundo mais fechado.
                glass = Ui.glass(window)
                floating = FloatingPanel(window, panel, handle, allowed = { !agentJustActed() }, onDrag = {
                    Live.dragging = it
                    glass?.setDragging(it)
                    main.removeCallbacks(collapse)
                }, onMinimizeGesture = owner { minimize() }, onCloseGesture = owner { close(confirm = false) })
                floating?.update()
            }
            create()  // montada, mas a faixa começa como o círculo
        }
        status.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { updateHeading() }
            override fun afterTextChanged(s: Editable?) {}
        })
        updateHeading()
        input.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                val text = !s.isNullOrBlank()
                sendButton.visibility = if (text) View.VISIBLE else View.GONE
                liveButton.visibility = if (text || writing) View.GONE else View.VISIBLE
            }
            override fun afterTextChanged(s: Editable?) {}
        })
        buildBubble()
        minimized = true
        bubble?.show()
        refreshRing()
        if (Live.continuous) startContinuous()
    }

    /** O círculo da faixa minimizada: arrasta com o dedo; um toque abre a faixa. */
    @SuppressLint("ClickableViewAccessibility")
    private fun buildBubble() {
        ring = GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(Color.parseColor("#E6202124"))
            setStroke(dp(3), Color.parseColor("#305CDE"))
        }
        bubbleIcon = ImageView(service).apply { setImageResource(R.drawable.ic_assistant) }
        val view = FrameLayout(service).apply {
            background = ring
            contentDescription = "Abrir a faixa do lm_phone"
            addView(bubbleIcon, FrameLayout.LayoutParams(dp(28), dp(28), Gravity.CENTER))
        }
        val slop = ViewConfiguration.get(service).scaledTouchSlop
        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var dragged = false
        view.setOnTouchListener { _, event ->
            val window = bubble?.window ?: return@setOnTouchListener false
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX; downY = event.rawY
                    startX = window.attributes.x; startY = window.attributes.y
                    dragged = false
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX
                    val dy = event.rawY - downY
                    if (dragged || abs(dx) > slop || abs(dy) > slop) {
                        dragged = true
                        window.attributes = window.attributes.apply { x = startX + dx.toInt(); y = startY + dy.toInt() }
                    }
                }
                MotionEvent.ACTION_UP -> if (!dragged && !agentJustActed()) expand()
            }
            true
        }
        bubble = Dialog(service).apply {
            requestWindowFeature(Window.FEATURE_NO_TITLE)
            setContentView(view)
            setCancelable(false)
            window?.let { window ->
                overlayWindow(window)
                window.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                window.setLayout(dp(56), dp(56))
                window.setGravity(Gravity.TOP or Gravity.START)
                val metrics = service.resources.displayMetrics
                window.attributes = window.attributes.apply { x = metrics.widthPixels - dp(68); y = metrics.heightPixels / 2 }
            }
        }
    }

    fun hide() = onMain {
        hint?.dismiss()
        hint = null
        main.removeCallbacks(refreshGlass)
        glass?.clear()
        glass = null
        floating?.cancelDrag()
        floating = null
        main.removeCallbacks(autoSend)
        main.removeCallbacks(relisten)
        main.removeCallbacks(collapse)
        if (listening) listener.stop()
        listening = false
        passive = false
        frame?.dismiss()
        frame = null
        bubble?.dismiss()
        bubble = null
        dialog?.dismiss()
        dialog = null
    }

    private fun minimize() {
        main.removeCallbacks(refreshGlass)
        glass?.clear()
        main.removeCallbacks(collapse)
        if (writing) stopWriting()
        if (listening && !passive) stopListening()  // no modo contínuo o círculo continua ouvindo
        minimized = true
        dialog?.hide()
        bubble?.show()
        refreshRing()
        Log.i("lmphone", "faixa: minimizada")
    }

    /** Abre a faixa minimizada (a vez do dono, no guia: ele lê o que fazer). */
    fun open() = onMain { expand() }

    private fun expand() {
        if (!minimized) return
        minimized = false
        refreshHeader()
        bubble?.hide()
        glass?.beginOpening()
        dialog?.show()
        floating?.update()
        panel.post { keepClear() }  // a faixa abriu: não pode ficar em cima do destaque
        main.removeCallbacks(refreshGlass)
        main.post(refreshGlass)
        Log.i("lmphone", "faixa: aberta")
    }

    private fun updateHeading() {
        val text = status.text.toString()
        val body = text.length > 60 || '\n' in text
        heading.text = when {
            Live.paused -> "Pausado"
            writing -> "Escrevendo…"
            listening -> "Ouvindo…"
            !body -> text
            else -> "Assistente"
        }
        statusScroll.visibility = if (body) View.VISIBLE else View.GONE
    }

    /** Só a janela abaixo, sem a própria faixa: evita realimentar o vidro a cada atualização. */
    private fun captureGlass() {
        val current = glass ?: return
        if (minimized || dialog?.isShowing != true) return
        if (!current.enabled) return
        main.removeCallbacks(refreshGlass)
        main.postDelayed(refreshGlass, 600)
        if (current.native || Live.dragging) return
        val target = service.windows.firstOrNull { it.type == AccessibilityWindowInfo.TYPE_APPLICATION && it.isActive }
            ?: service.windows.firstOrNull { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
        if (target == null || target.root?.packageName?.toString() in Live.banks) { current.unavailable(); return }
        val bounds = Rect().also { target.getBoundsInScreen(it) }
        try { if (!Flavor.screenshot(service, target.id, object : AccessibilityService.TakeScreenshotCallback {
            override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                val buffer = result.hardwareBuffer
                val bitmap = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace)
                if (glass !== current || minimized || bitmap == null) {
                    buffer.close()
                    if (glass === current && !minimized && bitmap == null) current.unavailable()
                    return
                }
                current.source(bitmap, bounds) { bitmap.recycle(); buffer.close() }
            }
            override fun onFailure(errorCode: Int) { if (glass === current) current.unavailable() }
        })) current.unavailable() } catch (_: SecurityException) { current.unavailable() }
    }

    /**
     * Só guia (a variante `loja`): o botão que a pessoa toca para abrir um app ou uma página das Configurações. Quem abre
     * é o app, a pedido dela; o toque conta como o passo dela (`toque_tela`). null tira o botão.
     */
    fun offer(button: JSONObject?) = onMain {
        if (dialog == null) return@onMain
        val intent = button?.let { intentFor(it) }
        if (button == null || intent == null) {
            currentOffer = null
            actionButton.visibility = View.GONE
            return@onMain
        }
        val text = button.optString("texto")
        val offered = Any()
        currentOffer = offered
        buttonAt = null  // uma oferta nova vai ao registro mesmo no mesmo lugar (2026-11-18: o segundo botão não foi)
        actionButton.text = text
        actionButton.contentDescription = text
        actionButton.setOnClickListener {
            actionButton.visibility = View.GONE
            Speaker.stop()
            Live.event("toque_tela")
            Live.event("botao_tocado", JSONObject().put("texto", text))
            // Uma página das Configurações abre numa tarefa nova e limpa: com só NEW_TASK, se a tarefa das Configurações
            // aberta antes tinha começado pela mesma página, o Android só a trazia para a frente, com outra página por
            // cima (2026-11-18: «Abrir as Configurações» de Sons mostrou o Não perturbar, 4 vezes).
            val flags = Intent.FLAG_ACTIVITY_NEW_TASK or if (button.has("acao")) Intent.FLAG_ACTIVITY_CLEAR_TASK else 0
            try {
                service.startActivity(intent.addFlags(flags))
            } catch (e: Exception) {
                Log.w("lmphone", "o botão da faixa não abriu", e)
            }
            // O agente tira o botão quando a página abre; se ele ainda é o mesmo depois disso, ela não abriu, e o botão
            // volta para a pessoa tocar de novo.
            main.postDelayed({
                if (dialog != null && currentOffer === offered) actionButton.visibility = View.VISIBLE
            }, BUTTON_AGAIN_MS)
        }
        actionButton.visibility = View.VISIBLE
        expand()
        // Onde ele ficou na tela, depois de a faixa abrir e se acomodar (sair de cima de um destaque): o registro do live
        // mode e a pessoa simulada (tests/pessoa_loja.py). Vai de novo se ele mudou de lugar.
        reportButton(0)
    }

    private var buttonAt: List<Int>? = null
    private var currentOffer: Any? = null  // o botão oferecido agora (cada oferta é um objeto novo)

    private fun reportButton(round: Int) {
        main.postDelayed({
            if (dialog == null || actionButton.visibility != View.VISIBLE) return@postDelayed
            val at = IntArray(2).also { actionButton.getLocationOnScreen(it) }
            val box = listOf(at[0], at[1], at[0] + actionButton.width, at[1] + actionButton.height)
            if (box != buttonAt) {
                buttonAt = box
                Live.event("botao_limites", JSONObject().put("limites", JSONArray(box)))
            }
            if (round < 4) reportButton(round + 1)
        }, if (round == 0) 150L else 500L)
    }

    /**
     * A pessoa saiu do caminho e o agente acha a volta: uma faixa amarela com "Recalculando o caminho…" e o indicador
     * girando, como o GPS, até a instrução nova (pedido do Pedro, 2026-11-17). O destaque e o botão já saíram.
     */
    fun reroute(on: Boolean) = onMain {
        if (dialog == null) return@onMain
        rerouting.visibility = if (on) View.VISIBLE else View.GONE
        if (on) {
            actionButton.visibility = View.GONE
            expand()
        }
    }

    private fun intentFor(button: JSONObject): Intent? = when {
        button.has("acao") -> Intent(button.getString("acao"))
        button.has("pacote") -> service.packageManager.getLaunchIntentForPackage(button.getString("pacote"))
        else -> null
    }

    /**
     * O anel do círculo diz o estado: azul trabalhando, amarelo pausado ou esperando o dono, verde na vez dele,
     * vermelho ouvindo (modo contínuo, com o microfone no lugar do ícone do assistente).
     */
    private fun refreshRing() {
        if (!::ring.isInitialized) return
        val color = when {
            questionId != null -> "#FDD663"
            Live.paused -> "#FDD663"
            Live.owner -> "#81C995"
            Live.continuous && listening && !Live.requesting -> "#F28B82"
            else -> "#305CDE"
        }
        ring.setStroke(dp(3), Color.parseColor(color))
        bubbleIcon.setImageResource(if (Live.continuous && listening && !Live.requesting) R.drawable.ic_mic else R.drawable.ic_assistant)
    }

    /**
     * O X: tira a faixa da tela e encerra a tarefa (as ações do agente passam a ser recusadas na hora). O primeiro toque
     * só arma: é preciso tocar de novo em até 3 s.
     */
    private fun close(confirm: Boolean = true) {
        val now = System.currentTimeMillis()
        if (confirm && now - closeArmed > CLOSE_CONFIRM_MS) {
            closeArmed = now
            Ui.setActive(closeButton, true)
            status.text = if (Ui.headerMenu(service)) "Escolha Fechar novamente para encerrar a tarefa."
                else "Toque de novo no X para encerrar a tarefa."
            main.postDelayed({ if (dialog != null) Ui.setActive(closeButton, false) }, CLOSE_CONFIRM_MS)
            return
        }
        if (Live.continuous) return endContinuous()
        Live.stopped = true
        Live.event("fechou")
        Speaker.stop()
        hide()
        release()
        Log.i("lmphone", "faixa: fechada pelo dono")
    }

    companion object {
        private const val AGENT_GUARD_MS = 1500L  // toque na faixa até este tempo depois de um gesto do agente: ignorado
        private const val CLOSE_CONFIRM_MS = 3000L  // tempo para o segundo toque no X
        private const val ANSWER_MS = 7000L  // a resposta fica na faixa este tempo depois de lida (pedido do Pedro)
        private const val RELISTEN_MS = 250L  // pausa antes de o microfone voltar a ouvir no modo contínuo
        private const val RETRY_MS = 2000L  // depois de um erro do reconhecedor
        private const val BUTTON_AGAIN_MS = 5000L  // o botão da faixa tocado volta se o agente ainda o oferece
        // Comandos que valem mesmo com uma pergunta em aberto (os outros, nela, são a resposta).
        private val URGENT = setOf(Command.STOP, Command.FINISH)
    }

    fun status(text: String) = onMain {
        if (dialog == null || Live.paused || questionId != null || (listening && !passive)) return@onMain
        status.text = text
        statusScroll.scrollTo(0, 0)
    }

    /** A vez do dono (o PC passou ou devolveu, pela instrução "deixa que eu faço" / "faz você"). */
    fun turn(owner: Boolean) = onMain { setOwner(owner, fromButton = false) }

    private fun setOwner(owner: Boolean, fromButton: Boolean) {
        if (dialog == null) return
        Live.owner = owner
        if (fromButton) Live.event(if (owner) "eu_faco" else "faz_voce")
        refreshPause()
        if (fromButton) status.text = if (owner) "Sua vez: eu mostro cada passo e acompanho." else "Deixa comigo."
        refreshRing()
    }

    /** Uma moldura em volta de `box` (coordenadas da tela), ou nenhuma. Não recebe toques: o dono e o agente tocam através. */
    fun highlight(box: Rect?) = onMain {
        frame?.dismiss()
        frame = null
        restorePanel?.invoke()
        restorePanel = null
        restoreBubble?.invoke()
        restoreBubble = null
        highlightBox = box
        if (box == null || dialog == null) return@onMain
        keepClear()
        val view = object : View(service) {
            private val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                style = android.graphics.Paint.Style.STROKE
                strokeWidth = dp(4).toFloat()
                color = Color.parseColor("#FDD663")
            }
            override fun onDraw(canvas: android.graphics.Canvas) {
                val at = IntArray(2).also { getLocationOnScreen(it) }
                val pad = dp(6).toFloat()
                canvas.drawRoundRect(box.left - at[0] - pad, box.top - at[1] - pad, box.right - at[0] + pad,
                    box.bottom - at[1] + pad, dp(12).toFloat(), dp(12).toFloat(), paint)
            }
        }
        frame = Dialog(service).apply {
            requestWindowFeature(Window.FEATURE_NO_TITLE)
            setContentView(view)
            window?.let { window ->
                overlayWindow(window, touchable = false)
                window.addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS)
                window.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            show()
        }
    }

    /**
     * Mostra o gesto que o dono deve fazer, animado e sem receber toques (docs/plano-tutor.md, fase 2): "puxar" é um
     * dedo descendo do alto da tela (o painel rápido); "rolar", um dedo subindo no meio dela. null tira.
     */
    fun gesture(kind: String?) = onMain {
        hint?.dismiss()
        hint = null
        if (kind == null || dialog == null) return@onMain
        val metrics = service.resources.displayMetrics
        val pull = kind.startsWith("puxar")
        // "puxar_direita": os painéis separados da One UI 7 em diante, em que os atalhos descem pelo lado direito do alto.
        val x = if (kind == "puxar_direita") metrics.widthPixels * 0.8f else metrics.widthPixels / 2f
        val (from, to) = if (pull) dp(8).toFloat() to metrics.heightPixels * 0.35f
                         else metrics.heightPixels * 0.7f to metrics.heightPixels * 0.35f
        val view = object : View(service) {
            private val finger = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.parseColor("#FDD663")
            }
            private val trail = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
                style = android.graphics.Paint.Style.STROKE
                strokeWidth = dp(6).toFloat()
                strokeCap = android.graphics.Paint.Cap.ROUND
                color = Color.parseColor("#80FDD663")
            }
            var progress = 0f
            override fun onDraw(canvas: android.graphics.Canvas) {
                val at = IntArray(2).also { getLocationOnScreen(it) }
                val y = from + (to - from) * progress
                canvas.drawLine(x - at[0], from - at[1], x - at[0], y - at[1], trail)
                finger.alpha = (255 * (1f - progress * 0.6f)).toInt()
                canvas.drawCircle(x - at[0], y - at[1], dp(22).toFloat(), finger)
            }
        }
        val animator = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1400
            repeatCount = android.animation.ValueAnimator.INFINITE
            startDelay = 300
            addUpdateListener { view.progress = it.animatedValue as Float; view.invalidate() }
        }
        hint = Dialog(service).apply {
            requestWindowFeature(Window.FEATURE_NO_TITLE)
            setContentView(view)
            window?.let { window ->
                overlayWindow(window, touchable = false)
                window.addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS)
                window.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
                window.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            }
            setOnDismissListener { animator.cancel() }
            show()
        }
        animator.start()
    }

    private var highlightBox: Rect? = null  // o destaque na tela agora (a faixa não pode ficar em cima dele)
    private var restorePanel: (() -> Unit)? = null  // a posição da faixa de antes de ela sair de cima do destaque
    private var restoreBubble: (() -> Unit)? = null  // a do círculo

    /**
     * A faixa (ou o círculo) sai de cima do destaque, com uma folga em volta (pedido do Pedro, 2026-11-16: o destaque
     * ficava embaixo da faixa, e a pessoa não via onde tocar). Volta à posição de antes quando o destaque sai. Conferido
     * de novo quando a faixa abre ou muda de tamanho (2026-11-16: o destaque chegava com a faixa minimizada, e ela abria
     * logo depois, na posição guardada, em cima do botão).
     */
    private fun keepClear() {
        val box = highlightBox ?: return
        if (writing || dialog == null) return
        val around = Rect(box).apply { inset(-dp(16), -dp(16)) }
        if (!minimized) {
            if (panel.width == 0) return  // ainda sem medida: o ouvinte de layout confere quando ela for desenhada
            if (Rect.intersects(bounds(panel), around)) {
                val restore = floating?.avoid(around)
                if (restorePanel == null) restorePanel = restore
                // Nenhum canto livra o destaque (a faixa alta, com a fala longa, e o destaque no meio da tela): ela vira o
                // círculo enquanto ele está na tela, e o círculo sai de cima dele (2026-11-18, no celular: o toque no
                // destaque da barra de Notificações caiu no X da faixa, e o guia acabou). Volta aberta quando ele sai.
                panel.post {
                    if (highlightBox == box && !minimized && dialog != null && Rect.intersects(bounds(panel), around)) {
                        val corner = restorePanel
                        minimize()
                        restorePanel = { corner?.invoke(); expand() }
                        keepClear()
                    }
                }
            }
            return
        }
        if (restoreBubble != null) return
        val window = bubble?.window ?: return
        val circle = bounds(window.decorView)
        if (!Rect.intersects(circle, around)) return
        val metrics = service.resources.displayMetrics
        val before = window.attributes.x to window.attributes.y
        val y = if (around.top > metrics.heightPixels / 2) dp(96) else metrics.heightPixels - dp(200)
        val x = if (circle.centerX() > metrics.widthPixels / 2) dp(12) else metrics.widthPixels - dp(68)
        window.attributes = window.attributes.apply { this.x = x; this.y = if (Rect.intersects(Rect(x, circle.top, x + dp(56), circle.bottom), around)) y else this.y }
        restoreBubble = { bubble?.window?.let { it.attributes = it.attributes.apply { this.x = before.first; this.y = before.second } } }
    }

    /**
     * Um gesto do agente em (x, y): se ele cairia na faixa ou no círculo, eles mudam de lado antes; durante o gesto não
     * recebem toques. Sem isso, um toque do agente no pé da tela abria a escrita.
     */
    fun <T> passThrough(x: Int?, y: Int?, block: () -> T): T {
        var restorePanel: (() -> Unit)? = null
        onMain {
            if (x != null && y != null && !writing) {
                if (!minimized && dialog != null && bounds(panel).contains(x, y)) restorePanel = floating?.avoid(x, y)
                if (minimized) bubble?.window?.let { window ->
                    val box = bounds(window.decorView)
                    if (box.contains(x, y)) {
                        val width = service.resources.displayMetrics.widthPixels
                        window.attributes = window.attributes.apply { this.x = if (box.centerX() > width / 2) dp(12) else width - dp(68) }
                    }
                }
            }
            dialog?.window?.addFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)
            bubble?.window?.addFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)
        }
        Thread.sleep(60)  // o sistema aplica a mudança da janela um instante depois
        try {
            return block()
        } finally {
            onMain {
                dialog?.window?.clearFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)
                bubble?.window?.clearFlags(WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)
                if (dialog != null) restorePanel?.invoke()
            }
        }
    }

    private fun bounds(view: View): Rect {
        val at = IntArray(2)
        view.getLocationOnScreen(at)
        return Rect(at[0], at[1], at[0] + view.width, at[1] + view.height)
    }

    private fun moveTo(top: Boolean) {
        floating?.moveTo(top)
    }

    /**
     * Uma pergunta do agente (escrita pelo provedor e desmascarada no PC): o texto, as opções em botões, e a resposta
     * falada (a pergunta é lida e a faixa ouve) ou escrita. Com `isSecret` (senha, código), vai direto para o campo,
     * escondido: nem é dita nem ouvida. A faixa abre sozinha se estava minimizada. `id` nulo tira a pergunta.
     */
    fun ask(id: String?, text: String, choices: List<String>, isSecret: Boolean) = onMain {
        if (dialog == null) return@onMain
        questionId = id
        secret = id != null && isSecret
        options.removeAllViews()
        if (id == null) {
            questionScroll.visibility = View.GONE
            optionsScroll.visibility = View.GONE
            input.inputType = InputType.TYPE_CLASS_TEXT
            input.hint = "Fale ou escreva…"
            refreshRing()
            return@onMain
        }
        expand()
        main.removeCallbacks(collapse)
        if (listening && passive) {
            // O modo contínuo estava ouvindo à toa: a pergunta é lida antes, e a resposta é ouvida depois.
            listener.stop()
            listening = false
            passive = false
            resetVoice()
        }
        question.text = text
        questionScroll.visibility = View.VISIBLE
        questionScroll.scrollTo(0, 0)
        choices.forEach { choice ->
            options.addView(chip(choice) { answer(choice) },
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { rightMargin = dp(6) })
        }
        optionsScroll.visibility = if (choices.isEmpty()) View.GONE else View.VISIBLE
        input.inputType = if (secret) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT
        input.hint = if (secret) "Digite aqui (fica só no celular e no PC)" else "Fale ou escreva a resposta…"
        status.text = "Preciso de você"
        refreshRing()
        if (secret) {
            startWriting(force = true)
        } else {
            // A pergunta é lida e, quando a leitura acaba, a faixa ouve a resposta.
            Speaker.speak(service, text) { if (questionId == id && !writing) listen() }
        }
    }

    /** A resposta à pergunta em aberto (um botão, a voz ou o campo). */
    private fun answer(text: String) {
        val id = questionId ?: return
        Live.event("resposta", JSONObject().put("id", id).put("texto", text).put("segredo", secret))
        val wasSecret = secret
        questionId = null
        ask(null, "", emptyList(), false)
        status.text = if (wasSecret) "Recebi a resposta." else "Recebi: $text"
        main.postDelayed(relisten, RELISTEN_MS)
    }

    private fun togglePause() {
        val resume = Live.paused || Live.owner
        Live.paused = !resume
        if (resume && Live.owner) setOwner(false, fromButton = true)
        Live.event(if (Live.paused) "pausa" else "retomada")
        refreshPause()
        val spoken = if (Wake.WORD.isEmpty()) "" else " ou diga «${Wake.WORD}, continua»"
        status.text = if (Live.paused) "Pausado. Toque em continuar$spoken." else "Continuando…"
        refreshRing()
    }

    private fun refreshPause() {
        val waiting = Live.paused || Live.owner
        pause.setImageResource(if (waiting) R.drawable.ic_play else R.drawable.ic_pause)
        pause.contentDescription = if (waiting) "Continuar" else "Pausar"
        Ui.setActive(pause, true)
    }

    /**
     * ACTION_OUTSIDE também cobre áreas vazias: não depende de o app emitir um clique acessível. Na vez do dono, ou com
     * um destaque para ele tocar (o guia), o toque dele é o passo que o agente espera, não um pedido de pausa (até
     * 2026-11-16 pausava, e o guia em que a pessoa toca parava no primeiro passo).
     */
    private fun outsideTouch() {
        if (dialog == null || Live.stopped || Live.dragging || writing || agentJustActed()) return
        val idle = Live.continuous && !Live.requesting && Brain.running.get() == 0  // modo contínuo, entre um pedido e outro
        // Com a tarefa em curso, a faixa minimizada volta à forma aberta quando a pessoa toca na tela (pedido do Pedro,
        // 2026-11-16), para ela ver o que o agente diz. Entre os pedidos do modo contínuo, não: abriria a cada uso.
        if (minimized && !idle) expand()
        if (Live.ownerTouchExpected()) {
            Live.event("toque_tela")  // o passo do dono: o PC sabe que foi ele quem mexeu na tela (o guia conta o passo)
            Speaker.stop()  // ela já está fazendo o passo: a explicação para (pedido do Pedro, 2026-11-17)
            return
        }
        // A faixa aparece com a acessibilidade, uns segundos antes de o cérebro anunciar o pedido; e no guia em que a
        // pessoa toca, ela mexe na tela o tempo todo. Nos dois casos, um toque não pausa (pedido do Pedro, 2026-11-16: um
        // toque no começo pausou o guia da letra, e ele teve de tocar em Continuar).
        if (!Live.task || Live.guide && !Live.guideAgent) return
        if (Live.paused || idle) return
        Live.paused = true  // bloqueia novas ações no aparelho antes de o cérebro ler os eventos
        setOwner(true, fromButton = true)
        Live.event("pausa")
        status.text = "Pausado — você está no controle. Toque em continuar para eu retomar."
        main.removeCallbacks(collapse)
        refreshPause()
        refreshRing()
    }

    private val agentKeyboard get() = Flavor.agentKeyboard(service)

    /**
     * Ouve o dono (uma resposta, se há pergunta; senão, uma instrução). Enquanto ele fala, o agente espera. `quiet`: o
     * modo contínuo ouvindo sem o dono ter pedido; o agente segue agindo, e a faixa não muda de texto.
     */
    private fun listen(quiet: Boolean = false, keepText: Boolean = false) {
        if (writing || textMode || listening || dialog == null) return
        if (!quiet) Speaker.stop()
        main.removeCallbacks(autoSend)
        main.removeCallbacks(relisten)
        listening = true
        passive = quiet
        voiceDraft.begin(if (keepText) input.text.toString() else "")
        if (!quiet) {
            Live.typing = true
            if (!keepText) input.setText("")
            status.text = "Ouvindo…"
        }
        voice.setImageResource(R.drawable.ic_mic)
        voice.contentDescription = "Desligar microfone"
        Ui.setActive(voice, true)
        refreshRing()
        listener.start(if (quiet) null else Wake.takeStream())
    }

    private fun resetVoice() {
        voice.setImageResource(R.drawable.ic_mic)
        voice.contentDescription = "Falar"
        Ui.setActive(voice, false)
        refreshRing()
    }

    private fun stopListening() {
        main.removeCallbacks(autoSend)
        main.removeCallbacks(relisten)
        if (listening) listener.stop()
        listening = false
        passive = false
        resetVoice()
        Live.typing = writing
    }

    /** O que o reconhecedor entendeu: aparece, e vai sozinho logo depois, a menos que o dono toque no campo. */
    private fun heard(text: String) {
        if (textMode) return
        listening = false
        passive = false
        resetVoice()
        if (previewOnly) { input.setText(voiceDraft.join(text)); return }
        val command = Commands.parse(text)
        Wake.report("faixa", text, command)
        if (!Live.continuous && command != null && (questionId == null || command in URGENT)) {
            Live.typing = writing
            input.setText("")
            if (act(command)) {
                main.postDelayed(relisten, RELISTEN_MS)
                return
            }
        }
        if (Commands.onlyWake(text)) {
            // Só a palavra (o cano trouxe o fim dela e o silêncio): ouve de novo, agora o pedido.
            Live.typing = writing
            listen()
            return
        }
        if (Live.continuous) {
            // No modo contínuo cada fala já vai: o pedido seguinte, a resposta de uma pergunta ou um comando.
            Live.typing = writing
            input.setText("")
            dispatch(voiceDraft.join(text))
            main.postDelayed(relisten, RELISTEN_MS)
            return
        }
        val said = voiceDraft.join(Commands.withoutWake(text))
        input.setText(said)
        status.text = "Entendi: «$said». Toque no campo para corrigir."
        main.postDelayed(autoSend, 1500)
    }

    /** O reconhecedor não ouviu nada: no modo contínuo, volta a ouvir; fora dele, avisa. */
    private fun silence() {
        val wasPassive = passive
        listening = false
        passive = false
        resetVoice()
        Live.typing = writing
        if (Live.continuous) {
            main.postDelayed(relisten, RELISTEN_MS)
        } else if (!wasPassive) {
            status.text = "Não ouvi nada. Toque no microfone e fale."
        }
    }

    /** No modo contínuo, o microfone volta a ouvir sempre que pode: sem o agente falando e sem o dono escrevendo. */
    private fun loop() {
        main.removeCallbacks(relisten)
        if (!Live.continuous || dialog == null || textMode || writing || listening || secret) return
        if (Speaker.speaking) {
            main.postDelayed(relisten, 500)  // uma fala sem aviso de fim (outra a cortou): tenta de novo logo
            return
        }
        listen(quiet = true)
    }

    /** Lê `text` em voz alta; no modo contínuo o microfone fecha durante a fala (senão ouviria o próprio agente). */
    fun say(text: String, then: (() -> Unit)? = null) = onMain {
        main.removeCallbacks(relisten)
        if (listening && passive) {
            listener.stop()
            listening = false
            passive = false
            resetVoice()
        }
        Speaker.speak(service, text) { then?.invoke(); loop() }
    }

    /** Uma fala no modo contínuo: a resposta da pergunta em aberto, um comando ou o pedido seguinte. */
    private fun dispatch(text: String) {
        val command = Commands.parse(text)
        when {
            questionId != null && command !in URGENT -> answer(Commands.withoutWake(text))
            command != null && act(command) -> {}
            else -> request(Commands.withoutWake(text))
        }
    }

    /**
     * Um comando falado: o mesmo que o botão, dito em voz alta. false quando ele não vale agora e a fala segue como
     * instrução ao agente ou, no modo contínuo, como pedido: sem pedido em curso, "pausa" e "para" são pedir para
     * pausar ou parar a música.
     */
    private fun act(command: Command): Boolean {
        val task = !Live.continuous || Live.requesting
        when (command) {
            Command.LIVE -> if (Live.continuous) {
                say("O modo contínuo já está ligado.")
            } else {
                startContinuous(fromButton = true)
                say("Modo contínuo ligado. Pode ir pedindo; diga «finalizar» para sair.")
            }
            Command.FINISH -> if (Live.continuous) endContinuous() else stopTask()
            Command.STOP, Command.CLOSE -> when {
                Live.continuous && Live.requesting -> stopRequest()
                Live.continuous && command == Command.CLOSE -> endContinuous()
                Live.continuous -> return false
                else -> stopTask()
            }
            Command.PAUSE -> {
                if (!task) return false
                if (!Live.paused) togglePause()
                say("Pausado.")
            }
            Command.RESUME -> {
                if (!Live.paused && !Live.owner) return false
                togglePause()
                say("Continuando.")
            }
            Command.OWNER -> {
                if (!task) return false
                setOwner(true, fromButton = true)
                say("Sua vez: eu mostro cada passo.")
            }
            Command.AGENT -> {
                if (!task || !Live.owner) return false
                setOwner(false, fromButton = true)
                say("Deixa comigo.")
            }
            Command.MINIMIZE -> minimize()
            Command.EXPAND -> expand()
            Command.MOVE -> moveTo(!(floating?.atTop ?: false))
            Command.MUTE -> {
                Speaker.setEnabled(service, false)
                status.text = "Voz desligada: o que eu disser fica só escrito aqui."
            }
            Command.UNMUTE -> {
                Speaker.setEnabled(service, true)
                say("Voz ligada.")
            }
            Command.REPEAT -> say(status.text.toString())
            Command.SLOWER, Command.FASTER -> {
                val changed = Speaker.changeRate(service, command == Command.SLOWER)
                // Diz de novo o que estava na faixa, já no ritmo novo: quem pede mais devagar quer ouvir de novo.
                if (changed) say(status.text.toString())
                else say(if (command == Command.SLOWER) "Já estou falando o mais devagar que consigo." else "Já estou no mais rápido.")
            }
            Command.WRITE -> startWriting(force = true)
        }
        Log.i("lmphone", "faixa: comando falado $command")
        return true
    }

    /** "Alexa, para" numa tarefa: encerra, como o X (sem o segundo toque: a fala já é a intenção). */
    private fun stopTask() {
        Live.stopped = true
        Live.event("fechou")
        hide()
        release()
        Speaker.speak(service, "Parei.")
        Log.i("lmphone", "faixa: tarefa encerrada pela voz")
    }

    /**
     * A faixa saiu: o cérebro desliga a acessibilidade (na hora, sem pedido em curso; senão, no fim dele), mesmo que
     * achasse que o modo contínuo estava ligado. Sem isso a acessibilidade ficava ligada sem a faixa.
     */
    private fun release() {
        val app = service.applicationContext
        thread(name = "lmphone-live") { Brain.live(app, "encerrar") }
    }

    /** "Para" no modo contínuo: o pedido em curso acaba, e a faixa segue ouvindo o próximo. */
    private fun stopRequest() {
        Live.stopped = true
        Live.event("fechou")
        status.text = "Parei. Pode pedir outra coisa."
        say("Parei.")
    }

    /** O dono disse a palavra de ativação com a faixa na tela: ela abre e ouve o comando (ou uma instrução). */
    fun wake() = onMain {
        if (dialog == null || writing) {
            Wake.endStream()
            return@onMain
        }
        expand()
        main.removeCallbacks(collapse)
        if (listening) stopListening()
        textMode = false
        listen()
    }

    /** O pedido seguinte. O que estiver em curso para: o PC vê "novo_pedido" na volta seguinte e o encerra. */
    private fun request(text: String) {
        val id = ++requestId
        if (Live.requesting) Live.event("novo_pedido", JSONObject().put("texto", text))
        Live.requesting = true
        main.removeCallbacks(collapse)
        status.text = "Recebi: $text"
        statusScroll.scrollTo(0, 0)
        refreshRing()
        val app = service.applicationContext
        thread(name = "lmphone-pedido") {
            val result = Brain.send(app, text, continuous = true)
            main.post {
                if (id != requestId) return@post  // um pedido mais novo tomou o lugar deste
                Live.requesting = false
                showAnswer(result.message)
            }
        }
    }

    /** A resposta de um pedido no modo contínuo: a faixa abre com ela, lê em voz alta e volta a ser o círculo depois. */
    fun showAnswer(message: String) = onMain {
        refreshRing()
        if (dialog == null || message.isBlank()) return@onMain
        expand()
        status.text = message
        statusScroll.scrollTo(0, 0)
        say(message) { main.postDelayed(collapse, ANSWER_MS) }
    }

    /** O começo de um pedido (o PC avisa): no modo contínuo a faixa passa de um pedido para o outro, sem pausa nem vez. */
    fun newTask() = onMain {
        Live.newTask()
        main.removeCallbacks(collapse)
        if (dialog == null) return@onMain
        refreshPause()
        setOwner(false, fromButton = false)
        refreshRing()
    }

    /** Liga o modo contínuo: pelo botão ∞ da faixa (o PC fica sabendo), ou o PC avisa que ele começou pelo painel. */
    fun startContinuous(fromButton: Boolean = false) = onMain {
        val was = Live.continuous
        Live.continuous = true
        // O aviso do cérebro pode chegar antes de a faixa ficar pronta (2026-10-27: o modo ficou ligado no cérebro e
        // desligado aqui, e o X não o encerrou): `show` termina o resto.
        if (dialog == null) return@onMain
        Ui.setActive(liveButton, true)
        liveButton.contentDescription = "Sair do modo contínuo"
        if (fromButton && !was) {
            status.text = "Modo contínuo: pode ir pedindo. Diga «finalizar» para encerrar."
            Live.event("continuo")
            // Se o pedido em curso acabar antes de o PC ler o evento, o "iniciar" deixa tudo ligado do mesmo jeito.
            val app = service.applicationContext
            thread(name = "lmphone-live") { Brain.live(app, "iniciar") }
        }
        refreshRing()
        loop()
    }

    /** Desliga o modo contínuo pelo botão ∞: o pedido em curso termina, e depois o PC desliga tudo. */
    private fun stopContinuous() {
        Live.continuous = false
        if (listening && passive) {
            listener.stop()
            listening = false
            passive = false
        }
        resetVoice()
        Ui.setActive(liveButton, false)
        liveButton.contentDescription = "Modo contínuo"
        status.text = if (Live.requesting) "Termino este pedido e saio do modo contínuo." else "Saindo do modo contínuo…"
        val app = service.applicationContext
        thread(name = "lmphone-live") { Brain.live(app, "encerrar") }
    }

    /** "Finalizar" ou o X no modo contínuo: o que estiver em curso para, a faixa sai e o PC desliga tudo. */
    private fun endContinuous() {
        Live.continuous = false
        Live.stopped = true
        Live.event("fechou")
        Speaker.stop()
        val app = service.applicationContext
        thread(name = "lmphone-live") { Brain.live(app, "encerrar") }
        hide()
        Log.i("lmphone", "faixa: modo contínuo encerrado")
    }

    /** O dono tocou no campo (ou trocou a voz pelo teclado): a janela ganha o foco e o teclado dele volta. */
    private fun startWriting(force: Boolean = false) {
        val window = dialog?.window ?: return
        // Um "toque" no campo logo depois de um gesto do agente é do agente, não do dono.
        if (writing || (!force && agentJustActed())) return
        textMode = true
        writing = true
        Live.typing = true
        main.removeCallbacks(autoSend)  // tocar no campo é corrigir o que a voz entendeu
        stopListening()
        Speaker.stop()
        status.text = "Escrevendo…"
        Live.event("escrevendo")
        window.clearFlags(WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE or WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING)
        // O controlador move só o necessário quando os insets do teclado chegarem.
        voice.visibility = View.VISIBLE
        liveButton.visibility = if (input.text.isNullOrBlank()) View.VISIBLE else View.GONE
        Live.previousIme?.let { Flavor.switchKeyboard(service, it) }
        input.isFocusableInTouchMode = true
        input.isFocusable = true
        input.requestFocus()
        input.setSelection(input.text.length)
        main.postDelayed({
            (service.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).showSoftInput(input, 0)
        }, 150)
    }

    /** Manda o que o dono disse ou escreveu (uma resposta, se há pergunta; senão, uma instrução). */
    private fun send() {
        if (previewOnly) return
        main.removeCallbacks(autoSend)
        val text = input.text.toString().trim()
        if (text.isNotEmpty() && Live.continuous) {
            dispatch(text)  // escrito vale como falado: a resposta, um comando ou o pedido seguinte
        } else if (text.isNotEmpty() && questionId != null) {
            answer(text)
        } else if (text.isNotEmpty()) {
            Live.event("instrucao", JSONObject().put("texto", text))
            status.text = "Recebi: $text"
        }
        if (writing) stopWriting(clearInput = true) else {
            input.setText("")
            stopListening()
        }
    }

    /** Fecha a escrita: esconde o teclado, devolve o do agente e a faixa volta a não ter foco. */
    private fun stopWriting(clearInput: Boolean = false) {
        val window = dialog?.window ?: return
        if (!writing) return
        writing = false
        if (clearInput) input.setText("")
        input.clearFocus()
        input.isFocusable = false
        voice.visibility = View.VISIBLE
        liveButton.visibility = if (input.text.isNullOrBlank()) View.VISIBLE else View.GONE
        (service.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(input.windowToken, 0)
        window.addFlags(WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_UNSPECIFIED)
        floating?.update()
        agentKeyboard?.let { Flavor.switchKeyboard(service, it) }
        Live.typing = listening
        if (!Live.paused && questionId == null && !Live.continuous) status.text = "Continuando…"
        if (!textMode) main.postDelayed(relisten, RELISTEN_MS)
    }

    /** O ícone continua sendo microfone nos dois modos; o campo é quem abre o teclado. */
    private fun microphone() {
        if (listening) {
            textMode = true
            stopListening()
            status.text = "Microfone desligado"
            return
        }
        textMode = false
        if (writing) stopWriting()
        listen(keepText = true)
    }
}
