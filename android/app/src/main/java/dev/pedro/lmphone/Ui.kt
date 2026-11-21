package dev.pedro.lmphone

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.FrameLayout
import android.view.Window
import android.view.WindowManager

/** Peças de interface comuns à faixa do live mode (Overlay) e ao painel do assistente (AssistSession). */
object Ui {
    const val BUTTON = "#28FFFFFF"
    const val ACTIVE = "#305CDE"
    const val INPUT = "#30FFFFFF"

    fun blurEnabled(context: Context) = context.getSharedPreferences("interface", Context.MODE_PRIVATE).getBoolean("blur", true)
    fun setBlurEnabled(context: Context, value: Boolean) {
        context.getSharedPreferences("interface", Context.MODE_PRIVATE).edit().putBoolean("blur", value).apply()
    }

    /** No guia, quem toca: a pessoa (o padrão, docs/plano-tutor.md) ou o agente, explicando, depois de uns segundos. */
    fun guideAgent(context: Context) = context.getSharedPreferences("interface", Context.MODE_PRIVATE).getBoolean("guia_agente", false)
    fun setGuideAgent(context: Context, value: Boolean) {
        context.getSharedPreferences("interface", Context.MODE_PRIVATE).edit().putBoolean("guia_agente", value).apply()
    }

    fun headerMenu(context: Context) = context.getSharedPreferences("interface", Context.MODE_PRIVATE).getBoolean("menu_na_barra", false)
    fun setHeaderMenu(context: Context, value: Boolean) {
        context.getSharedPreferences("interface", Context.MODE_PRIVATE).edit().putBoolean("menu_na_barra", value).apply()
    }

    internal fun configureHeader(context: Context, handle: View, actions: View,
        move: () -> Unit, minimize: () -> Unit, close: () -> Unit): () -> Unit {
        handle.setOnClickListener {
            if (headerMenu(context)) android.widget.PopupMenu(context, handle).apply {
                menu.add(0, 1, 0, "Mudar de lado")
                menu.add(0, 2, 1, "Minimizar")
                menu.add(0, 3, 2, "Fechar")
                setOnMenuItemClickListener {
                    when (it.itemId) { 1 -> move(); 2 -> minimize(); 3 -> close() }
                    true
                }
                show()
            }
        }
        return {
            val enabled = headerMenu(context)
            actions.visibility = if (enabled) View.GONE else View.VISIBLE
            handle.contentDescription = if (enabled) "Opções do painel. Toque para abrir o menu; arraste para o lado para minimizar ou para baixo além do limite para fechar."
                else "Arraste para mover o painel"
        }.also { it() }
    }

    fun dp(context: Context, value: Int) = (value * context.resources.displayMetrics.density).toInt()

    fun rounded(context: Context, color: String, radius: Int) =
        GradientDrawable().apply { cornerRadius = dp(context, radius).toFloat(); setColor(Color.parseColor(color)) }

    /** Blur simples do fundo, nativo quando disponível ou calculado com a imagem mantida só no aparelho. */
    internal fun glass(window: Window) = FrostedGlass(window)

    /** A área de arraste é maior que o traço visível, como a alça de uma bottom sheet. */
    fun handle(context: Context) = FrameLayout(context).apply {
        contentDescription = "Arraste para mover o painel. O botão Mudar de lado também permite reposicioná-lo."
        isFocusable = true
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(context, 18))
        addView(View(context).apply { background = rounded(context, "#70FFFFFF", 3) },
            FrameLayout.LayoutParams(dp(context, 34), dp(context, 3), android.view.Gravity.CENTER))
    }

    /** Um botão redondo com um ícone vetorial (res/drawable/ic_*.xml). `description` é o que um leitor de tela diz. */
    fun icon(context: Context, drawable: Int, description: String, onClick: () -> Unit) = icon(context, drawable, description, 36, onClick)

    fun icon(context: Context, drawable: Int, description: String, size: Int, onClick: () -> Unit) = ImageView(context).apply {
        setImageResource(drawable)
        contentDescription = description
        scaleType = ImageView.ScaleType.CENTER_INSIDE
        val pad = dp(context, if (size <= 24) 4 else 8)
        setPadding(pad, pad, pad, pad)
        background = rounded(context, BUTTON, size / 2)
        layoutParams = LinearLayout.LayoutParams(dp(context, size), dp(context, size))
        setOnClickListener { onClick() }
    }

    fun setActive(view: View, on: Boolean) {
        view.background = rounded(view.context, if (on) ACTIVE else BUTTON, 18)
    }

    /** Os três controles superiores ocupam a mesma largura que microfone + margem + live mode. */
    fun headerActions(context: Context, first: View, second: View, third: View) = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = android.view.Gravity.CENTER_VERTICAL
        layoutParams = LinearLayout.LayoutParams(dp(context, 36) * 2 + dp(context, 4), ViewGroup.LayoutParams.WRAP_CONTENT)
        addView(first)
        addView(android.widget.Space(context), LinearLayout.LayoutParams(0, 0, 1f))
        addView(second)
        addView(android.widget.Space(context), LinearLayout.LayoutParams(0, 0, 1f))
        addView(third)
    }

    fun margin(view: View, left: Int) = view.apply {
        (layoutParams as? LinearLayout.LayoutParams ?: LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT)).let { params ->
            params.leftMargin = dp(context, left)
            layoutParams = params
        }
    }
}

/**
 * Uma área de texto que rola e não passa de `maxHeight`: o texto inteiro fica acessível (antes ele era cortado em duas
 * linhas, sem rolagem) sem empurrar os botões para fora da tela.
 */
class CappedScroll(context: Context, private val maxHeight: Int) : ScrollView(context) {
    private var availableHeight = maxHeight

    fun limitHeight(height: Int) {
        val limited = height.coerceIn(0, maxHeight)
        if (availableHeight != limited) { availableHeight = limited; requestLayout() }
    }
    init {
        // O que passa da altura esmaece na borda, e a barra de rolagem aparece: dá para ver que há mais texto.
        isVerticalFadingEdgeEnabled = true
        setFadingEdgeLength(Ui.dp(context, 18))
        isVerticalScrollBarEnabled = true
        isScrollbarFadingEnabled = false
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        super.onMeasure(widthMeasureSpec, MeasureSpec.makeMeasureSpec(availableHeight, MeasureSpec.AT_MOST))
    }
}
