package dev.pino.app

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.sp

/**
 * The look of the app and of every card. The A2UI renderer draws with the Material theme it finds,
 * so this is where the cards get their colours (the tablet's own, from the wallpaper) and their
 * text sizes, larger than a phone's because the tablet is read from across the kitchen.
 */
@Composable
fun PinoTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val context = LocalContext.current
    val colors = when {
        Build.VERSION.SDK_INT >= 31 && dark -> dynamicDarkColorScheme(context)
        Build.VERSION.SDK_INT >= 31 -> dynamicLightColorScheme(context)
        dark -> darkColorScheme()
        else -> lightColorScheme()
    }
    val base = Typography()
    val type = base.copy(
        headlineSmall = base.headlineSmall.copy(fontSize = 28.sp, lineHeight = 34.sp),
        titleLarge = base.titleLarge.copy(fontSize = 26.sp, lineHeight = 32.sp),
        titleMedium = base.titleMedium.copy(fontSize = 20.sp, lineHeight = 26.sp),
        bodyLarge = base.bodyLarge.copy(fontSize = 20.sp, lineHeight = 28.sp),
        bodyMedium = base.bodyMedium.copy(fontSize = 18.sp, lineHeight = 25.sp),
        labelMedium = base.labelMedium.copy(fontSize = 14.sp),
    )
    MaterialTheme(colorScheme = colors, typography = type, content = content)
}
