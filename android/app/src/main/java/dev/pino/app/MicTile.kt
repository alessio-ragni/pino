package dev.pino.app

import android.content.ComponentName
import android.content.Context
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.util.Log

/**
 * The «Pino» tile in quick settings (the pull-down shade): the microphone switch, like Alexa's
 * button. On it listens for the name, off it closes the microphone.
 */
class MicTile : TileService() {
    override fun onStartListening() {
        super.onStartListening()
        show(Prefs(this).micOn)
    }

    override fun onClick() {
        super.onClick()
        val on = !Prefs(this).micOn
        Prefs(this).micOn = on
        show(on)
        try {
            startService(PinoService.micIntent(this, on))
        } catch (bad: Exception) {
            // The service is not running and Android does not let it start from here: opening the app will.
            Log.w("pino", "service not reachable from the tile", bad)
        }
    }

    private fun show(on: Boolean) {
        val tile = qsTile ?: return
        tile.state = if (on) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = getString(R.string.app_name)
        tile.subtitle = getString(if (on) R.string.tile_on else R.string.tile_off)
        tile.updateTile()
    }

    companion object {
        /** Asks quick settings to redraw the tile after a change made elsewhere. */
        fun refresh(context: Context) {
            runCatching { requestListeningState(context, ComponentName(context, MicTile::class.java)) }
        }
    }
}
