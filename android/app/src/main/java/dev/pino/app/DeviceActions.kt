package dev.pino.app

import android.content.Context
import android.content.Intent
import android.provider.AlarmClock
import android.util.Log

/**
 * What the server can ask the tablet to do on the device itself. For now: alarms on the Clock app,
 * so they ring even when Pino or the server are down, and opening the Clock app's list.
 *
 * Android only lets an app open another app's screen while it is in front. When Pino's screen
 * is not showing the request is refused, and Claude says so instead of pretending.
 */
object DeviceActions {
    private const val TAG = "pino.device"

    /** Set by the activity: Android blocks starting the Clock app from the background. */
    @Volatile var inFront = false

    fun run(context: Context, m: Incoming.Device): Boolean {
        if (!inFront) {
            Log.w(TAG, "${m.action}: the app is not in front, Android would block it")
            return false
        }
        val intent = when (m.action) {
            "set_alarm" -> Intent(AlarmClock.ACTION_SET_ALARM).apply {
                putExtra(AlarmClock.EXTRA_HOUR, m.hour)
                putExtra(AlarmClock.EXTRA_MINUTES, m.minute)
                if (m.label.isNotBlank()) putExtra(AlarmClock.EXTRA_MESSAGE, m.label)
                if (m.days.isNotEmpty()) putExtra(AlarmClock.EXTRA_DAYS, ArrayList(m.days.map(::calendarDay)))
                putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            }
            // Android lets no app delete another app's alarm: the Clock app's list opens instead.
            "show_alarms" -> Intent(AlarmClock.ACTION_SHOW_ALARMS)
            else -> return false
        }.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (intent.resolveActivity(context.packageManager) == null) {
            Log.w(TAG, "${m.action}: no Clock app answers")
            return false
        }
        return runCatching { context.startActivity(intent) }
            .onFailure { Log.w(TAG, "${m.action} refused", it) }
            .isSuccess
    }

    /** ISO weekday (Monday = 1 … Sunday = 7) to java.util.Calendar (Sunday = 1 … Saturday = 7). */
    fun calendarDay(iso: Int): Int = iso % 7 + 1
}
