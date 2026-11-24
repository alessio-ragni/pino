package dev.pino.app

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import android.util.Log
import org.vosk.Model
import org.vosk.Recognizer
import kotlin.math.max
import kotlin.math.sqrt

/**
 * The ears: one microphone, always open (unless switched off), and four ways of using it.
 *
 * - WAKE: waits for the name. Speech only goes through the on-tablet recognizer, closed grammar.
 * - FOLLOW: right after an answer (or while a confirmation is open) just talk, no name needed.
 * - RECORDING: sends the voice to the server until you stop talking.
 * - BUSY: Pino thinks or speaks. If it hears its name it records with [Why.BARGE]: the voice is
 *   turned down, not stopped, and the server decides whether someone really called (or it heard
 *   itself).
 */
class Ears(private val listener: Listener) {
    interface Listener {
        /**
         * Starts sending: `lead` is the audio just before, so the name is not lost. `why` tells
         * the server why it is listening (see [Why]).
         */
        fun onBegin(lead: ByteArray, why: String)
        fun onMic(pcm: ByteArray)
        fun onEnd()
        /** The name heard while Pino speaks or thinks. */
        fun onBargeIn()
        fun onFollowUpExpired()
        /** «Basta», «stop» heard while he talks, thinks or rings. */
        fun onStopWord()
    }

    enum class Mode { OFF, WAKE, FOLLOW, RECORDING, BUSY }

    /** Why it started listening: the server checks the name again for [NAME] and [BARGE]. */
    object Why {
        const val NAME = "name"
        const val FOLLOW = "follow"
        const val BUTTON = "button"
        const val KEY = "key"
        const val BARGE = "barge"
    }

    @Volatile var mode = Mode.OFF
        private set

    @Volatile private var model: Model? = null
    @Volatile private var recognizer: Recognizer? = null
    @Volatile private var running = false
    private var thread: Thread? = null

    // To tell when you talk and when you have stopped.
    private var noise = 300.0
    private var speechMs = 0
    private var silenceMs = 0
    private var heardSpeech = false
    private var modeMs = 0
    private var followLimitMs = FOLLOW_MS
    private val lead = ArrayDeque<ByteArray>()
    private var maybeMs = 0
    private var deafMs = 0
    private var why = Why.NAME
    private var stopHeard = false

    val hasWakeWord: Boolean get() = recognizer != null

    fun loadModel(path: String) {
        val m = Model(path)
        val r = Recognizer(m, INPUT_RATE.toFloat(), Wake.grammar())
        r.setWords(true)
        model = m
        recognizer = r
    }

    @Synchronized
    fun set(next: Mode, followLimit: Int = FOLLOW_MS) {
        if (next == mode && next != Mode.FOLLOW) return
        mode = next
        modeMs = 0
        speechMs = 0
        silenceMs = 0
        heardSpeech = false
        followLimitMs = followLimit
        maybeMs = 0
        if (next == Mode.WAKE || next == Mode.BUSY) runCatching { recognizer?.reset() }
        // After Pino spoke, the audio before is his voice: it is not sent to the server, and the
        // first moment is skipped because the speaker is still finishing.
        if (next == Mode.FOLLOW) {
            lead.clear()
            deafMs = TAIL_MS
        }
    }

    /** Is the microphone open? Switched off, Android no longer shows the green dot. */
    val micOpen: Boolean get() = running

    @SuppressLint("MissingPermission")
    fun start() {
        if (running) return
        running = true
        thread = Thread({ loop() }, "pino-ears").apply { start() }
    }

    /** Really closes the microphone, but keeps the wake word ready for when it opens again. */
    fun closeMic() {
        set(Mode.OFF)
        running = false
        // The microphone thread itself may ask (end of the follow-up): then leaving the loop is enough.
        if (Thread.currentThread() != thread) thread?.join(1000)
        thread = null
    }

    fun stop() {
        closeMic()
        recognizer?.close()
        model?.close()
        recognizer = null
        model = null
    }

