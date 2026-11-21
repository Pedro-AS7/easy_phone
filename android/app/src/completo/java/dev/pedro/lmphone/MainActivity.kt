package dev.pedro.lmphone

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import java.io.File

/**
 * Tela inicial: como chamar o assistente (etapa 3 de docs/plano-assistente.md) e onde fica o cérebro (etapa 3 de
 * docs/plano-app-android.md): no PC, como antes, ou no próprio celular, com a chave do provedor guardada aqui.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // O microfone, para o pedido falado no painel (o painel não pode pedir a permissão), e os contatos, para o cofre
        // do cérebro no celular.
        val missing = listOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.READ_CONTACTS)
            .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) requestPermissions(missing.toTypedArray(), 1)
        setContent { Home() }
    }

    override fun onResume() {
        super.onResume()
        Wake.start(this)  // com o app na frente o Android sempre deixa ligar o microfone
    }
}

@Composable
fun Home() {
    val context = LocalContext.current
    val accent = Color(0xFF305CDE)
    MaterialTheme(colorScheme = if (isSystemInDarkTheme())
        darkColorScheme(primary = accent, secondary = accent, tertiary = accent, onPrimary = Color.White)
    else lightColorScheme(primary = accent, secondary = accent, tertiary = accent, onPrimary = Color.White)) {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(modifier = Modifier.padding(24.dp).verticalScroll(rememberScrollState())) {
                Text("lm_phone", style = MaterialTheme.typography.headlineMedium)
                Text("Versão ${BuildConfig.VERSION_NAME}.\n\nPara chamar o assistente: toque longo na tecla lateral, com o " +
                     "lm_phone escolhido em Configurações > Apps > Apps padrão > Assistente digital, e a tecla lateral " +
                     "em Recursos avançados > Tecla lateral > Pressionar e segurar > Assistente digital.",
                     style = MaterialTheme.typography.bodyLarge)
                Spacer(Modifier.height(24.dp))
                WakeChoice(context)
                Spacer(Modifier.height(24.dp))
                HeaderChoice(context)
                Spacer(Modifier.height(24.dp))
                BrainChoice(context)
            }
        }
    }
}

@Composable
private fun HeaderChoice(context: Context) {
    var enabled by remember { mutableStateOf(Ui.headerMenu(context)) }
    var blur by remember { mutableStateOf(Ui.blurEnabled(context)) }
    var personTaps by remember { mutableStateOf(!Ui.guideAgent(context)) }
    Text("Ensinar", style = MaterialTheme.typography.titleMedium)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(checked = personTaps, onCheckedChange = { Ui.setGuideAgent(context, !it); personTaps = it })
        Spacer(Modifier.width(12.dp))
        Text("Quando eu peço para aprender, eu mesmo toco")
    }
    Text(if (personTaps) "O assistente mostra onde tocar, explica e espera você fazer cada passo. Se preferir, diga «faz pra mim»."
         else "O assistente explica cada passo e toca ele mesmo, depois de uns segundos para você tocar primeiro.",
        style = MaterialTheme.typography.bodyMedium)
    Spacer(Modifier.height(16.dp))
    Text("Interface", style = MaterialTheme.typography.titleMedium)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(checked = blur, onCheckedChange = { Ui.setBlurEnabled(context, it); blur = it })
        Spacer(Modifier.width(12.dp))
        Text("Desfocar o fundo (blur)")
    }
    Text("Desligado, usa apenas um fundo semitransparente. Aplicado na próxima abertura do painel.",
        style = MaterialTheme.typography.bodyMedium)
    Spacer(Modifier.height(12.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(checked = enabled, onCheckedChange = { Ui.setHeaderMenu(context, it); enabled = it })
        Spacer(Modifier.width(12.dp))
        Text("Reunir ações na barra superior")
    }
    Text("Toque na barra para abrir as opções. Arraste para o lado para minimizar, ou para baixo além do limite inferior para fechar. Arraste na vertical para mover o painel.",
        style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun WakeChoice(context: Context) {
    var on by remember { mutableStateOf(Wake.enabled(context)) }
    val models = Wake.modelsPresent(context)
    Text("Chamar pela voz", style = MaterialTheme.typography.titleMedium)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(checked = on, enabled = models, onCheckedChange = { Wake.setEnabled(context, it); on = it })
        Spacer(Modifier.width(12.dp))
        Text("Dizer \"${Wake.WORD}\" abre o assistente")
    }
    Text(when {
        !models -> "Faltam os modelos da palavra (no PC: tools.app.escuta enviar)."
        !Wake.microphone(context) -> "Falta a permissão do microfone."
        else -> "O microfone fica aberto (o ponto verde do Android aparece); o som fica no celular e não é gravado. " +
            "Gasta bateria."
    }, style = MaterialTheme.typography.bodyMedium)
    Spacer(Modifier.height(8.dp))
    Text("Pode falar de uma vez: \"${Wake.WORD}, abre o Waze\". Os botões também valem falados: live mode, pausa, " +
         "continua, para (encerra a tarefa), deixa que eu faço, faz você, minimiza, mostra a faixa, muda de lado, " +
         "silêncio, liga a voz, repete, escrever, fecha. No modo contínuo, basta o comando; \"finalizar\" sai dele.",
         style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun BrainChoice(context: Context) {
    var phone by remember { mutableStateOf(OnDevice.enabled(context)) }
    var hasKey by remember { mutableStateOf(ProviderKey.present(context)) }
    var typed by remember { mutableStateOf("") }
    val models = File(context.filesDir, "modelos/marcacao.onnx").exists() && File(context.filesDir, "modelos/escolha.onnx").exists()
    Text("Onde o assistente pensa", style = MaterialTheme.typography.titleMedium)
    Row(verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = !phone, onClick = { OnDevice.choose(context, false); phone = false })
        Text("No PC (o celular no USB ou na mesma rede, com \"run --celular\" no ar)")
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = phone, onClick = { OnDevice.choose(context, true); phone = true })
        Text("No celular (sem o PC)")
    }
    if (phone) {
        Spacer(Modifier.height(8.dp))
        Text(if (models) "Modelos pequenos: no celular." else "Modelos pequenos: faltam (no PC: tools.app.modelos enviar).")
        Text(if (hasKey) "Chave do provedor: guardada, cifrada pelo Keystore." else "Chave do provedor: falta.")
        if (!hasKey) {
            OutlinedTextField(value = typed, onValueChange = { typed = it }, label = { Text("Chave do OpenRouter") },
                visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                Button(onClick = {
                    if (typed.isNotBlank()) {
                        ProviderKey.save(context, typed)
                        typed = ""
                        hasKey = ProviderKey.present(context)
                    }
                }) { Text("Guardar") }
            }
        }
    }
}
