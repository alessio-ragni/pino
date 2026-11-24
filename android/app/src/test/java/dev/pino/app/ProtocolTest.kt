package dev.pino.app

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolTest {
    @Test
    fun readsReady() {
        val m = parseIncoming("""{"type":"ready","voice":true,"ears":false,"rate":24000,"a2ui":"v0.9.1"}""")
        assertEquals(Incoming.Ready(voice = true, ears = false, rate = 24000, a2ui = "v0.9.1"), m)
    }

    @Test
    fun readsSayAndDone() {
        assertEquals(Incoming.Say("Ecco la carbonara.", 24000), parseIncoming("""{"type":"say","text":"Ecco la carbonara.","rate":24000}"""))
        assertEquals(Incoming.Done(9100), parseIncoming("""{"type":"done","ms":9100}"""))
        assertEquals(Incoming.SayEnd, parseIncoming("""{"type":"say_end"}"""))
    }

    @Test
    fun readsIgnored() {
        assertEquals(Incoming.Ignored("non chiamato"), parseIncoming("""{"type":"ignored","reason":"non chiamato"}"""))
    }

    @Test
    fun startSaysWhyItListens() {
        val start = Json.parseToJsonElement(Outgoing.start(Ears.Why.FOLLOW)).jsonObject
        assertEquals("start", start["type"]!!.jsonPrimitive.content)
        assertEquals("follow", start["why"]!!.jsonPrimitive.content)
        assertEquals(16000, start["rate"]!!.jsonPrimitive.content.toInt())
    }

    @Test
    fun readsScreenMessagesKeepingThemWhole() {
        val m = parseIncoming(
            """{"type":"a2ui","messages":[
              {"version":"v0.9.1","createSurface":{"surfaceId":"conferma","catalogId":"x"}},
              {"version":"v0.9.1","deleteSurface":{"surfaceId":"ricetta"}}
            ]}""",
        ) as Incoming.Screen
        assertEquals(listOf("createSurface", "deleteSurface"), m.messages.map { it.kind })
        assertEquals(listOf("conferma", "ricetta"), m.messages.map { it.surfaceId })
        val first = Json.parseToJsonElement(m.messages[0].raw).jsonObject
        assertEquals("v0.9.1", first["version"]!!.jsonPrimitive.content)
    }

    @Test
    fun garbageIsUnknown() {
        assertEquals(Incoming.Unknown(null), parseIncoming("not json"))
        assertEquals(Incoming.Unknown("boh"), parseIncoming("""{"type":"boh"}"""))
    }

    @Test
    fun writesAction() {
        val raw = Outgoing.action("confirm_yes", "conferma", "yes", mapOf("n" to 2, "list" to listOf("a", null)))
        val obj = Json.parseToJsonElement(raw).jsonObject
        assertEquals("action", obj["type"]!!.jsonPrimitive.content)
        assertEquals("confirm_yes", obj["name"]!!.jsonPrimitive.content)
        assertEquals("yes", obj["sourceComponentId"]!!.jsonPrimitive.content)
        assertEquals("""{"n":2,"list":["a",null]}""", obj["context"].toString())
    }

    @Test
    fun buildsSocketUrl() {
        assertEquals("ws://mio-mac:4390/ws?token=abc&device=tablet", socketUrl("mio-mac", "abc"))
        assertEquals("ws://mio-mac:4390/ws?token=abc&device=tablet", socketUrl("mio-mac:4390", "abc"))
        assertEquals("wss://x.example:443/ws?token=a+b&device=tablet", socketUrl("https://x.example:443/", "a b"))
        assertTrue(socketUrl("ws://10.0.0.2:4390/ws", "t").startsWith("ws://10.0.0.2:4390/ws?"))
    }

    @Test
    fun readsCardsAndFocus() {
        val m = parseIncoming(
            """{"type":"card","id":"carbonara","title":"Carbonara","thread":[{"q":"quanto pecorino?","a":"Cinquanta grammi."}]}""",
        )
        assertEquals(Incoming.Card(CardMeta("carbonara", "Carbonara", listOf(ThreadItem("quanto pecorino?", "Cinquanta grammi.")))), m)
        assertEquals(Incoming.Focus("carbonara"), parseIncoming("""{"type":"focus","id":"carbonara"}"""))
        assertEquals(Incoming.CardClosed("x"), parseIncoming("""{"type":"card_closed","id":"x"}"""))
        assertEquals(Incoming.CardsReset, parseIncoming("""{"type":"cards_reset"}"""))
    }

    @Test
    fun readsRingAndDevice() {
        assertEquals(Incoming.Ring(3, "timer", "pasta"), parseIncoming("""{"type":"ring","id":3,"kind":"timer","label":"pasta"}"""))
        val d = parseIncoming(
            """{"type":"device","id":7,"action":"set_alarm","hour":7,"minute":15,"days":[1,5],"label":"Scuola"}""",
        )
        assertEquals(Incoming.Device(7, "set_alarm", 7, 15, listOf(1, 5), "Scuola"), d)
    }

    @Test
    fun writesCardMessages() {
        val closed = Json.parseToJsonElement(Outgoing.closed("carbonara")).jsonObject
        assertEquals("closed", closed["type"]!!.jsonPrimitive.content)
        assertEquals("carbonara", closed["surfaceId"]!!.jsonPrimitive.content)
        val result = Json.parseToJsonElement(Outgoing.deviceResult(7, true)).jsonObject
        assertEquals("true", result["ok"]!!.jsonPrimitive.content)
        val error = Json.parseToJsonElement(Outgoing.renderError("x", "boom")).jsonObject
        assertEquals("render_error", error["type"]!!.jsonPrimitive.content)
    }

    @Test
    fun weekdaysForTheClockApp() {
        assertEquals(java.util.Calendar.MONDAY, DeviceActions.calendarDay(1))
        assertEquals(java.util.Calendar.SUNDAY, DeviceActions.calendarDay(7))
    }
}
