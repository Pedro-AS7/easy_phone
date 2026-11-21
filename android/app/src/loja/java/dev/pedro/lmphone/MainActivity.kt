package dev.pedro.lmphone

import android.Manifest
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/**
 * A tela do app da loja (docs/plano-play-store.md, fase 4): o que falta para o Guia funcionar, em passos grandes, um de
 * cada vez. O atalho da acessibilidade vem antes de tudo e só depois do aviso em destaque, com "Concordo" explícito (a política da
 * Play: o aviso fica no próprio app, separado de outros avisos, e sair dele não vale como consentimento).
 */
class MainActivity : ComponentActivity() {
    private val refresh = mutableIntStateOf(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { Home(refresh.intValue) }
    }

    override fun onResume() {
        super.onResume()
        refresh.intValue++  // a pessoa voltou das Configurações: o que mudou aparece
    }
}

private object Setup {
    private fun prefs(context: Context) = context.getSharedPreferences("loja", Context.MODE_PRIVATE)

    fun consented(context: Context) = prefs(context).getBoolean("aviso_acessibilidade", false)

    fun consent(context: Context, yes: Boolean) = prefs(context).edit().putBoolean("aviso_acessibilidade", yes)
        .putLong("aviso_acessibilidade_em", System.currentTimeMillis()).apply()

    /** O atalho dos botões de volume já ligou o serviço uma vez (`AgentService` grava): o caminho todo funciona. */
    fun shortcut(context: Context) = prefs(context).getBoolean("atalho_ok", false)

    fun assistant(context: Context) =
        context.getSystemService(RoleManager::class.java)?.isRoleHeld(RoleManager.ROLE_ASSISTANT) == true

    fun microphone(context: Context) = context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun notifications(context: Context) = context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    fun models(context: Context) = Flavor.modelsDir(context) != null
}

@Composable
private fun Home(refresh: Int) {
    val context = LocalContext.current
    val accent = Color(0xFF305CDE)
    var consented by remember(refresh) { mutableStateOf(Setup.consented(context)) }
    var shortcut by remember(refresh) { mutableStateOf(Setup.shortcut(context)) }
    // O teste do atalho abre o painel por cima desta tela, que pode não voltar a `onResume`: confere a cada segundo.
    LaunchedEffect(consented, shortcut) {
        while (consented && !shortcut) {
            delay(1000)
            shortcut = Setup.shortcut(context)
        }
    }
    MaterialTheme(colorScheme = if (isSystemInDarkTheme())
        darkColorScheme(primary = accent, onPrimary = Color.White)
    else lightColorScheme(primary = accent, onPrimary = Color.White)) {
        Surface(modifier = Modifier.fillMaxSize()) {
            Column(modifier = Modifier.padding(24.dp).verticalScroll(rememberScrollState())) {
                Text("Guia do Celular", style = MaterialTheme.typography.headlineMedium)
                Spacer(Modifier.height(8.dp))
                Text("Pergunte como se faz alguma coisa no celular. O Guia mostra onde tocar, explica e espera você " +
                     "fazer. Ele nunca toca nem muda nada sozinho.", fontSize = 20.sp, lineHeight = 28.sp)
                Spacer(Modifier.height(24.dp))
                when {
                    !consented -> Disclosure(onYes = {
                        Setup.consent(context, true)
                        consented = true
                    })
                    !shortcut -> Shortcut(context)
                    else -> Ready(context)
                }
            }
        }
    }
}

/** O aviso em destaque, antes de pedir a acessibilidade (formato da política "User Data" da Play). */
@Composable
private fun Disclosure(onYes: () -> Unit) {
    var declined by remember { mutableStateOf(false) }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text("Antes de começar: o Guia precisa ler a tela", fontSize = 22.sp, fontWeight = FontWeight.Bold, lineHeight = 28.sp)
            Spacer(Modifier.height(12.dp))
            Text("O Guia do Celular usa o serviço de acessibilidade do Android para ler o texto que aparece na tela e " +
                 "saber onde você toca. Isso serve para mostrar onde tocar enquanto ele te ensina.", fontSize = 18.sp, lineHeight = 26.sp)
            Spacer(Modifier.height(10.dp))
            Text("• Ele só fica ligado quando você pede ajuda: você liga segurando os dois botões de volume, e ele se " +
                 "desliga sozinho no fim de cada guia.", fontSize = 18.sp, lineHeight = 26.sp)
            Spacer(Modifier.height(10.dp))
            Text("• Só durante um guia que você pediu, o texto da tela vai ao servidor do Guia do Celular e a um provedor " +
                 "de inteligência artificial, para entender o que fazer. Antes de sair do celular, nomes, números de " +
                 "telefone, e-mails e documentos são trocados por dados falsos.", fontSize = 18.sp, lineHeight = 26.sp)
            Text("• O servidor não guarda o que você pede nem o que está na tela; guarda só quantos pedidos foram feitos.",
                 fontSize = 18.sp, lineHeight = 26.sp)
            Text("• O Guia nunca toca, digita, compra nem muda nada no celular. Quem faz cada passo é você.",
                 fontSize = 18.sp, lineHeight = 26.sp)
            Spacer(Modifier.height(20.dp))
            Button(onClick = onYes, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                Text("Concordo, continuar", fontSize = 20.sp)
            }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = { declined = true }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                Text("Agora não", fontSize = 20.sp)
            }
            if (declined) {
                Spacer(Modifier.height(8.dp))
                Text("Tudo bem. Sem ler a tela o Guia não consegue te mostrar onde tocar. Você pode voltar aqui quando quiser.",
                     fontSize = 18.sp, lineHeight = 26.sp)
            }
        }
    }
}

