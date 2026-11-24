package dev.pino.app

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put

/** The messages between tablet and server, as described in docs/protocol.md. */

const val INPUT_RATE = 16_000
const val CONFIRM_SURFACE = "conferma"

/** An A2UI message for the renderer, with the little worth knowing without opening it. */
data class ScreenMessage(val raw: String, val kind: String?, val surfaceId: String?)

/** One question and its answer, under a card. */
data class ThreadItem(val q: String, val a: String)

/** A card: one topic on the screen. Its body (if any) is the A2UI surface with the same id. */
data class CardMeta(val id: String, val title: String, val thread: List<ThreadItem>)

sealed interface Incoming {
    data class Ready(val voice: Boolean, val ears: Boolean, val rate: Int?, val a2ui: String?) : Incoming
    data class Heard(val text: String) : Incoming
    data object Thinking : Incoming
    data class Say(val text: String, val rate: Int?) : Incoming
    data object SayEnd : Incoming
    data class Screen(val messages: List<ScreenMessage>) : Incoming
    data class Card(val card: CardMeta) : Incoming
    data class CardClosed(val id: String) : Incoming
    data object CardsReset : Incoming
    data class Focus(val id: String) : Incoming
    data class Ring(val id: Int, val kind: String, val label: String) : Incoming
    data class Device(
        val id: Int,
        val action: String,
        val hour: Int,
        val minute: Int,
        val days: List<Int>,
        val label: String,
    ) : Incoming
    data class Done(val ms: Long?) : Incoming
    /** Not for Pino (or «stop»): no answer, back to waiting for the name. */
    data class Ignored(val reason: String) : Incoming
    data class Failure(val text: String) : Incoming
    data class Unknown(val type: String?) : Incoming
}

private val SCREEN_KINDS = listOf("createSurface", "updateComponents", "updateDataModel", "deleteSurface")

private fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.contentOrNull

private fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.intOrNull

