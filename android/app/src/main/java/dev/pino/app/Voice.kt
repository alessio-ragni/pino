package dev.pino.app

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * The mouth: plays the PCM coming from the server, in pieces, as it arrives. On its own thread, so
 * the websocket never waits for the speaker.
 */
class Voice {
    private sealed interface Item {
        class Pcm(val bytes: ByteArray) : Item
        class Rate(val rate: Int) : Item
    }

    private val queue = LinkedBlockingQueue<Item>()
    @Volatile private var track: AudioTrack? = null
    @Volatile private var rate = 24_000
    @Volatile private var written = 0L
    @Volatile private var running = true
    @Volatile private var generation = 0
    @Volatile private var writing = false
    @Volatile private var volume = 1f

    private val thread = Thread({ loop() }, "pino-voice").apply { start() }

    fun rate(rate: Int?) {
        if (rate != null && rate > 0) queue.put(Item.Rate(rate))
    }

    fun play(pcm: ByteArray) {
        queue.put(Item.Pcm(pcm))
    }

    /** Quiet at once: throws away what is left to say. */
    fun hush() {
        generation++
        queue.clear()
        track?.let {
            runCatching {
                it.pause()
                it.flush()
                it.play()
            }
        }
        written = 0
    }

    /** Turned down while someone may be talking over it, back up if it was a false alarm. */
    fun duck(down: Boolean) {
        volume = if (down) DUCKED else 1f
        track?.let { runCatching { it.setVolume(volume) } }
    }

    /** Is something still playing, or still queued? */
    val busy: Boolean
        get() = queue.isNotEmpty() || writing || sounding

    private val sounding: Boolean
        get() {
            val t = track ?: return false
            val played = runCatching { t.playbackHeadPosition.toLong() and 0xffffffffL }.getOrDefault(written)
            return played < written
        }

    fun close() {
        running = false
        thread.interrupt()
        track?.release()
        track = null
    }

    private fun loop() {
        while (running) {
            val item = try {
                queue.poll(500, TimeUnit.MILLISECONDS) ?: continue
            } catch (_: InterruptedException) {
                break
            }
            when (item) {
                is Item.Rate -> if (item.rate != rate || track == null) {
                    // Changed only with an empty queue: wait for the sentence before to finish.
                    drain()
                    rate = item.rate
                    track?.release()
                    track = null
                }
                is Item.Pcm -> {
                    writing = true
                    val g = generation
                    val t = track ?: open().also { track = it }
                    var off = 0
                    while (off < item.bytes.size && g == generation && running) {
                        val n = t.write(item.bytes, off, item.bytes.size - off)
                        if (n <= 0) break
                        off += n
                    }
                    if (g == generation) written += item.bytes.size / 2
                    writing = false
                }
            }
        }
    }

    private fun drain() {
        val t = track ?: return
        var waited = 0
        while (sounding && waited < 10_000 && running) {
            Thread.sleep(20)
            waited += 20
        }
        runCatching { t.stop() }
        written = 0
    }

    private fun open(): AudioTrack {
        val min = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val t = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(rate)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setBufferSizeInBytes(min * 4)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        t.setVolume(volume)
        t.play()
        written = 0
        return t
    }

    companion object {
        private const val DUCKED = 0.2f
    }
}
