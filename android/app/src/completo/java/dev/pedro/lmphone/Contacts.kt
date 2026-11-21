package dev.pedro.lmphone

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.ContactsContract
import dev.pedro.lmphone.cerebro.Masker
import dev.pedro.lmphone.cerebro.Masking
import dev.pedro.lmphone.cerebro.Py
import dev.pedro.lmphone.cerebro.Vault
import java.io.File

/**
 * O cofre a partir dos contatos do próprio aparelho, como `lmphone/sources.py` no PC: nomes, telefones e e-mails dos
 * contatos e o nome do dono (perfil), somados ao cofre que veio do PC (as contas, que um app não lê). Só com
 * `READ_CONTACTS`. As palavras dos nomes dos apps ficam fora (um contato "Gmail" não mascara o app).
 */
object Contacts {
    fun refresh(context: Context, vaultFile: File, stoplist: List<String>): Map<String, Int> {
        if (context.checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) return emptyMap()
        val vault = Vault(vaultFile)
        val masker = Masker(vault, stoplist + appWords(context))
        val counts = LinkedHashMap<String, Int>()
        fun count(key: String) = counts.merge(key, 1, Int::plus)
        val email = Py.re(Masking.EMAIL)

        for (name in column(context, ContactsContract.Profile.CONTENT_URI, ContactsContract.Profile.DISPLAY_NAME)) {
            masker.addName(name)
            count("perfil do dono")
        }
        for (name in column(context, ContactsContract.Contacts.CONTENT_URI, ContactsContract.Contacts.DISPLAY_NAME)) {
            if (Py.fullmatch(email, name) != null) vault.add("email", Py.lower(name)) else masker.addName(name)
            count("contatos: nome")
        }
        for (number in column(context, ContactsContract.CommonDataKinds.Phone.CONTENT_URI, ContactsContract.CommonDataKinds.Phone.NUMBER)) {
            masker.addPhone(number)
            count("contatos: telefone")
        }
        for (address in column(context, ContactsContract.CommonDataKinds.Email.CONTENT_URI, ContactsContract.CommonDataKinds.Email.ADDRESS)) {
            vault.add("email", Py.lower(address))
            count("contatos: e-mail")
        }
        vault.save()
        return counts
    }

    private fun column(context: Context, uri: android.net.Uri, name: String): List<String> = try {
        context.contentResolver.query(uri, arrayOf(name), null, null, null)?.use { cursor ->
            val out = ArrayList<String>()
            while (cursor.moveToNext()) cursor.getString(0)?.trim()?.takeIf { it.isNotEmpty() }?.let { out.add(it) }
            out
        } ?: emptyList()
    } catch (e: Exception) {
        emptyList()
    }

    private fun appWords(context: Context): List<String> {
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return context.packageManager.queryIntentActivities(launcher, PackageManager.ResolveInfoFlags.of(0))
            .flatMap { Masking.words(it.loadLabel(context.packageManager).toString()) }
    }
}
