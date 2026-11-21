package dev.pedro.lmphone

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Rect
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject

/**
 * A tela no mesmo JSON que o `state_full` do Portal (Mobilerun): `a11y_tree`, `phone_state` e `device_context`. Assim o
 * `lmphone/device.py` a transforma no mesmo texto de sempre, e o executor, a IA local, a máscara e o cache não mudam.
 * Os campos são os que o `device.py` lê; o teste `tests/test_device.py` fixa o formato do lado do PC.
 */
object Screen {
    fun state(service: AccessibilityService): JSONObject {
        // O cache da acessibilidade guardava linhas que a lista já tinha reciclado: depois de rolar, elas vinham por cima
        // das novas, visíveis e iguais em duas leituras (2026-11-18, na varredura das Configurações: 16 de 30 telas
        // roladas; o destaque cairia no lugar de uma linha que já saiu dali). A leitura vem sempre do app da tela.
        service.clearCache()
        val root = service.rootInActiveWindow
        val focused = root?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        val packageName = root?.packageName?.toString() ?: ""
        val phone = JSONObject()
            .put("currentApp", label(service, packageName))
            .put("packageName", packageName)
            .put("isEditable", focused?.isEditable == true)
            .put("focusedElement", if (focused != null) JSONObject().put("text", text(focused) ?: "") else JSONObject.NULL)
        val metrics = (service.getSystemService(Context.WINDOW_SERVICE) as WindowManager).currentWindowMetrics.bounds
        val context = JSONObject().put("screen_bounds", JSONObject().put("width", metrics.width()).put("height", metrics.height()))
        return JSONObject()
            .put("a11y_tree", if (root != null) node(root) else JSONObject().put("children", JSONArray()))
            .put("phone_state", phone)
            .put("device_context", context)
    }

    /** O nome do app como aparece para o usuário ("Settings"), ou o pacote. */
    private fun label(context: Context, packageName: String): String = try {
        val pm = context.packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(packageName, PackageManager.ApplicationInfoFlags.of(0))).toString()
    } catch (e: Exception) {
        packageName
    }

    /** O texto do nó, sem a dica de campo vazio ("Search…" num campo sem texto não é texto digitado). */
    private fun text(node: AccessibilityNodeInfo): String? =
        if (node.isShowingHintText) null else node.text?.toString()

    private fun node(info: AccessibilityNodeInfo): JSONObject {
        val bounds = Rect().also { info.getBoundsInScreen(it) }
        val out = JSONObject()
            .put("className", info.className?.toString() ?: "")
            .put("resourceId", info.viewIdResourceName ?: "")
            .put("text", text(info) ?: "")
            .put("contentDescription", info.contentDescription?.toString() ?: "")
            .put("boundsInScreen", JSONObject().put("left", bounds.left).put("top", bounds.top)
                .put("right", bounds.right).put("bottom", bounds.bottom))
            .put("isCheckable", info.isCheckable)
            .put("isChecked", info.isChecked)
            .put("isClickable", info.isClickable)
            .put("isLongClickable", info.isLongClickable)
            .put("isEditable", info.isEditable)
            .put("isVisibleToUser", info.isVisibleToUser)
            .put("drawingOrder", info.drawingOrder)
            .put("windowId", info.windowId)
        val children = JSONArray()
        for (i in 0 until info.childCount) {
            info.getChild(i)?.let { children.put(node(it)) }
        }
        return out.put("children", children)
    }
}