    @SuppressLint("MissingPermission")
    private fun loop() {
        val min = AudioRecord.getMinBufferSize(INPUT_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            INPUT_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            max(min, CHUNK_BYTES * 4),
        )
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "microphone not available")
            Hub.error.value = errorMic
            running = false
            return
        }
        // His own voice comes back into the microphone: the tablet's echo canceller and noise
        // suppressor take some of it away, when the tablet has them.
        val aec = if (AcousticEchoCanceler.isAvailable()) AcousticEchoCanceler.create(rec.audioSessionId) else null
        aec?.enabled = true
        val ns = if (NoiseSuppressor.isAvailable()) NoiseSuppressor.create(rec.audioSessionId) else null
        ns?.enabled = true
        Log.i(TAG, "echo canceller: ${aec?.enabled ?: "none"}, noise suppressor: ${ns?.enabled ?: "none"}")
        rec.startRecording()
        val buf = ByteArray(CHUNK_BYTES)
        try {
            while (running) {
                val n = rec.read(buf, 0, buf.size)
                if (n <= 0) continue
                val chunk = buf.copyOf(n)
                step(chunk)
            }
        } finally {
            Hub.level.value = 0f
            aec?.release()
            ns?.release()
            rec.stop()
            rec.release()
        }
    }

    @Synchronized
    private fun step(chunk: ByteArray) {
        val ms = chunk.size / 2 * 1000 / INPUT_RATE
        modeMs += ms
        val level = rms(chunk)
        Hub.level.value = (level / LOUD_RMS).toFloat().coerceIn(0f, 1f)
        val loud = level > max(noise * SPEECH_OVER_NOISE, MIN_SPEECH_RMS)
        if (!loud && mode != Mode.RECORDING) noise = noise * 0.95 + level * 0.05

        when (mode) {
            Mode.OFF -> remember(chunk)
            Mode.WAKE -> {
                remember(chunk)
                if (wake(chunk)) begin(Why.NAME)
                else if (stopHeard) listener.onStopWord()
            }
            Mode.BUSY -> {
                remember(chunk)
                if (wake(chunk)) {
                    listener.onBargeIn()
                    begin(Why.BARGE)
                } else if (stopHeard) {
                    listener.onStopWord()
                }
            }
            Mode.FOLLOW -> {
                if (deafMs > 0) {
                    deafMs -= ms
                    return
                }
                remember(chunk)
                speechMs = if (loud) speechMs + ms else 0
                if (speechMs >= FOLLOW_TRIGGER_MS) {
                    begin(Why.FOLLOW)
                } else if (modeMs >= followLimitMs) {
                    set(Mode.WAKE)
                    listener.onFollowUpExpired()
                }
            }
            Mode.RECORDING -> {
                listener.onMic(chunk)
                if (loud) {
                    heardSpeech = true
                    silenceMs = 0
                } else {
                    silenceMs += ms
                }
                // Over his own voice silence never comes: a call over him is short anyway.
                val limit = if (why == Why.BARGE) MAX_BARGE_MS else MAX_RECORDING_MS
                val done = (heardSpeech && silenceMs >= END_SILENCE_MS) ||
                    (!heardSpeech && modeMs >= NOTHING_SAID_MS) ||
                    modeMs >= limit
                if (done) finish()
            }
        }
    }

    /** From the circle: start listening now, or stop if it was already listening. */
    @Synchronized
    fun toggle() {
        if (mode == Mode.RECORDING) finish() else begin(Why.BUTTON)
    }

    /** Listen right away, no name (side key). If already listening, carry on. */
    @Synchronized
    fun listenNow() {
        if (mode != Mode.RECORDING) begin(Why.KEY)
    }

    private fun begin(why: String) {
        val before = lead.fold(ByteArray(0)) { acc, b -> acc + b }
        lead.clear()
        set(Mode.RECORDING)
        this.why = why
        heardSpeech = before.isNotEmpty() && rms(before) > max(noise * SPEECH_OVER_NOISE, MIN_SPEECH_RMS)
        listener.onBegin(before, why)
    }

    private fun finish() {
        set(Mode.BUSY)
        listener.onEnd()
    }

    /**
     * The name heard last stays "maybe" until the next word comes: if that is a decoy it was not a
     * call, if nothing came after [SETTLE_MS] it was.
     */
    private fun wake(chunk: ByteArray): Boolean {
        stopHeard = false
        val r = recognizer ?: return false
        val final = r.acceptWaveForm(chunk, chunk.size)
        val json = if (final) r.result else r.partialResult
        if (final && Wake.stop(json)) {
            Log.i(TAG, "stop word")
            stopHeard = true
            return false
        }
        var verdict = Wake.verdict(json)
        if (verdict == Wake.Verdict.MAYBE) {
            maybeMs += CHUNK_MS
            if (maybeMs >= SETTLE_MS) verdict = Wake.Verdict.YES
        } else {
            maybeMs = 0
        }
        val heard = verdict == Wake.Verdict.YES
        if (heard) {
            Log.i(TAG, "called")
            r.reset()
            maybeMs = 0
        }
        return heard
    }

    private fun remember(chunk: ByteArray) {
        lead.addLast(chunk)
        while (lead.size * CHUNK_MS > LEAD_MS) lead.removeFirst()
    }

    companion object {
        private const val TAG = "pino.ears"
        const val CHUNK_MS = 100
        const val CHUNK_BYTES = INPUT_RATE / 1000 * CHUNK_MS * 2
        // The name may be recognized a second after it was said: the audio before is kept.
        const val LEAD_MS = 3000
        const val SETTLE_MS = 700
        const val TAIL_MS = 400
        // After an answer the conversation stays open: it keeps listening without the name until you
        // say «stop» or stay quiet this long. Only a real voice starts a turn, and the server drops
        // the echo and what was not for Pino.
        const val FOLLOW_MS = 20_000
        const val FOLLOW_TRIGGER_MS = 400
        // How long a pause means "I'm done". Shorter answers sooner; too short cuts you off mid-thought.
        const val END_SILENCE_MS = 1200
        const val MAX_BARGE_MS = 6000
        const val NOTHING_SAID_MS = 5000
        const val MAX_RECORDING_MS = 5 * 60 * 1000
        const val SPEECH_OVER_NOISE = 3.0
        // From afar a voice arrives around 300-900, the house's silence below 50.
        const val MIN_SPEECH_RMS = 200.0
        const val LOUD_RMS = 3000.0

        /** Set by the service from the resources, so the ears can say what went wrong. */
        @Volatile var errorMic: String = "The microphone won't open"

        fun rms(pcm: ByteArray): Double {
            if (pcm.size < 2) return 0.0
            var sum = 0.0
            var i = 0
            while (i + 1 < pcm.size) {
                val s = ((pcm[i + 1].toInt() shl 8) or (pcm[i].toInt() and 0xff)).toShort().toDouble()
                sum += s * s
                i += 2
            }
            return sqrt(sum / (pcm.size / 2))
        }
    }
}
