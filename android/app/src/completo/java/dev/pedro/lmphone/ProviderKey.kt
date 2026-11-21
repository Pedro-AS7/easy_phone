package dev.pedro.lmphone

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import dev.pedro.lmphone.cerebro.Upstream
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * A chave do provedor (OpenRouter) no celular, cifrada por uma chave do Keystore do Android que nunca sai do aparelho
 * (files/chave.bin). Ela chega pelo adb, sem passar por linha de comando nem terminal (`tools/app/cerebro.py enviar`
 * grava files/chave.txt pela entrada padrão), ou digitada na tela do app; o texto claro é cifrado e apagado na hora.
 * Nunca vai no APK.
 */
object ProviderKey {
    private const val ALIAS = "lmphone-provedor"
    private const val PLAIN = "chave.txt"
    private const val SEALED = "chave.bin"

    private fun secret(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }

    /** Cifra e guarda a chave. */
    fun save(context: Context, key: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, secret()) }
        val sealed = cipher.doFinal(key.trim().toByteArray())
        File(context.filesDir, SEALED).writeBytes(byteArrayOf(cipher.iv.size.toByte()) + cipher.iv + sealed)
    }

    /** A chave que o PC deixou em texto claro, se houver: cifrada e apagada. */
    fun importPlain(context: Context) {
        val plain = File(context.filesDir, PLAIN)
        if (!plain.exists()) return
        try {
            val key = plain.readText().trim()
            if (key.isNotEmpty()) save(context, key)
        } finally {
            plain.delete()
        }
    }

    fun load(context: Context): String? {
        importPlain(context)
        val file = File(context.filesDir, SEALED)
        if (!file.exists()) return null
        return try {
            val bytes = file.readBytes()
            val ivSize = bytes[0].toInt()
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, secret(), GCMParameterSpec(128, bytes, 1, ivSize))
            String(cipher.doFinal(bytes, 1 + ivSize, bytes.size - 1 - ivSize))
        } catch (e: Exception) {
            null
        }
    }

    fun present(context: Context) = load(context) != null
}

/** O caminho até o OpenRouter, com a chave do Keystore. Uma ligação caída antes da resposta é tentada mais uma vez. */
class OpenRouter(private val context: Context, private val base: String) : Upstream {
    override fun post(path: String, body: String): Pair<Int, ByteArray> {
        val key = ProviderKey.load(context) ?: throw IllegalStateException("a chave do provedor não está no celular")
        var attempt = 0
        while (true) {
            val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 15_000
                readTimeout = 300_000
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer $key")
            }
            try {
                connection.outputStream.use { it.write(body.toByteArray()) }
                val status = connection.responseCode
                val stream = if (status < 400) connection.inputStream else connection.errorStream
                return status to (stream?.use { it.readBytes() } ?: ByteArray(0))
            } catch (e: IOException) {
                if (attempt++ >= 1) throw e
                Thread.sleep(1000)
            } finally {
                connection.disconnect()
            }
        }
    }
}
