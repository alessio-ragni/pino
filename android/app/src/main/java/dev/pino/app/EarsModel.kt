package dev.pino.app

import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.zip.ZipInputStream

/**
 * vosk's small Italian model (about 50 MB) for the wake word. It is neither in the repo nor in the
 * app: it is downloaded once at first start and stays on the tablet.
 */
object EarsModel {
    private const val NAME = "vosk-model-small-it-0.22"
    private const val URL = "https://alphacephei.com/vosk/models/$NAME.zip"

    fun dir(context: Context): File = File(context.filesDir, NAME)

    fun ready(context: Context): Boolean = File(dir(context), "conf").isDirectory

    /** Downloads and unpacks. `progress` goes from 0 to 100. */
    fun fetch(context: Context, progress: (Int) -> Unit): File {
        val target = dir(context)
        if (ready(context)) return target
        val zip = File(context.cacheDir, "$NAME.zip")
        val response = OkHttpClient().newCall(Request.Builder().url(URL).build()).execute()
        response.use { r ->
            check(r.isSuccessful) { "download del modello fallito: HTTP ${r.code}" }
            val body = r.body
            val total = body.contentLength().takeIf { it > 0 } ?: 50_000_000L
            body.byteStream().use { input ->
                zip.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    var done = 0L
                    var last = -1
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        done += n
                        val pct = (done * 90 / total).toInt()
                        if (pct != last) progress(pct).also { last = pct }
                    }
                }
            }
        }
        val tmp = File(context.filesDir, "$NAME.tmp").apply { deleteRecursively(); mkdirs() }
        ZipInputStream(zip.inputStream().buffered()).use { zin ->
            while (true) {
                val entry = zin.nextEntry ?: break
                // Inside the zip everything sits under a folder named after the model: it is stripped.
                val rel = entry.name.substringAfter('/', "")
                if (rel.isEmpty()) continue
                val out = File(tmp, rel)
                require(out.canonicalPath.startsWith(tmp.canonicalPath)) { "zip non valido" }
                if (entry.isDirectory) out.mkdirs() else {
                    out.parentFile?.mkdirs()
                    out.outputStream().use { zin.copyTo(it) }
                }
            }
        }
        zip.delete()
        target.deleteRecursively()
        check(tmp.renameTo(target)) { "non riesco a sistemare il modello" }
        progress(100)
        return target
    }
}
