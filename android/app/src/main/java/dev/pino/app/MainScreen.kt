package dev.pino.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.a2ui.A2uiSurface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeoutOrNull

/**
 * The main screen: the circle that shows the state (and is the only button), and the cards, one per
 * topic, swiped left and right. Landscape puts the circle on the left; portrait at the bottom.
 */
@Composable
fun MainScreen(onSettings: () -> Unit) {
    val phase by Hub.phase.collectAsState()
    val level by Hub.level.collectAsState()
    val micOn by Hub.micOn.collectAsState()
    val error by Hub.error.collectAsState()
    val progress by Hub.earsProgress.collectAsState()

    BoxWithConstraints(modifier = Modifier.fillMaxSize().safeDrawingPadding()) {
        val wide = maxWidth > maxHeight
        val orb = @Composable {
            StatePanel(phase, level, error, progress, if (wide) 150.dp else 104.dp)
        }
        Column(modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp)) {
            TopBar(micOn, onSettings)
            if (wide) {
                Row(modifier = Modifier.weight(1f).fillMaxWidth()) {
                    Box(
                        modifier = Modifier.width(240.dp).fillMaxHeight(),
                        contentAlignment = Alignment.Center,
                    ) { orb() }
                    Cards(modifier = Modifier.weight(1f).fillMaxHeight())
                }
            } else {
                Cards(modifier = Modifier.weight(1f).fillMaxWidth())
                Box(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), contentAlignment = Alignment.Center) {
                    orb()
                }
            }
        }
    }
}

@Composable
private fun TopBar(micOn: Boolean, onSettings: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        AssistChip(
            onClick = { Hub.commands.tryEmit(Command.Mic(!micOn)) },
            label = { Text(stringResource(if (micOn) R.string.mic_on else R.string.mic_off)) },
            leadingIcon = {
                Box(
                    Modifier.size(10.dp).clip(CircleShape)
                        .background(if (micOn) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error),
                )
            },
            colors = if (micOn) AssistChipDefaults.assistChipColors() else AssistChipDefaults.assistChipColors(
                labelColor = MaterialTheme.colorScheme.error,
            ),
        )
        Spacer(Modifier.weight(1f))
        TextButton(onClick = onSettings) { Text(stringResource(R.string.settings)) }
    }
}

@Composable
private fun StatePanel(phase: Phase, level: Float, error: String?, progress: Int?, size: androidx.compose.ui.unit.Dp) {
    val said by Hub.said.collectAsState()
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        StateOrb(phase, level, stringResource(R.string.orb_description), size) { Hub.commands.tryEmit(Command.Orb) }
        Text(stringResource(phase.label), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        phase.hint?.let {
            Text(
                stringResource(it),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
        if (phase == Phase.SPEAKING && said.isNotBlank()) {
            Text(
                said,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                textAlign = TextAlign.Center,
                maxLines = 3,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.width(220.dp),
            )
        }
        progress?.let {
            Text(stringResource(R.string.downloading_wake, it), style = MaterialTheme.typography.bodySmall)
            LinearProgressIndicator(progress = { it / 100f }, modifier = Modifier.width(160.dp))
        }
        error?.let {
            Text(
                it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
                modifier = Modifier.width(220.dp),
            )
        }
    }
}

@Composable
private fun Cards(modifier: Modifier) {
    val context = LocalContext.current
    val cards by Hub.cards.collectAsState()
    val surfaces by Hub.screen(context).activeSurfaces.collectAsState()
    val byId = surfaces.associateBy { it.id }
    val confirm = byId[CONFIRM_SURFACE]
    val pager = rememberPagerState { cards.size }

    // The server says which card the answer is on: the pager goes there.
    LaunchedEffect(Unit) {
        Hub.focus.collect { id ->
            val i = Hub.cards.value.indexOfFirst { it.id == id }
            if (i < 0) return@collect
            // A card that has just arrived is not a page yet: wait for the pager to grow.
            withTimeoutOrNull(1500) { snapshotFlow { pager.pageCount }.first { it > i } }
            runCatching { pager.animateScrollToPage(i) }
        }
    }
    // The card in front, so "this" in a question means this one.
    LaunchedEffect(pager, cards) {
        snapshotFlow { pager.settledPage }.distinctUntilChanged().collect { i ->
            cards.getOrNull(i)?.let { Hub.commands.tryEmit(Command.Front(it.id)) }
        }
    }

    Column(modifier = modifier) {
        if (confirm != null) {
            Card(
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer),
            ) {
                A2uiSurface(surfaceModel = confirm, modifier = Modifier.fillMaxWidth().padding(8.dp))
            }
        }
        if (cards.isEmpty()) {
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(32.dp)) {
                    Text(stringResource(R.string.no_cards), style = MaterialTheme.typography.titleMedium)
                    Text(
                        stringResource(R.string.no_cards_hint),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                    )
                }
            }
            return@Column
        }
        HorizontalPager(
            state = pager,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            pageSpacing = 12.dp,
            key = { i -> cards.getOrNull(i)?.id ?: i },
        ) { i ->
            val card = cards.getOrNull(i) ?: return@HorizontalPager
            CardPage(card, byId[card.id])
        }
        Dots(count = cards.size, current = pager.currentPage)
    }
}

@Composable
private fun CardPage(card: CardMeta, surface: androidx.a2ui.model.processor.A2uiSurfaceModel?) {
    Card(
        modifier = Modifier.fillMaxSize(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 4.dp, top = 8.dp),
        ) {
            Text(
                card.title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            val close = stringResource(R.string.close_card)
            TextButton(
                onClick = { Hub.commands.tryEmit(Command.CloseCard(card.id)) },
                modifier = Modifier.semantics { contentDescription = close },
            ) {
                Text("✕", style = MaterialTheme.typography.titleLarge)
            }
        }
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (surface != null) A2uiSurface(surfaceModel = surface, modifier = Modifier.fillMaxWidth())
            Thread(card.thread, quiet = surface != null)
            Spacer(Modifier.height(16.dp))
        }
    }
}

/** The answers given on this topic, newest last: what matters is the answer, the question stays small. */
@Composable
private fun Thread(items: List<ThreadItem>, quiet: Boolean) {
    val shown = if (quiet) items.takeLast(3) else items.takeLast(8)
    if (shown.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
        shown.forEach { item ->
            Column {
                Text(
                    item.q,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(item.a, style = MaterialTheme.typography.bodyLarge)
            }
        }
    }
}

@Composable
private fun Dots(count: Int, current: Int) {
    if (count < 2) return
    Row(
        horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
    ) {
        repeat(count) { i ->
            val on = i == current
            Box(
                Modifier.height(7.dp).width(if (on) 18.dp else 7.dp).clip(CircleShape)
                    .background(if (on) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.outlineVariant),
            )
        }
    }
}