private fun JsonObject.bool(key: String): Boolean = (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

fun parseIncoming(text: String): Incoming {
    val obj =
        try {
            Json.parseToJsonElement(text).jsonObject
        } catch (_: Exception) {
            return Incoming.Unknown(null)
        }
    return when (val type = obj.str("type")) {
        "ready" -> Incoming.Ready(obj.bool("voice"), obj.bool("ears"), obj.int("rate"), obj.str("a2ui"))
        "heard" -> Incoming.Heard(obj.str("text").orEmpty())
        "thinking" -> Incoming.Thinking
        "say" -> Incoming.Say(obj.str("text").orEmpty(), obj.int("rate"))
        "say_end" -> Incoming.SayEnd
        "a2ui" -> Incoming.Screen(screenMessages(obj["messages"]))
        "card" -> Incoming.Card(
            CardMeta(
                obj.str("id").orEmpty(),
                obj.str("title").orEmpty(),
                (obj["thread"] as? JsonArray).orEmpty().mapNotNull { item ->
                    val o = item as? JsonObject ?: return@mapNotNull null
                    ThreadItem(o.str("q").orEmpty(), o.str("a").orEmpty())
                },
            ),
        )
        "card_closed" -> Incoming.CardClosed(obj.str("id").orEmpty())
        "cards_reset" -> Incoming.CardsReset
        "focus" -> Incoming.Focus(obj.str("id").orEmpty())
        "ring" -> Incoming.Ring(obj.int("id") ?: 0, obj.str("kind").orEmpty(), obj.str("label").orEmpty())
        "device" -> Incoming.Device(
            obj.int("id") ?: 0,
            obj.str("action").orEmpty(),
            obj.int("hour") ?: 0,
            obj.int("minute") ?: 0,
            (obj["days"] as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.intOrNull },
            obj.str("label").orEmpty(),
        )
        "done" -> Incoming.Done((obj["ms"] as? JsonPrimitive)?.longOrNull)
        "ignored" -> Incoming.Ignored(obj.str("reason").orEmpty())
        "error" -> Incoming.Failure(obj.str("text").orEmpty())
        else -> Incoming.Unknown(type)
    }
}

private fun screenMessages(element: JsonElement?): List<ScreenMessage> {
    val list = element as? JsonArray ?: return emptyList()
    return list.mapNotNull { item ->
        val msg = item as? JsonObject ?: return@mapNotNull null
        val kind = SCREEN_KINDS.firstOrNull { it in msg }
        val surfaceId = kind?.let { (msg[it] as? JsonObject)?.str("surfaceId") }
        ScreenMessage(msg.toString(), kind, surfaceId)
    }
}

object Outgoing {
    fun start(why: String, rate: Int = INPUT_RATE): String = buildJsonObject {
        put("type", "start")
        put("rate", rate)
        put("why", why)
    }.toString()

    fun end(rate: Int = INPUT_RATE): String = buildJsonObject {
        put("type", "end")
        put("rate", rate)
    }.toString()

    fun text(text: String): String = buildJsonObject {
        put("type", "text")
        put("text", text)
    }.toString()

    fun stop(): String = buildJsonObject { put("type", "stop") }.toString()

    /** The card was swiped away or closed with its ✕. */
    fun closed(id: String): String = buildJsonObject {
        put("type", "closed")
        put("surfaceId", id)
    }.toString()

    /** The card now in front: "this" in a question means this one. */
    fun front(id: String): String = buildJsonObject {
        put("type", "front")
        put("surfaceId", id)
    }.toString()

    /** The renderer could not draw something: the server tells Claude, so it can fix it. */
    fun renderError(surfaceId: String?, message: String): String = buildJsonObject {
        put("type", "render_error")
        put("surfaceId", surfaceId)
        put("message", message)
    }.toString()

    fun deviceResult(id: Int, ok: Boolean): String = buildJsonObject {
        put("type", "device_result")
        put("id", id)
        put("ok", ok)
    }.toString()

    fun ringStop(id: Int): String = buildJsonObject {
        put("type", "ring_stop")
        put("id", id)
    }.toString()

    /** A tap on an A2UI component: the protocol's `action` message. */
    fun action(name: String, surfaceId: String, componentId: String, context: Map<String, Any?>): String =
        buildJsonObject {
            put("type", "action")
            put("name", name)
            put("surfaceId", surfaceId)
            put("sourceComponentId", componentId)
            put("context", toJson(context))
        }.toString()
}

/** From any Kotlin value (maps, lists, numbers, text) to JSON. */
fun toJson(value: Any?): JsonElement = when (value) {
    null -> JsonNull
    is JsonElement -> value
    is String -> JsonPrimitive(value)
    is Boolean -> JsonPrimitive(value)
    is Number -> JsonPrimitive(value)
    is Map<*, *> -> JsonObject(value.entries.associate { (k, v) -> k.toString() to toJson(v) })
    is Iterable<*> -> JsonArray(value.map { toJson(it) })
    is Array<*> -> JsonArray(value.map { toJson(it) })
    else -> JsonPrimitive(value.toString())
}

/** The websocket address from what is typed in the settings. */
fun socketUrl(server: String, token: String, device: String = "tablet"): String {
    var base = server.trim().trimEnd('/')
    base = when {
        base.startsWith("ws://") || base.startsWith("wss://") -> base
        base.startsWith("http://") -> "ws://" + base.removePrefix("http://")
        base.startsWith("https://") -> "wss://" + base.removePrefix("https://")
        else -> "ws://$base"
    }
    val hostPart = base.substringAfter("://")
    if (!hostPart.substringBefore('/').contains(':')) {
        val scheme = base.substringBefore("://")
        base = "$scheme://${hostPart.substringBefore('/')}:4390" +
            hostPart.removePrefix(hostPart.substringBefore('/'))
    }
    if (!base.endsWith("/ws")) base += "/ws"
    val enc = { s: String -> java.net.URLEncoder.encode(s, "UTF-8") }
    return "$base?token=${enc(token)}&device=${enc(device)}"
}
