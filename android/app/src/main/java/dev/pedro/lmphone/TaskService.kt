package dev.pedro.lmphone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder

/**
 * Serviço em primeiro plano enquanto o agente trabalha (a acessibilidade ligada), com a notificação "tarefa em
 * andamento". Sem ele, o congelador de apps da Samsung (Freecess) congela o processo em segundo plano mesmo com a
 * acessibilidade ligada e fora da economia de bateria, e o servidor local para de responder ao cérebro.
 */
class TaskService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Tarefa em andamento", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.aviso_tarefa))
            .setOngoing(true)
            .build()
        startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        return START_NOT_STICKY
    }

    companion object {
        private const val CHANNEL = "tarefa"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, TaskService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, TaskService::class.java))
        }
    }
}
