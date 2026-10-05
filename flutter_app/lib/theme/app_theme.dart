import 'package:flutter/material.dart';

/// AK Forex Trading — Design System & Tokens
///
/// Complies with `design-system/MASTER.md` and the `designer-skills` framework.
/// Three-tier token architecture:
/// 1. Global Tokens: Raw colors, base grid units
/// 2. Semantic Tokens: Surfaces, typography roles, state indicators
/// 3. Component Tokens: Card metrics, navigation pills, chart elements

class AppColors {
  AppColors._();

  // ── Global Canvas & Dark Elevation Hierarchy ─────────────────────────
  /// Level 0: Deep void root canvas
  static const Color bgPrimary = Color(0xFF080C15);
  /// Level 0.5: Sub-workspace canvas, side rails
  static const Color bgSecondary = Color(0xFF0D1424);
  /// Level 1: Surface cards, primary charts, execution tables
  static const Color bgCard = Color(0xFF131B2E);
  /// Level 1 Dark: Inset dark containers, dark metric panels
  static const Color bgCardDark = Color(0xFF0B101D);
  /// Level 2: Elevated cards, active pills, table header backgrounds
  static const Color bgCardLight = Color(0xFF1A243D);
  /// Level 2.5: Interactive hover surface
  static const Color bgCardHover = Color(0xFF223050);
  /// Level 3: Modal dialogs, dropdowns, floating menus
  static const Color bgSurface = Color(0xFF0A0F1D);
  static const Color bgSurfaceElevated = Color(0xFF223050);

  // ── Glassmorphism & Translucent Overlays ──────────────────────────────
  static const Color glassFill = Color(0x1AFFFFFF);
  static const Color glassBorder = Color(0x2EFFFFFF);
  static const Color glassHighlight = Color(0x0DFFFFFF);

  // ── High-Contrast Electric Accents ───────────────────────────────────
  /// Signature Primary Action Accent (Start Trading, Active Pair Indicator)
  static const Color accentLime = Color(0xFFCDFF64);
  /// Bullish Candle, Positive PnL, Winning Ratio, MT4 Connected Status
  static const Color accentGreen = Color(0xFF00E676);
  /// Bearish Candle, Negative PnL, Emergency Kill-Switch, Rejection Halt
  static const Color accentRed = Color(0xFFFF3B30);
  /// Spread Caution, Margin Warning, Paused State
  static const Color accentOrange = Color(0xFFFF9500);
  /// Major Pair Symbol, Technical Indicator SMA 20, MT4 Link
  static const Color accentBlue = Color(0xFF2979FF);
  /// R:R Bracket Badges, EMA 50 Overlay, Institutional Rules
  static const Color accentPurple = Color(0xFFA855F7);
  /// Dynamic ATR Sizing, Live Bid Ticker, Analytics Accents
  static const Color accentCyan = Color(0xFF00F0FF);

  // ── Semantic Aliases ─────────────────────────────────────────────────
  static const Color profitGreen = accentGreen;
  static const Color lossRed = accentRed;
  static const Color cautionAmber = accentOrange;
  static const Color infoCyan = accentCyan;

  // ── Accessible Typographic Hierarchy (WCAG 2.2 AA) ────────────────────
  /// 16.5:1 contrast against dark card background
  static const Color textPrimary = Color(0xFFF9FAFB);
  /// 5.6:1 contrast against dark card background (passes 4.5:1 AA)
  static const Color textSecondary = Color(0xFF94A3B8);
  /// 3.5:1 contrast for subtle metadata labels and uppercase tags
  static const Color textMuted = Color(0xFF64748B);
  /// Inverse text for electric lime high-contrast buttons
  static const Color textOnAccent = Color(0xFF080C15);

  // ── Financial Chart Palette ──────────────────────────────────────────
  static const Color chartGreen = Color(0xFF00E676);
  static const Color chartRed = Color(0xFFFF3B30);
  static const Color chartLine = Color(0xFF2979FF);
  static const Color chartGrid = Color(0x14FFFFFF);

  // ── Structural Dividers & Boundaries ─────────────────────────────────
  static const Color borderSubtle = Color(0x1FFFFFFF);
  static const Color borderActive = Color(0xFFCDFF64);
}

/// Systematic Typography Scale derived from `designer-skills` modular scale.
class AppTypography {
  AppTypography._();

  static const String fontPrimary = 'Segoe UI';
  static const String fontMono = 'Consolas';

