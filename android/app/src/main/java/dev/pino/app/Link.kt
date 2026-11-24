package dev.pino.app

import android.util.Log
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit

/** The link to the server: a websocket that reconnects on its own when it drops. */
class Link(private val listener: Listener, private val text: (Int) -> String) {
    interface Listener {
        fun onOpen()
        fun onText(text: String)
        fun onAudio(pcm: ByteArray)
        fun onClosed(reason: String, retry: Boolean)
    }

    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    @Volatile private var socket: WebSocket? = null
    @Volatile private var url: String? = null
    @Volatile private var attempt = 0
    @Volatile private var wanted = false
    @Volatile private var generation = 0

    val connected: Boolean get() = socket != null

    fun connect(url: String) {
        this.url = url
        wanted = true
        attempt = 0
        generation++
        socket?.cancel()
        socket = null
        open()
    }

    fun close() {
        wanted = false
        generation++
        socket?.close(1000, "bye")
        socket = null
    }

    fun send(text: String): Boolean = socket?.send(text) ?: false

    fun send(pcm: ByteArray): Boolean = socket?.send(pcm.toByteString()) ?: false

    private fun open() {
        val target = url ?: return
        val request = try {
            Request.Builder().url(target).build()
        } catch (bad: IllegalArgumentException) {
            listener.onClosed(text(R.string.error_bad_address), retry = false)
            return
        }
        val g = generation
        client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                if (g != generation) {
                    webSocket.cancel()
                    return
                }
                socket = webSocket
                attempt = 0
                listener.onOpen()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                if (g == generation) listener.onText(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                if (g == generation) listener.onAudio(bytes.toByteArray())
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = lost(g, code, null)

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
                lost(g, response?.code ?: 0, t)
        })
    }

    private fun lost(g: Int, code: Int, error: Throwable?) {
        if (g != generation) return
        socket = null
        if (error != null) Log.w(TAG, "collegamento perso", error)
        // The server refuses the token by closing before accepting: it arrives as 403 (or 4401).
        if (code == 4401 || code == 403) {
            listener.onClosed(text(R.string.error_bad_token), retry = false)
            return
        }
        if (!wanted) return
        listener.onClosed(text(R.string.state_offline), retry = true)
        val wait = BACKOFF_S[minOf(attempt, BACKOFF_S.lastIndex)]
        attempt++
        Hub.scope.launch {
            delay(wait * 1000L)
            if (wanted && socket == null && g == generation) open()
        }
    }

    companion object {
        private const val TAG = "pino.link"
        private val BACKOFF_S = longArrayOf(1, 2, 5, 10, 20)
    }
}