/**
 * A pessoa concordou: o atalho dos botões de volume, em passos grandes, e um teste (a faixa ainda não existe sem a
 * acessibilidade). O app não pode ligar a própria acessibilidade; com o atalho, ela liga com um gesto quando precisa, e
 * o app a desliga no fim do guia (apps de banco bloqueiam o celular quando a veem ligada). Nomes da One UI 9.
 */
@Composable
private fun Shortcut(context: Context) {
    Text("Ligar o Guia com os botões de volume", fontSize = 22.sp, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(12.dp))
    listOf("1. Toque no botão azul aqui embaixo.",
           "2. Na tela que abrir, toque em «Atalhos de acessibilidade».",
           "3. Toque em «Teclas Aumentar/Diminuir volume».",
           "4. Escolha «Guia do Celular» e volte para cá com a setinha de voltar.").forEach {
        Text(it, fontSize = 20.sp, lineHeight = 30.sp)
    }
    Spacer(Modifier.height(20.dp))
    Button(onClick = { openAccessibility(context) }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
        Text("Abrir as Configurações", fontSize = 20.sp)
    }
    Spacer(Modifier.height(24.dp))
    Text("Agora teste", fontSize = 22.sp, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(8.dp))
    Text("Segure os dois botões de volume juntos, o de aumentar e o de diminuir, por 3 segundos. Na primeira vez o " +
         "celular mostra um aviso sobre o atalho: se ele pedir, aceite, e segure os dois de novo.", fontSize = 20.sp, lineHeight = 30.sp)
}

@Composable
private fun Ready(context: Context) {
    Text("Pronto, o Guia está configurado.", fontSize = 22.sp, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(8.dp))
    Text("Quando precisar de ajuda, segure os dois botões de volume juntos por 3 segundos. O Guia liga, ouve o que você " +
         "quer aprender e se desliga sozinho no fim.", fontSize = 18.sp, lineHeight = 26.sp)
    Spacer(Modifier.height(16.dp))
    if (!Setup.models(context)) {
        Text("Falta só baixar uma parte do Guia. Deixe o celular no Wi-Fi um pouco.", fontSize = 18.sp, lineHeight = 26.sp)
        Spacer(Modifier.height(16.dp))
    }
    if (!Setup.microphone(context) || !Setup.notifications(context)) {
        Text("Para você poder falar com o Guia e ver o aviso de que ele está te ajudando:", fontSize = 18.sp, lineHeight = 26.sp)
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            (context as? ComponentActivity)?.requestPermissions(
                arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS), 1)
        }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("Permitir microfone e avisos", fontSize = 20.sp) }
        Spacer(Modifier.height(16.dp))
    }
    if (!Setup.assistant(context)) {
        Text("Para chamar o Guia segurando o botão do lado do celular, escolha o Guia como assistente digital:",
             fontSize = 18.sp, lineHeight = 26.sp)
        Spacer(Modifier.height(8.dp))
        Button(onClick = { start(context, Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS)) },
            modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("Escolher o assistente", fontSize = 20.sp) }
        Text("Toque em «Assistente digital» e depois em «Guia do Celular».", fontSize = 18.sp, lineHeight = 26.sp)
        Spacer(Modifier.height(16.dp))
    } else {
        Button(onClick = { AssistService.open() }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
            Text("Pedir ajuda agora", fontSize = 20.sp)
        }
        Spacer(Modifier.height(8.dp))
        Text("Ou segure o botão do lado do celular, de qualquer tela, e diga o que quer aprender.", fontSize = 18.sp, lineHeight = 26.sp)
    }
}

private fun openAccessibility(context: Context) = start(context, Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))

private fun start(context: Context, intent: Intent) {
    try {
        context.startActivity(intent)
    } catch (_: Exception) {
        context.startActivity(Intent(Settings.ACTION_SETTINGS))
    }
}
