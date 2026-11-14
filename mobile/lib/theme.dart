import 'package:flutter/material.dart';

/// The colours of the web version (app/web/static/style.css), so the two look the same.
abstract final class CnvColors {
  static const background = Color(0xFF121212);
  static const surface = Color(0xFF1E1E1E);
  static const surface2 = Color(0xFF2A2A2A);
  static const border = Color(0xFF333333);
  static const text = Color(0xFFE0E0E0);
  static const textMuted = Color(0xFF9A9A9A);
  static const accent = Color(0xFFBB86FC);
  static const green = Color(0xFF4CAF50);
  static const yellow = Color(0xFFFF9800);
  static const red = Color(0xFFF44336);
}

ThemeData cnvTheme() {
  const scheme = ColorScheme.dark(
    primary: CnvColors.accent,
    onPrimary: Colors.black,
    secondary: CnvColors.accent,
    onSecondary: Colors.black,
    surface: CnvColors.surface,
    onSurface: CnvColors.text,
    error: CnvColors.red,
  );
  Color selectedOr(Set<WidgetState> states, Color other) =>
      states.contains(WidgetState.selected) ? CnvColors.accent : other;
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: CnvColors.background,
    dividerColor: CnvColors.border,
    appBarTheme: const AppBarTheme(
      backgroundColor: CnvColors.surface,
      foregroundColor: CnvColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: CnvColors.surface,
      indicatorColor: CnvColors.accent.withValues(alpha: 0.22),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 12,
          color: selectedOr(states, CnvColors.textMuted),
          fontWeight: states.contains(WidgetState.selected) ? FontWeight.w600 : FontWeight.w400,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(color: selectedOr(states, CnvColors.textMuted)),
      ),
    ),
  );
}