  // ── Monospace Tabular Figures for Quant & Financial Data ─────────────
  static TextStyle mono({
    double fontSize = 13,
    FontWeight fontWeight = FontWeight.w600,
    Color color = AppColors.textPrimary,
    double? letterSpacing,
  }) {
    return TextStyle(
      fontFamily: fontMono,
      fontSize: fontSize,
      fontWeight: fontWeight,
      color: color,
      letterSpacing: letterSpacing ?? -0.2,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
  }

  // ── Fixed Scale Semantic Helpers ─────────────────────────────────────
  static TextStyle displayLarge({Color color = AppColors.textPrimary}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 44,
        fontWeight: FontWeight.w800,
        letterSpacing: -1.2,
        height: 1.15,
        color: AppColors.textPrimary,
      );

  static TextStyle headingLarge({Color color = AppColors.textPrimary}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 32,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.8,
        height: 1.20,
        color: AppColors.textPrimary,
      );

  static TextStyle headingMedium({Color color = AppColors.textPrimary}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 20,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.4,
        height: 1.25,
        color: AppColors.textPrimary,
      );

  static TextStyle headingSmall({Color color = AppColors.textPrimary}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 16,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
        height: 1.30,
        color: AppColors.textPrimary,
      );

  static TextStyle bodyLarge({Color color = AppColors.textPrimary}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 15,
        fontWeight: FontWeight.w500,
        letterSpacing: 0.0,
        height: 1.45,
        color: AppColors.textPrimary,
      );

  static TextStyle bodyMedium({Color color = AppColors.textSecondary}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 13,
        fontWeight: FontWeight.w500,
        letterSpacing: 0.0,
        height: 1.40,
        color: AppColors.textSecondary,
      );

  static TextStyle caption({Color color = AppColors.textMuted}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 11,
        fontWeight: FontWeight.w500,
        letterSpacing: 0.1,
        height: 1.35,
        color: AppColors.textMuted,
      );

  static TextStyle badgeLabel({Color color = AppColors.textMuted}) => const TextStyle(
        fontFamily: fontPrimary,
        fontSize: 10,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.8,
        height: 1.20,
        color: AppColors.textMuted,
      );
}

/// Systematic 4px Base Spacing Scale.
class AppSpacing {
  AppSpacing._();
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20; // 20 maintains exact backward compatibility
  static const double xl24 = 24;
  static const double xxl = 24; // 24 maintains exact backward compatibility
  static const double xxl32 = 32;
  static const double xxxl = 32; // 32 maintains exact backward compatibility
  static const double xxxl48 = 48;
  static const double x4l = 64;
}

/// Corner Radius Hierarchy with concentric calculation helpers.
class AppRadius {
  AppRadius._();
  static const double none = 0;
  static const double xs = 6;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double pill = 999;

  /// Concentric border radius formula: outer = inner + padding
  static double concentricInner(double outerRadius, double padding) =>
      (outerRadius - padding).clamp(2.0, double.infinity);
  static double concentricOuter(double innerRadius, double padding) => innerRadius + padding;
}

/// Elevation and Shadows for Dark Mode.
class AppShadows {
  AppShadows._();

  /// Dual-layer physically grounded card elevation (ambient diffuse + crisp contact)
  static const List<BoxShadow> card = [
    BoxShadow(
      color: Color(0x66000000),
      blurRadius: 24,
      spreadRadius: -4,
      offset: Offset(0, 12),
    ),
    BoxShadow(
      color: Color(0x33000000),
      blurRadius: 8,
      spreadRadius: -1,
      offset: Offset(0, 3),
    ),
  ];

  static const List<BoxShadow> floating = [
    BoxShadow(
      color: Color(0x8C000000),
      blurRadius: 36,
      spreadRadius: -6,
      offset: Offset(0, 18),
    ),
    BoxShadow(
      color: Color(0x40000000),
      blurRadius: 10,
      spreadRadius: -2,
      offset: Offset(0, 4),
    ),
  ];

  static List<BoxShadow> accentGlow(Color accentColor, {double opacity = 0.35, double blur = 14}) {
    return [
      BoxShadow(
        color: accentColor.withValues(alpha: opacity),
        blurRadius: blur,
        offset: const Offset(0, 4),
      ),
    ];
  }
}

/// Motion and Durations following `designer-skills` and `emil-design-eng` guidelines.
class AppMotion {
  AppMotion._();
  static const Duration press = Duration(milliseconds: 120);
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 250);
  static const Duration slow = Duration(milliseconds: 400);

  static const Curve curve = Curves.easeInOutCubic;
  static const Curve easeOut = Curves.easeOutCubic;
  static const Curve snappy = Cubic(0.2, 0.0, 0.0, 1.0);
}

/// Flutter ThemeData root configuration.
class AppTheme {
  AppTheme._();

  static ThemeData get darkTheme {
    const String defaultFont = AppTypography.fontPrimary;

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
        displayLarge: TextStyle(fontFamily: defaultFont, fontSize: 44, fontWeight: FontWeight.w800, color: AppColors.textPrimary, letterSpacing: -1.2),
        displayMedium: TextStyle(fontFamily: defaultFont, fontSize: 32, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: -0.8),
        displaySmall: TextStyle(fontFamily: defaultFont, fontSize: 26, fontWeight: FontWeight.w600, color: AppColors.textPrimary, letterSpacing: -0.4),
        headlineMedium: TextStyle(fontFamily: defaultFont, fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
        headlineSmall: TextStyle(fontFamily: defaultFont, fontSize: 18, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        titleLarge: TextStyle(fontFamily: defaultFont, fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
        titleMedium: TextStyle(fontFamily: defaultFont, fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
        bodyLarge: TextStyle(fontFamily: defaultFont, fontSize: 15, fontWeight: FontWeight.w400, color: AppColors.textPrimary),
        bodyMedium: TextStyle(fontFamily: defaultFont, fontSize: 13, fontWeight: FontWeight.w400, color: AppColors.textSecondary),
        bodySmall: TextStyle(fontFamily: defaultFont, fontSize: 11, fontWeight: FontWeight.w400, color: AppColors.textMuted),
        labelLarge: TextStyle(fontFamily: defaultFont, fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.textPrimary),
        labelMedium: TextStyle(fontFamily: defaultFont, fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textSecondary),
        labelSmall: TextStyle(fontFamily: defaultFont, fontSize: 10, fontWeight: FontWeight.w700, color: AppColors.textMuted, letterSpacing: 0.8),
      ),
      iconTheme: const IconThemeData(color: AppColors.textSecondary, size: 20),
      dividerColor: AppColors.borderSubtle,
      cardColor: AppColors.bgCard,
    );
  }
}
