package dev.pino.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {
    private lateinit var prefs: Prefs

    private val askPermissions = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { startIfAllowed() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        prefs = Prefs(this)
        // In the kitchen the screen stays on while the app is in front.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContent {
            PinoTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    var editing by remember { mutableStateOf(!prefs.ready) }
                    if (editing) {
                        SettingsScreen(prefs) {
                            editing = false
                            startIfAllowed()
                            Hub.commands.tryEmit(Command.Reconnect)
                        }
                    } else {
                        MainScreen(onSettings = { editing = true })
                    }
                }
            }
        }
        askPermissions()
        handle(intent)
    }

    override fun onResume() {
        super.onResume()
        DeviceActions.inFront = true
    }

    override fun onPause() {
        DeviceActions.inFront = false
        super.onPause()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    /**
     * The side key held down (Pino as default assistant): listen at once. With a text extra
     * (`adb shell am start -a dev.pino.app.ASCOLTA --es text "…"`) the question is asked in
     * writing, to try things on the tablet without a voice.
     */
    private fun handle(intent: Intent?) {
        if (intent?.action != Intent.ACTION_ASSIST && intent?.action != ACTION_LISTEN) return
        if (intent.getStringExtra(EXTRA_DEMO) == "gallery") {
            Hub.commands.tryEmit(Command.Gallery)
            return
        }
        val text = intent.getStringExtra(EXTRA_TEXT)
        if (!text.isNullOrBlank()) {
            Hub.commands.tryEmit(Command.Ask(text))
            return
        }
        Hub.listenWhenReady = true
        Hub.commands.tryEmit(Command.Listen)
    }

    companion object {
        const val ACTION_LISTEN = "dev.pino.app.ASCOLTA"
        const val EXTRA_TEXT = "text"
        const val EXTRA_DEMO = "demo"
    }

    private fun askPermissions() {
        val wanted = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (wanted.isEmpty()) startIfAllowed() else askPermissions.launch(wanted.toTypedArray())
    }

    private fun startIfAllowed() {
        val mic = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
        if (mic != PackageManager.PERMISSION_GRANTED) {
            Hub.error.value = getString(R.string.error_mic_permission)
            return
        }
        if (prefs.ready) PinoService.start(this)
    }
}

@Composable
private fun SettingsScreen(prefs: Prefs, onDone: () -> Unit) {
    var server by remember { mutableStateOf(prefs.server) }
    var token by remember { mutableStateOf(prefs.token) }
    Column(
        modifier = Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(stringResource(R.string.settings), style = MaterialTheme.typography.headlineMedium)
        Text(stringResource(R.string.settings_intro), style = MaterialTheme.typography.bodyMedium)
        OutlinedTextField(
            value = server,
            onValueChange = { server = it },
            label = { Text(stringResource(R.string.server_address)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text(stringResource(R.string.token)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            enabled = server.isNotBlank() && token.isNotBlank(),
            onClick = {
                prefs.server = server
                prefs.token = token
                onDone()
            },
        ) { Text(stringResource(R.string.save_connect)) }
    }
}
