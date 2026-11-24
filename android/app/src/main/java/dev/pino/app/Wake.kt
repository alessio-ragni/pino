package dev.pino.app

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject

/**
 * The wake word. The on-tablet recognizer has a CLOSED grammar: the names, a few decoy words and
 * `[unk]`. Household speech cannot be represented in there, so it is not transcribed: until it
 * hears the name, nothing goes to the server.
 *
 * Decoys are words «pino» gets confused with (pinoli, vino, fino, Pinocchio…): they give those
 * sounds a box of their own, so the name stops collecting everything that resembles it. They never
 * leave this file: they help decide, then vanish like `[unk]`.
 */
object Wake {
    val NAMES = listOf("pino")

    val DECOYS = listOf(
        "pina", "pinoli", "pinolo", "pinocchio", "pinot", "spino", "spina", "vino", "fino", "pieno",
        "piano",
    )

    /** Greetings allowed before the name: «ehi Pino», «ciao Pino», «hey Pino». */
    val GREETINGS = listOf("ehi", "hey", "hei", "ei", "ciao", "hi")

    /** Said on their own, while Pino talks or rings, they stop him at once: no answer follows. */
    val STOPS = listOf("basta", "stop", "zitto", "zitta", "fermati", "silenzio")

    const val UNKNOWN = "[unk]"

    /** A stop word needs this confidence, so his own voice does not stop him. */
    const val STOP_CONFIDENCE = 0.6

    /** Below this confidence, in the final result, it is not a call. Tuned with `tools/prova_parola.py`. */
    const val MIN_CONFIDENCE = 0.5

    /** At most two greetings before the name. */
    const val MAX_GREETINGS = 2

    enum class Verdict { YES, NO, MAYBE }

    fun grammar(): String = JsonArray(
        (NAMES + GREETINGS + STOPS + DECOYS.filter { it !in NAMES } + UNKNOWN).map { JsonPrimitive(it) },
    ).toString()

    /**
     * From vosk's JSON (partial or final) to "they called me": YES, NO, or MAYBE when the name is
     * the last thing heard and it is not known yet whether a decoy follows («pino… cchio»).
     *
     * Rule: greetings skipped, the first word must be a name, and the next one not a decoy.
     * «Ho visto Pino» does not wake it: the name is not first. Nothing else is kept.
     */
    fun verdict(voskJson: String): Verdict {
        val obj = try {
            Json.parseToJsonElement(voskJson).jsonObject
        } catch (_: Exception) {
            return Verdict.NO
        }
        val result = obj["result"] as? JsonArray
        if (result != null) {
            val words = result.mapNotNull { it as? JsonObject }.map {
                ((it["word"] as? JsonPrimitive)?.contentOrNull ?: "") to
                    ((it["conf"] as? JsonPrimitive)?.doubleOrNull ?: 0.0)
            }
            return decide(words, final = true)
        }
        val text = (obj["partial"] as? JsonPrimitive)?.contentOrNull
            ?: (obj["text"] as? JsonPrimitive)?.contentOrNull
            ?: return Verdict.NO
        return decide(text.split(' ').filter { it.isNotBlank() }.map { it to 1.0 }, final = false)
    }

    private fun decide(words: List<Pair<String, Double>>, final: Boolean): Verdict {
        var i = 0
        while (i < words.size && words[i].first in GREETINGS) i++
        if (i >= words.size || i > MAX_GREETINGS) return Verdict.NO
        val (word, conf) = words[i]
        if (word !in NAMES || (final && conf < MIN_CONFIDENCE)) return Verdict.NO
        val next = words.getOrNull(i + 1)?.first
        return when {
            next != null -> if (next in DECOYS) Verdict.NO else Verdict.YES
            final -> Verdict.YES
            else -> Verdict.MAYBE
        }
    }

    fun heard(voskJson: String): Boolean = verdict(voskJson) == Verdict.YES

    /**
     * «Basta», «stop», «Pino, basta»: the whole thing heard is a stop word (after the name or a
     * greeting at most). Only final results count, with enough confidence: a word inside one of his
     * own sentences must not stop him.
     */
    fun stop(voskJson: String): Boolean {
        val obj = try {
            Json.parseToJsonElement(voskJson).jsonObject
        } catch (_: Exception) {
            return false
        }
        val result = obj["result"] as? JsonArray ?: return false
        val words = result.mapNotNull { it as? JsonObject }.map {
            ((it["word"] as? JsonPrimitive)?.contentOrNull ?: "") to
                ((it["conf"] as? JsonPrimitive)?.doubleOrNull ?: 0.0)
        }.filter { it.first != UNKNOWN }
        val rest = words.dropWhile { it.first in GREETINGS || it.first in NAMES }
        return rest.size == 1 && rest[0].first in STOPS && rest[0].second >= STOP_CONFIDENCE
    }
}
