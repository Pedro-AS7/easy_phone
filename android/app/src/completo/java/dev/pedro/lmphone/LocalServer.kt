package dev.pedro.lmphone

import android.util.Log
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

/**
 * Um servidor HTTP mínimo em 127.0.0.1, para o cérebro do PC (pelo `adb forward`). Qualquer app do aparelho alcança essa
 * porta, então todo pedido precisa da senha que o app gera e só o adb lê (`run-as`): sem ela, outro app leria a tela.
 * Cada resposta leva Content-Length e fecha a conexão.
 */
class LocalServer(private val port: Int, private val token: String, private val handle: (String, JSONObject) -> JSONObject) {
    private var socket: ServerSocket? = null

    fun start() {
        val server = ServerSocket(port, 8, InetAddress.getByName("127.0.0.1"))
        socket = server
        thread(name = "lmphone-server", isDaemon = true) {
            while (!server.isClosed) {
                val client = try { server.accept() } catch (e: Exception) { break }
                thread(isDaemon = true) { serve(client) }
            }
        }
    }

    fun stop() {
        socket?.close()
        socket = null
    }

    private fun serve(client: Socket) = client.use {
        try {
            val input = BufferedInputStream(it.getInputStream())
            val head = readHead(input)
            val lines = head.split("\r\n")
            val (method, path) = lines.first().split(" ").let { parts -> parts[0] to parts.getOrElse(1) { "/" } }
            val headers = lines.drop(1).filter { line -> ':' in line }
                .associate { line -> line.substringBefore(':').trim().lowercase() to line.substringAfter(':').trim() }
            val length = headers["content-length"]?.toIntOrNull() ?: 0
            val body = ByteArray(length).also { bytes -> var read = 0; while (read < length) { val n = input.read(bytes, read, length - read); if (n < 0) break; read += n } }
            val reply = when {
                headers["authorization"] != "Bearer $token" -> 401 to JSONObject().put("error", "unauthorized")
                else -> try {
                    200 to handle(path, if (method == "POST" && length > 0) JSONObject(String(body)) else JSONObject())
                } catch (e: Exception) {
                    Log.w("lmphone", "pedido $path falhou", e)
                    500 to JSONObject().put("error", e.toString())
                }
            }
            val bytes = reply.second.toString().toByteArray()
            val status = if (reply.first == 200) "200 OK" else if (reply.first == 401) "401 Unauthorized" else "500 Internal Server Error"
            it.getOutputStream().apply {
                write(("HTTP/1.1 $status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\n" +
                    "Connection: close\r\n\r\n").toByteArray())
                write(bytes)
                flush()
            }
        } catch (e: Exception) {
            Log.w("lmphone", "conexão falhou", e)
        }
    }

    private fun readHead(input: BufferedInputStream): String {
        val out = ByteArrayOutputStream()
        var last4 = 0
        while (true) {
            val b = input.read()
            if (b < 0) break
            out.write(b)
            last4 = (last4 shl 8) or b
            if (last4 == 0x0D0A0D0A) break
        }
        return out.toString(Charsets.UTF_8.name()).trimEnd()
    }
}
