package dev.pino.app

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

private val Blue = Color(0xFF2F6FDB)
private val Red = Color(0xFFD9483B)
private val Amber = Color(0xFFE5A21A)
private val Green = Color(0xFF1F9D6B)
private val Teal = Color(0xFF1F7A6D)

/**
 * The circle in the middle: it shows the state and it is the only button. Quiet and breathing while
 * it waits for its name, blue and pulsing with your voice while it listens, four dots turning while
 * it thinks, bars while it speaks, a red ring when the microphone is off.
 */
@Composable
fun StateOrb(phase: Phase, level: Float, description: String, size: Dp = 132.dp, onClick: () -> Unit) {
    val t = rememberInfiniteTransition(label = "orb")
    val breath by t.animateFloat(
        0f, 1f, infiniteRepeatable(tween(2200), RepeatMode.Reverse), label = "breath",
    )
    val spin by t.animateFloat(
        0f, 360f, infiniteRepeatable(tween(1100, easing = LinearEasing)), label = "spin",
    )
    val wave by t.animateFloat(
        0f, (2 * PI).toFloat(), infiniteRepeatable(tween(900, easing = LinearEasing)), label = "wave",
    )
    val voice by animateFloatAsState(level, tween(120), label = "level")
    val surface = MaterialTheme.colorScheme.surfaceVariant
    val onSurface = MaterialTheme.colorScheme.onSurfaceVariant

    Canvas(
        modifier = Modifier
            .size(size)
            .semantics { contentDescription = description }
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                role = Role.Button,
                onClick = onClick,
            ),
    ) {
        val r = min(this.size.width, this.size.height) / 2f
        val c = center
        when (phase) {
            Phase.IDLE -> {
                drawCircle(surface, r * (0.86f + 0.04f * breath), c)
                play(c, r * 0.32f, Teal)
            }
            Phase.OFF -> {
                drawCircle(surface, r * 0.86f, c)
                drawCircle(Red, r * 0.86f, c, style = Stroke(r * 0.06f))
                micOff(c, r * 0.3f, Red)
            }
            Phase.LISTENING, Phase.FOLLOW -> {
                val ring = 0.9f + 0.1f * voice + 0.04f * breath
                drawCircle(Blue.copy(alpha = 0.18f), r * ring, c)
                drawCircle(Blue, r * (0.7f + 0.12f * voice), c)
                bars(c, r * 0.36f, Color.White, wave, 0.3f + voice)
            }
            Phase.THINKING -> {
                drawCircle(surface, r * 0.86f, c)
                rotate(spin, c) {
                    listOf(Blue, Red, Amber, Green).forEachIndexed { i, color ->
                        val a = i * PI / 2
                        drawCircle(color, r * 0.11f, Offset(c.x + cos(a).toFloat() * r * 0.42f, c.y + sin(a).toFloat() * r * 0.42f))
                    }
                }
            }
            Phase.SPEAKING -> {
                drawCircle(Teal, r * 0.86f, c)
                bars(c, r * 0.4f, Color.White, wave, 1f)
            }
            Phase.RINGING -> {
                drawCircle(Amber.copy(alpha = 0.25f), r * (0.86f + 0.1f * breath), c)
                drawCircle(Amber, r * 0.7f, c)
                bars(c, r * 0.36f, Color.White, wave * 2, 1f)
            }
            Phase.SETUP, Phase.OFFLINE, Phase.CONNECTING -> {
                drawCircle(surface, r * 0.86f, c)
                drawArc(
                    onSurface.copy(alpha = 0.6f), spin, 90f, false,
                    topLeft = Offset(c.x - r * 0.4f, c.y - r * 0.4f),
                    size = androidx.compose.ui.geometry.Size(r * 0.8f, r * 0.8f),
                    style = Stroke(r * 0.06f),
                )
            }
        }
    }
}

private fun DrawScope.play(c: Offset, r: Float, color: Color) {
    val p = Path().apply {
        moveTo(c.x - r * 0.6f, c.y - r)
        lineTo(c.x + r, c.y)
        lineTo(c.x - r * 0.6f, c.y + r)
        close()
    }
    drawPath(p, color)
}

private fun DrawScope.bars(c: Offset, r: Float, color: Color, phase: Float, gain: Float) {
    val n = 5
    val w = r * 0.22f
    for (i in 0 until n) {
        val x = c.x + (i - (n - 1) / 2f) * w * 1.7f
        val h = r * (0.25f + 0.75f * gain.coerceIn(0f, 1f) * (0.5f + 0.5f * sin(phase + i * 0.9f)))
        drawLine(color, Offset(x, c.y - h), Offset(x, c.y + h), strokeWidth = w, cap = androidx.compose.ui.graphics.StrokeCap.Round)
    }
}

private fun DrawScope.micOff(c: Offset, r: Float, color: Color) {
    val w = r * 0.22f
    drawRoundRect(
        color,
        topLeft = Offset(c.x - r * 0.35f, c.y - r),
        size = androidx.compose.ui.geometry.Size(r * 0.7f, r * 1.3f),
        cornerRadius = androidx.compose.ui.geometry.CornerRadius(r * 0.35f),
    )
    drawLine(color, Offset(c.x, c.y + r * 0.5f), Offset(c.x, c.y + r), strokeWidth = w)
    drawLine(color, Offset(c.x - r, c.y - r), Offset(c.x + r, c.y + r), strokeWidth = w * 0.8f)
}
