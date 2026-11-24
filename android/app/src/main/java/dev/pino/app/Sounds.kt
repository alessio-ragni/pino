package dev.pino.app

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

/**
 * Small sounds made on the tablet, never recorded files: a chime when it hears its name, a soft
 * "thinking" pulse from the end of your sentence to the first word of the answer, and the bell of
 * timers and reminders. Each runs on its own thread and stops when told.
 */
class Sounds {
    @Volatile private var thinking: Thread? = null
    @Volatile private var ringing: Thread? = null

    /** A short high note: "I heard you". */
    fun chime() = once(tone(880.0, 110, 0.18) + tone(1320.0, 90, 0.12))

    /** A single soft note every few seconds, until [stopThinking]. */
    fun startThinking() {
        if (thinking != null) return
        // One soft note every few seconds: often enough to say «still on it», rarely enough not to nag.
        val pulse = tone(587.0, 90, 0.05) + silence(3600)
        thinking = loop(pulse, maxMs = 60_000) { thinking = null }
    }

    fun stopThinking() {
        thinking?.interrupt()
        thinking = null
    }

    /** The bell: a bright pattern repeated until [stopRing], at most a minute. */
    fun startRing() {
        if (ringing != null) return
        val bell = tone(988.0, 160, 0.35) + silence(80) + tone(988.0, 160, 0.35) + silence(80) +
            tone(1319.0, 260, 0.35) + silence(700)
        ringing = loop(bell, maxMs = 60_000) { ringing = null }
    }

    fun stopRing() {
        ringing?.interrupt()
        ringing = null
    }

    val ringingNow: Boolean get() = ringing != null

    private fun once(pcm: ShortArray) {
        Thread({ play(pcm) }, "pino-sound").start()
    }

    private fun loop(pcm: ShortArray, maxMs: Int, done: () -> Unit): Thread =
        Thread({
            val track = open(pcm.size)
            try {
                val started = System.currentTimeMillis()
                track.play()
                while (!Thread.currentThread().isInterrupted && System.currentTimeMillis() - started < maxMs) {
                    var off = 0
                    while (off < pcm.size && !Thread.currentThread().isInterrupted) {
                        val n = track.write(pcm, off, min(pcm.size - off, RATE / 10))
                        if (n <= 0) break
                        off += n
                    }
                }
            } finally {
                runCatching {
                    track.pause()
                    track.flush()
                }
                track.release()
                done()
            }
        }, "pino-sound").apply { start() }

    private fun play(pcm: ShortArray) {
        val track = open(pcm.size)
        try {
            track.play()
            track.write(pcm, 0, pcm.size)
            Thread.sleep(pcm.size * 1000L / RATE + 50)
        } catch (_: InterruptedException) {
        } finally {
            track.release()
        }
    }

    private fun open(samples: Int): AudioTrack {
        val min = AudioTrack.getMinBufferSize(RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(RATE)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(maxOf(min, samples * 2).coerceAtMost(RATE * 2))
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
    }

    companion object {
        const val RATE = 24_000

        /** A sine note with a short fade in and out, so it never clicks. */
        fun tone(freq: Double, ms: Int, volume: Double): ShortArray {
            val n = RATE * ms / 1000
            val fade = RATE * 12 / 1000
            return ShortArray(n) { i ->
                val env = min(1.0, min(i, n - 1 - i).toDouble() / fade)
                (sin(2 * PI * freq * i / RATE) * env * volume * Short.MAX_VALUE).toInt().toShort()
            }
        }

        fun silence(ms: Int) = ShortArray(RATE * ms / 1000)
    }
}
