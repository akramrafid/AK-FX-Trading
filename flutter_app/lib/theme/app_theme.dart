import 'package:flutter/material.dart';

/// AK Forex Trading — Design System & Theme
///
/// Impeccable dark glassmorphic theme inspired by TrendWise and pro quant terminals.
/// Deep void background, frosted acrylic glass, electric lime accents, tabular monospace data.

class AppColors {
  AppColors._();

  // ── Background layers ────────────────────────────────────────────────
  static const Color bgPrimary = Color(0xFF080C15);
  static const Color bgSecondary = Color(0xFF0D1424);
  static const Color bgCard = Color(0xFF131B2E);
  static const Color bgCardDark = Color(0xFF0B101D);
  static const Color bgCardLight = Color(0xFF1A243D);
  static const Color bgCardHover = Color(0xFF223050);
  static const Color bgSurface = Color(0xFF0A0F1D);

  // ── Glass morphism ───────────────────────────────────────────────────
  static const Color glassFill = Color(0x1AFFFFFF);
  static const Color glassBorder = Color(0x2EFFFFFF);
  static const Color glassHighlight = Color(0x0DFFFFFF);

  // ── Accent colors ────────────────────────────────────────────────────
  static const Color accentLime = Color(0xFFCDFF64);
  static const Color accentGreen = Color(0xFF00E676);
  static const Color accentRed = Color(0xFFFF3B30);
  static const Color accentOrange = Color(0xFFFF9500);
  static const Color accentBlue = Color(0xFF2979FF);
  static const Color accentPurple = Color(0xFFA855F7);
  static const Color accentCyan = Color(0xFF00F0FF);

  // ── Text ─────────────────────────────────────────────────────────────
  static const Color textPrimary = Color(0xFFF9FAFB);
  static const Color textSecondary = Color(0xFF94A3B8);
  static const Color textMuted = Color(0xFF64748B);
  static const Color textOnAccent = Color(0xFF080C15);

  // ── Chart colors ─────────────────────────────────────────────────────
  static const Color chartGreen = Color(0xFF00E676);
  static const Color chartRed = Color(0xFFFF3B30);
  static const Color chartLine = Color(0xFF2979FF);
  static const Color chartGrid = Color(0x14FFFFFF);

  // ── Borders ──────────────────────────────────────────────────────────
  static const Color borderSubtle = Color(0x1FFFFFFF);
  static const Color borderActive = Color(0xFFCDFF64);
}

class AppTypography {
  AppTypography._();

  static TextStyle mono({
    double fontSize = 13,
    FontWeight fontWeight = FontWeight.w600,
    Color color = AppColors.textPrimary,
    double? letterSpacing,
  }) {
    return TextStyle(
      fontFamily: 'Consolas',
      fontSize: fontSize,
      fontWeight: fontWeight,
      color: color,
      letterSpacing: letterSpacing ?? -0.2,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
  }
}

class AppTheme {
  AppTheme._();

  static ThemeData get darkTheme {
    const String defaultFont = 'Segoe UI';

    return ThemeData(
      brightness: Brightness.dark,
      fontFamily: defaultFont,
      scaffoldBackgroundColor: AppColors.bgPrimary,
      primaryColor: AppColors.accentLime,
      colorScheme: const ColorScheme.dark(
        primary: AppColors.accentLime,
        secondary: AppColors.accentCyan,
        surface: AppColors.bgCard,
        error: AppColors.accentRed,
      ),
      textTheme: const TextTheme(
        displayLarge: TextStyle(fontFamily: defaultFont, fontSize: 44, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: -1.2),
        displayMedium: TextStyle(fontFamily: defaultFont, fontSize: 32, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: -0.8),
        displaySmall: TextStyle(fontFamily: defaultFont, fontSize: 26, fontWeight: FontWeight.w600, color: AppColors.textPrimary, letterSpacing: -0.4),
        headlineMedium: TextStyle(fontFamily: defaultFont, fontSize: 20, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        headlineSmall: TextStyle(fontFamily: defaultFont, fontSize: 18, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        titleLarge: TextStyle(fontFamily: defaultFont, fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        titleMedium: TextStyle(fontFamily: defaultFont, fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
        bodyLarge: TextStyle(fontFamily: defaultFont, fontSize: 15, fontWeight: FontWeight.w400, color: AppColors.textPrimary),
        bodyMedium: TextStyle(fontFamily: defaultFont, fontSize: 13, fontWeight: FontWeight.w400, color: AppColors.textSecondary),
        bodySmall: TextStyle(fontFamily: defaultFont, fontSize: 11, fontWeight: FontWeight.w400, color: AppColors.textMuted),
        labelLarge: TextStyle(fontFamily: defaultFont, fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        labelMedium: TextStyle(fontFamily: defaultFont, fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
        labelSmall: TextStyle(fontFamily: defaultFont, fontSize: 10, fontWeight: FontWeight.w600, color: AppColors.textMuted, letterSpacing: 1.0),
      ),
      iconTheme: const IconThemeData(color: AppColors.textSecondary, size: 20),
      dividerColor: AppColors.borderSubtle,
      cardColor: AppColors.bgCard,
    );
  }
}

class AppRadius {
  AppRadius._();
  static const double xs = 6;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
}

class AppSpacing {
  AppSpacing._();
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
}
