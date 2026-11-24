package dev.pino.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * The heart on the tablet: a foreground service that keeps microphone and link to the server open
 * even when the screen shows another app. A fixed notification says it is listening.
 */
class PinoService : Service(), Link.Listener, Ears.Listener {
    private lateinit var prefs: Prefs
    private lateinit var link: Link
    private lateinit var ears: Ears
    private val voice = Voice()
    private val sounds = Sounds()
    private var wakeLock: PowerManager.WakeLock? = null
    private val jobs = mutableListOf<Job>()
    private var stopped = false

    // The turn's state.
    @Volatile private var turnOpen = false
    @Volatile private var confirmOpen = false
    // A confirmation closed in this turn: at the end it does not listen without the name.
    @Volatile private var confirmDone = false
    @Volatile private var endedAt = 0L
    // The name heard over his own voice: turned down, waiting for the server's verdict.
    @Volatile private var barging = false
    @Volatile private var ringId = 0
    @Volatile private var thinkingSince = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        Hub.micOn.value = prefs.micOn
        Ears.errorMic = getString(R.string.error_mic)
        link = Link(this) { getString(it) }
        ears = Ears(this)
        try {
            startForeground(NOTIFICATION_ID, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        } catch (bad: Exception) {
            // Android does not let a service restarted in the background open the microphone:
            // it starts again when the app is opened.
            Log.w(TAG, "cannot listen now", bad)
            stopped = true
            stopSelf()
            return
        }
        wakeLock = (getSystemService(Context.POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pino:listening")
            .apply { acquire() }

        Hub.send = { link.send(it) }
        Hub.screen(this)
        if (prefs.micOn) ears.start()
        jobs += Hub.scope.launch { prepareEars() }
        jobs += Hub.scope.launch { Hub.commands.collect { onCommand(it) } }
        jobs += Hub.scope.launch { watchVoice() }
        connect()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (stopped) return START_NOT_STICKY
        // From the notification or the quick settings tile.
        if (intent?.action == ACTION_MIC) Hub.commands.tryEmit(Command.Mic(intent.getBooleanExtra(EXTRA_ON, true)))
        return START_STICKY
    }

    override fun onDestroy() {
        if (stopped) {
            voice.close()
            super.onDestroy()
            return
        }
        jobs.forEach { it.cancel() }
        link.close()
        ears.stop()
        voice.close()
        sounds.stopThinking()
        sounds.stopRing()
        wakeLock?.release()
        super.onDestroy()
    }

    private fun connect() {
        if (!prefs.ready) {
            Hub.phase.value = Phase.SETUP
            link.close()
            return
        }
        Hub.phase.value = Phase.CONNECTING
        link.connect(socketUrl(prefs.server, prefs.token))
    }

    private suspend fun prepareEars() {
        try {
            if (!EarsModel.ready(this)) {
                Hub.earsProgress.value = 0
                EarsModel.fetch(this) { Hub.earsProgress.value = it }
            }
            ears.loadModel(EarsModel.dir(this).absolutePath)
            Hub.earsProgress.value = null
            if (link.connected && ears.mode == Ears.Mode.OFF) listen()
        } catch (bad: Exception) {
            Log.e(TAG, "wake word not available", bad)
            Hub.earsProgress.value = null
            Hub.error.value = getString(R.string.error_wake)
        }
    }

    private fun onCommand(command: Command) {
        when (command) {
            Command.Orb -> onOrb()
            Command.Reconnect -> connect()
            Command.Listen -> {
                if (!link.connected) {
                    Hub.listenWhenReady = true
                    return
                }
                Hub.listenWhenReady = false
                stopAll()
                if (!ears.micOpen) ears.start()
                ears.listenNow()
            }
            is Command.Ask -> {
                stopAll()
                link.send(Outgoing.text(command.text))
                Hub.heard.value = command.text
                Hub.phase.value = Phase.THINKING
                ears.set(Ears.Mode.BUSY)
                sounds.startThinking()
            }
            is Command.Mic -> setMic(command.on)
            is Command.CloseCard -> {
                link.send(Outgoing.closed(command.id))
                Hub.dropCard(command.id)
                deleteSurface(command.id)
            }
            is Command.Front -> link.send(Outgoing.front(command.id))
            Command.Gallery -> Hub.scope.launch(Dispatchers.Main) {
                Gallery.cards.forEach { (card, messages) ->
                    Hub.putCard(card)
                    messages.forEach { raw ->
                        runCatching { Hub.show(this@PinoService, ScreenMessage(raw, null, card.id)) }
                            .onFailure { Log.w(TAG, "gallery: ${card.id} not drawn", it) }
                    }
                }
                Hub.focus.tryEmit(Gallery.cards.first().first.id)
            }
        }
    }

    /** The circle: one button that does the obvious thing for the state Pino is in. */
    private fun onOrb() {
        when (Hub.phase.value) {
            Phase.RINGING -> stopRinging()
            Phase.THINKING, Phase.SPEAKING -> {
                stopAll()
                listen()
            }
            Phase.LISTENING -> ears.toggle()
            Phase.SETUP, Phase.OFFLINE, Phase.CONNECTING -> connect()
            Phase.IDLE, Phase.OFF, Phase.FOLLOW -> {
                voice.hush()
                // With the microphone off the circle opens it for one question only.
                if (!ears.micOpen) ears.start()
                ears.toggle()
            }
        }
    }

    /** Stops whatever is going on: voice, thinking, an open confirmation (as a no), the turn. */
    private fun stopAll() {
        voice.hush()
        voice.duck(false)
        barging = false
        sounds.stopThinking()
        if (turnOpen || confirmOpen) link.send(Outgoing.stop())
        turnOpen = false
    }

    private fun stopRinging() {
        sounds.stopRing()
        link.send(Outgoing.ringStop(ringId))
        listen()
    }

    /** The switch, like Alexa's: off means the microphone is closed, not just deaf. */
    private fun setMic(on: Boolean) {
        prefs.micOn = on
        Hub.micOn.value = on
        if (on) {
            if (!ears.micOpen) ears.start()
            if (link.connected && ears.mode != Ears.Mode.RECORDING) listen()
        } else if (ears.mode != Ears.Mode.RECORDING && !turnOpen) {
            listen()
        }
        // If it is listening or answering, the microphone closes at the end of the turn (in listen()).
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification())
        MicTile.refresh(this)
    }

    /**
     * Back to waiting for the name. With the microphone switched off it closes it instead, even
     * after a question asked with the circle.
     */
    private fun listen() {
        sounds.stopThinking()
        voice.duck(false)
        barging = false
        if (!prefs.micOn) {
            ears.closeMic()
            Hub.phase.value = if (link.connected) Phase.OFF else Phase.OFFLINE
            return
        }
        if (!ears.micOpen) ears.start()
        ears.set(Ears.Mode.WAKE)
        Hub.phase.value = if (link.connected) Phase.IDLE else Phase.OFFLINE
    }

    /** After an answer: a few seconds without the name, unless the microphone is off or there was a confirmation. */
    private fun followUp() {
        if (!prefs.micOn || confirmDone) {
            listen()
            return
        }
        ears.set(Ears.Mode.FOLLOW)
        Hub.phase.value = Phase.FOLLOW
    }

    /**
     * When the voice has finished: if the turn is closed it listens a few seconds without the name;
     * if a confirmation is open it listens until the answer comes.
     */
    private suspend fun watchVoice() {
        val scope = Hub.scope
        while (scope.isActive) {
            delay(150)
            if (Hub.phase.value == Phase.RINGING) {
                if (!sounds.ringingNow && !voice.busy) listen()
                continue
            }
            // Never stuck on «thinking»: with no word from the server for this long, it gives up.
            if (Hub.phase.value == Phase.THINKING) {
                if (thinkingSince == 0L) thinkingSince = System.currentTimeMillis()
                if (System.currentTimeMillis() - thinkingSince > STUCK_MS && !voice.busy) {
                    Log.w(TAG, "no answer for ${STUCK_MS / 1000} s: back to listening")
                    stopAll()
                    link.send(Outgoing.stop())
                    listen()
                }
            } else {
                thinkingSince = 0L
            }
            val m = ears.mode
            if (m != Ears.Mode.BUSY || voice.busy) continue
            val stale = System.currentTimeMillis() - endedAt > NO_ANSWER_MS
            when {
                // «Lo faccio?» said and done: wait for the answer without the name.
                confirmOpen && Hub.phase.value == Phase.SPEAKING -> {
                    ears.set(Ears.Mode.FOLLOW, followLimit = CONFIRM_LISTEN_MS)
                    Hub.phase.value = Phase.FOLLOW
                }
                !turnOpen && Hub.phase.value == Phase.SPEAKING -> followUp()
                // The server did not answer (empty or too short audio): listen again.
                !turnOpen && Hub.phase.value == Phase.THINKING && stale -> listen()
            }
        }
    }

    private fun deleteSurface(id: String) {
        val raw = """{"version":"v0.9.1","deleteSurface":{"surfaceId":"$id"}}"""
        Hub.scope.launch(Dispatchers.Main) {
            runCatching { Hub.show(this@PinoService, ScreenMessage(raw, "deleteSurface", id)) }
        }
    }

    // ── the link ────────────────────────────────────────────────────────────

    override fun onOpen() {
        Hub.error.value = null
    }

    override fun onText(text: String) {
        when (val m = parseIncoming(text)) {
            is Incoming.Ready -> {
                Hub.error.value = when {
                    !m.ears -> getString(R.string.error_no_ears)
                    !m.voice -> getString(R.string.error_no_voice)
                    else -> null
                }
                if (ears.mode == Ears.Mode.OFF || ears.mode == Ears.Mode.BUSY) listen()
                else Hub.phase.value = Phase.IDLE
                if (Hub.listenStillWanted) onCommand(Command.Listen) else Hub.listenWhenReady = false
            }
            is Incoming.Heard -> {
                Hub.heard.value = m.text
                if (barging) {
                    // The server read the sentence: someone really called. Now he goes quiet.
                    barging = false
                    voice.hush()
                    voice.duck(false)
                }
            }
            Incoming.Thinking -> {
                turnOpen = true
                confirmDone = false
                Hub.said.value = ""
                Hub.phase.value = Phase.THINKING
                sounds.startThinking()
                if (ears.mode != Ears.Mode.RECORDING) ears.set(Ears.Mode.BUSY)
            }
            is Incoming.Say -> {
                thinkingSince = 0L
                sounds.stopThinking()
                voice.rate(m.rate)
                Hub.said.value = m.text
                if (Hub.phase.value != Phase.RINGING) Hub.phase.value = Phase.SPEAKING
                if (ears.mode != Ears.Mode.RECORDING) ears.set(Ears.Mode.BUSY)
            }
            Incoming.SayEnd -> Unit
            is Incoming.Screen -> m.messages.forEach { msg ->
                if (msg.surfaceId == CONFIRM_SURFACE) {
                    if (msg.kind == "createSurface") confirmOpen = true
                    if (msg.kind == "deleteSurface") {
                        confirmOpen = false
                        confirmDone = true
                    }
                }
                Hub.scope.launch(Dispatchers.Main) {
                    runCatching { Hub.show(this@PinoService, msg) }
                        .onFailure {
                            Log.w(TAG, "A2UI message dropped", it)
                            link.send(Outgoing.renderError(msg.surfaceId, it.message ?: it.toString()))
                        }
                }
            }
            is Incoming.Card -> Hub.putCard(m.card)
            is Incoming.CardClosed -> {
                Hub.dropCard(m.id)
                deleteSurface(m.id)
            }
            Incoming.CardsReset -> {
                Hub.cards.value.forEach { deleteSurface(it.id) }
                Hub.cards.value = emptyList()
            }
            is Incoming.Focus -> Hub.focus.tryEmit(m.id)
            is Incoming.Ring -> {
                ringId = m.id
                Hub.phase.value = Phase.RINGING
                sounds.startRing()
                ears.set(Ears.Mode.WAKE)
            }
            is Incoming.Device -> Hub.scope.launch(Dispatchers.Main) {
                link.send(Outgoing.deviceResult(m.id, DeviceActions.run(this@PinoService, m)))
            }
            is Incoming.Done -> {
                turnOpen = false
                sounds.stopThinking()
                // No voice (or already finished): listen right away without the name.
                if (Hub.phase.value != Phase.SPEAKING && ears.mode == Ears.Mode.BUSY) followUp()
            }
            is Incoming.Ignored -> {
                Log.i(TAG, "discarded by the server: ${m.reason}")
                sounds.stopThinking()
                if (m.reason == "stop" && sounds.ringingNow) {
                    stopRinging()
                    return
                }
                if (barging && m.reason == "eco") {
                    // It was his own voice: back up, and carry on as if nothing happened.
                    barging = false
                    voice.duck(false)
                    if (turnOpen || voice.busy) {
                        ears.set(Ears.Mode.BUSY)
                        Hub.phase.value = Phase.SPEAKING
                        return
                    }
                }
                // Not for Pino, or «stop»: no answer is coming. The turn the server opened for it
                // is over too (leaving it open kept the circle on «thinking» for good).
                voice.hush()
                turnOpen = false
                Hub.heard.value = ""
                if (m.reason == "stop") listen() else if (m.reason == "non per me" && prefs.micOn) followUp() else listen()
            }
            is Incoming.Failure -> Hub.error.value = m.text
            is Incoming.Unknown -> Unit
        }
    }

    override fun onAudio(pcm: ByteArray) = voice.play(pcm)

    override fun onClosed(reason: String, retry: Boolean) {
        Hub.error.value = reason
        Hub.phase.value = if (retry) Phase.OFFLINE else Phase.SETUP
        voice.hush()
        sounds.stopThinking()
        ears.set(Ears.Mode.OFF)
        turnOpen = false
    }

    // ── the ears ────────────────────────────────────────────────────────────

    override fun onBegin(lead: ByteArray, why: String) {
        if (why != Ears.Why.BARGE) {
            Hub.phase.value = Phase.LISTENING
            Hub.heard.value = ""
            if (why == Ears.Why.NAME) sounds.chime()
        }
        sounds.stopThinking()
        link.send(Outgoing.start(why))
        if (lead.isNotEmpty()) link.send(lead)
    }

    override fun onMic(pcm: ByteArray) {
        link.send(pcm)
    }

    override fun onEnd() {
        endedAt = System.currentTimeMillis()
        link.send(Outgoing.end())
        if (!barging) {
            Hub.phase.value = Phase.THINKING
            sounds.startThinking()
        }
    }

    override fun onBargeIn() {
        // Not quiet yet: only turned down, until the server says someone really called.
        barging = true
        voice.duck(true)
    }

    override fun onFollowUpExpired() {
        listen()
    }

    /** «Basta» while he talks, thinks or rings: quiet at once, and no answer to it. */
    override fun onStopWord() {
        Hub.scope.launch {
            when (Hub.phase.value) {
                Phase.RINGING -> stopRinging()
                Phase.THINKING, Phase.SPEAKING -> {
                    stopAll()
                    link.send(Outgoing.stop())
                    listen()
                }
                else -> Unit
            }
        }
    }

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW).apply {
                description = getString(R.string.channel_description)
            },
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val on = prefs.micOn
        val toggle = PendingIntent.getService(
            this, 1, micIntent(this, !on), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val action = Notification.Action.Builder(
            null, getString(if (on) R.string.notif_turn_off else R.string.notif_turn_on), toggle,
        ).build()
        return Notification.Builder(this, CHANNEL)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(if (on) R.string.notif_on else R.string.notif_off))
            .setSmallIcon(R.drawable.ic_pino)
            .setContentIntent(open)
            .addAction(action)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val TAG = "pino"
        private const val CHANNEL = "ascolto"
        private const val NOTIFICATION_ID = 1
        private const val CONFIRM_LISTEN_MS = 60_000
        private const val NO_ANSWER_MS = 20_000L
        private const val STUCK_MS = 45_000L
        const val ACTION_MIC = "dev.pino.app.MICROFONO"
        const val EXTRA_ON = "acceso"

        fun micIntent(context: Context, on: Boolean): Intent =
            Intent(context, PinoService::class.java).setAction(ACTION_MIC).putExtra(EXTRA_ON, on)

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, PinoService::class.java))
        }
    }
}
