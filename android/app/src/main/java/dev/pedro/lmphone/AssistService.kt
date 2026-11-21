package dev.pedro.lmphone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionService
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService
import android.speech.RecognitionService
import android.speech.SpeechRecognizer

/**
 * O lm_phone como assistente digital do Android (etapa 3 de docs/plano-assistente.md): com ele escolhido em
 * Configurações > Apps > Apps padrão > Assistente digital, o toque longo na tecla lateral abre o painel (AssistSession).
 * O sistema mantém este serviço ligado enquanto ele é o assistente; fora de uma tarefa a acessibilidade continua
 * desligada (apps de banco): o painel não precisa dela.
 */
class AssistService : VoiceInteractionService() {
    override fun onReady() {
        super.onReady()
        instance = this
        Wake.start(this)  // o sistema liga o assistente ao ligar o celular: a palavra de ativação volta junto
    }

    override fun onShutdown() {
        instance = null
        super.onShutdown()
    }

    companion object {
        @Volatile private var instance: AssistService? = null
        private const val CHANNEL = "resposta"

        internal const val CONTEXT_FLAGS = VoiceInteractionSession.SHOW_WITH_SCREENSHOT or VoiceInteractionSession.SHOW_WITH_ASSIST

        /** Abre o painel já ouvindo, como o toque longo na tecla lateral (a palavra de ativação). false sem o serviço. */
        fun open(): Boolean {
            val service = instance ?: return false
            // O Android só entrega screenshot junto do pedido de contexto; a sessão descarta a estrutura recebida.
            service.showSession(Bundle(), CONTEXT_FLAGS)
            return true
        }

        /** Fecha o painel (a conferência pelo adb: o shell não tem permissão de fechá-lo). */
        fun close() {
            AssistSession.current?.finish()
        }

        /**
         * Um aviso do app (não uma resposta do assistente: sem o botão de denunciar), lido em voz alta no painel, que fecha
         * sozinho depois. O que a `loja` diz quando o guia precisa da tela e a acessibilidade está desligada.
         */
        fun notice(context: Context, message: String) {
            val service = instance
            if (service == null) {
                answer(context, message)
                return
            }
            service.showSession(Bundle().apply {
                putString(AssistSession.ANSWER, message)
                putBoolean(AssistSession.NOTICE, true)
            }, CONTEXT_FLAGS)
        }

        /** Mostra a resposta do pedido: o painel volta com ela; sem o serviço no ar, vai numa notificação. */
        fun answer(context: Context, message: String) {
            val service = instance
            if (service != null) {
                service.showSession(Bundle().apply { putString(AssistSession.ANSWER, message) },
                    CONTEXT_FLAGS)
                return
            }
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL, "Respostas do assistente", NotificationManager.IMPORTANCE_DEFAULT))
            manager.notify(2, Notification.Builder(context, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle("lm_phone")
                .setContentText(message)
                .setStyle(Notification.BigTextStyle().bigText(message))
                .build())
        }
    }
}

/** Cria o painel a cada vez que o sistema pede uma sessão (toque longo na tecla lateral ou `showSession`). */
class AssistSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession = AssistSession(this)
}

/**
 * O Android só aceita um assistente digital que tenha também um serviço de reconhecimento de fala. A voz é a etapa 4;
 * por enquanto ele recusa.
 */
class AssistRecognition : RecognitionService() {
    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {
        listener?.error(SpeechRecognizer.ERROR_CLIENT)
    }

    override fun onCancel(listener: Callback?) {}

    override fun onStopListening(listener: Callback?) {}
}
