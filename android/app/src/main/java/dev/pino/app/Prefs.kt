package dev.pino.app

import android.content.Context

/** Server address and token: typed on the tablet, never in the code. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("pino", Context.MODE_PRIVATE)

    var server: String
        get() = sp.getString("server", "").orEmpty()
        set(value) = sp.edit().putString("server", value.trim()).apply()

    var token: String
        get() = sp.getString("token", "").orEmpty()
        set(value) = sp.edit().putString("token", value.trim()).apply()

    /** The microphone switch: it stays as it is across restarts. */
    var micOn: Boolean
        get() = sp.getBoolean("mic", true)
        set(value) = sp.edit().putBoolean("mic", value).apply()

    val ready: Boolean get() = server.isNotBlank() && token.isNotBlank()
}
