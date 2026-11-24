package dev.pino.app

import android.content.Context
import androidx.a2ui.compose.runtime.A2uiMessageParser
import androidx.a2ui.compose.ui.catalog.A2uiBasicCatalogV1
import androidx.a2ui.model.processor.processInput
import androidx.a2ui.model.protocol.A2uiClientErrorMessage
import androidx.a2ui.model.protocol.A2uiClientEventMessage
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.material3.a2ui.catalog.A2uiAudioPlayerRenderer
import androidx.compose.material3.a2ui.catalog.A2uiImageRenderer
import androidx.compose.material3.a2ui.catalog.A2uiVideoRenderer
import androidx.compose.material3.a2ui.catalog.MaterialA2uiBasicCatalogV1Defaults
import androidx.compose.material3.a2ui.catalog.materialA2uiBasicCatalogV1
import androidx.compose.ui.unit.dp
import coil3.ImageLoader
import coil3.compose.AsyncImage
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import okhttp3.OkHttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import androidx.a2ui.compose.ui.A2uiMessageProcessor as newA2uiMessageProcessor
import androidx.a2ui.model.processor.A2uiMessageProcessor

/**
 * Where Pino is, as a person sees it. Three states matter: OFF (microphone closed), IDLE
 * (waiting for its name) and LISTENING; THINKING and SPEAKING are the answer on its way.
 */
enum class Phase(@StringRes val label: Int, @StringRes val hint: Int?) {
    SETUP(R.string.state_setup, null),
    CONNECTING(R.string.state_connecting, null),
    OFFLINE(R.string.state_offline, null),
    OFF(R.string.state_mic_off, R.string.state_mic_off_hint),
    IDLE(R.string.state_idle, R.string.state_idle_hint),
    LISTENING(R.string.state_listening, R.string.state_listening_hint),
    FOLLOW(R.string.state_follow, R.string.state_follow_hint),
    THINKING(R.string.state_thinking, R.string.state_stop_hint),
    SPEAKING(R.string.state_speaking, R.string.state_stop_hint),
    RINGING(R.string.state_ringing, R.string.state_ringing_hint),
}

sealed interface Command {
    /** The circle in the middle: listen without the name, finish, or stop, depending on the state. */
    data object Orb : Command
    /** From the side key (assistant): listen right away, without the name. */
    data object Listen : Command
    /** A written question (from adb, to try things without a voice). */
    data class Ask(val text: String) : Command
    data object Reconnect : Command
    /** The switch: microphone on (listens for the name) or off (really closed). */
    data class Mic(val on: Boolean) : Command
    data class CloseCard(val id: String) : Command
    data class Front(val id: String) : Command
    /** Show the A2UI gallery: every kind of card the renderer can draw, tablet only. */
    data object Gallery : Command
}

/** The state shared between the service that listens and the screen that shows. */
object Hub {
    private const val USER_AGENT = "Pino/2.0 (https://github.com/alessio-ragni/pino)"

    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val phase = MutableStateFlow(Phase.CONNECTING)
    val heard = MutableStateFlow("")
    val said = MutableStateFlow("")
    val error = MutableStateFlow<String?>(null)
    val earsProgress = MutableStateFlow<Int?>(null)
    val micOn = MutableStateFlow(true)
    /** How loud the microphone is right now, 0..1: the circle breathes with your voice. */
    val level = MutableStateFlow(0f)
    /** The cards, oldest first. Their bodies are the A2UI surfaces with the same id. */
    val cards = MutableStateFlow<List<CardMeta>>(emptyList())
    /** "Show this card": the pager moves to it. */
    val focus = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val commands = MutableSharedFlow<Command>(extraBufferCapacity = 8)

    /** Asked to listen before the link to the server was ready: listen as soon as it is. */
    @Volatile var listenWhenReady = false
        set(value) {
            field = value
            listenAskedAt = if (value) System.currentTimeMillis() else 0L
        }

    @Volatile var listenAskedAt = 0L

    /** An old request (the server was down) must not open the microphone later. */
    val listenStillWanted: Boolean
        get() = listenWhenReady && System.currentTimeMillis() - listenAskedAt < 15_000

    /** What goes to the server: taps on A2UI components and drawing errors. */
    var send: (String) -> Unit = {}

    @Volatile private var processor: A2uiMessageProcessor? = null
    private val parser = A2uiMessageParser()

    fun screen(context: Context): A2uiMessageProcessor = processor ?: synchronized(this) {
        processor ?: build(context.applicationContext).also { processor = it }
    }

    fun show(context: Context, message: ScreenMessage) {
        screen(context).processInput(parser, message.raw)
    }

    fun putCard(card: CardMeta) {
        val now = cards.value
        cards.value = if (now.any { it.id == card.id }) now.map { if (it.id == card.id) card else it } else now + card
    }

    fun dropCard(id: String) {
        cards.value = cards.value.filterNot { it.id == id }
    }

    /**
     * Pictures in cards come from anywhere on the web. Some sites (Wikimedia, for one) refuse a
     * request that does not say who is asking: every picture is fetched saying it is Pino.
     */
    @Volatile private var images: ImageLoader? = null

    private fun build(context: Context): A2uiMessageProcessor {
        images = ImageLoader.Builder(context)
            .components {
                add(
                    OkHttpNetworkFetcherFactory(
                        callFactory = {
                            OkHttpClient.Builder()
                                .addInterceptor { chain ->
                                    chain.proceed(chain.request().newBuilder().header("User-Agent", USER_AGENT).build())
                                }
                                .build()
                        },
                    ),
                )
            }
            .build()
        val catalog = materialA2uiBasicCatalogV1(
            image = MaterialA2uiBasicCatalogV1Defaults.image(imageRenderer),
            video = MaterialA2uiBasicCatalogV1Defaults.video(videoRenderer),
            audioPlayer = MaterialA2uiBasicCatalogV1Defaults.audioPlayer(audioRenderer),
            functions = A2uiBasicCatalogV1.Functions(context),
        )
        val p = newA2uiMessageProcessor(listOf(catalog))
        scope.launch { p.collectMessages() }
        scope.launch {
            p.outboundEvents.collect { event ->
                when (event) {
                    is A2uiClientEventMessage ->
                        send(Outgoing.action(event.type, event.surfaceId, event.componentId, event.context))
                    is A2uiClientErrorMessage ->
                        send(Outgoing.renderError(event.surfaceId, "${event.code}: ${event.message}"))
                    else -> Unit
                }
            }
        }
        return p
    }

    private val imageRenderer = A2uiImageRenderer { url, description, scale, modifier, onError ->
        AsyncImage(
            model = url,
            imageLoader = images ?: coil3.SingletonImageLoader.get(androidx.compose.ui.platform.LocalContext.current),
            contentDescription = description,
            contentScale = scale,
            modifier = modifier,
            onError = { onError(it.result.throwable) },
        )
    }

    // Video and audio inside the screen are not needed yet: the link is shown.
    private val videoRenderer = A2uiVideoRenderer { url, modifier, _ ->
        Text("Video: $url", modifier = modifier.padding(8.dp))
    }

    private val audioRenderer = A2uiAudioPlayerRenderer { url, _, modifier, _ ->
        Text("Audio: $url", modifier = modifier.padding(8.dp))
    }
}
