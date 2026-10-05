import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

enum TactileButtonVariant {
  primary,
  secondary,
  danger,
  ghost,
}

/// Tactical high-craft interactive button adhering to Emil Kowalski & Better-UI principles:
/// - Tactile scale-on-press (0.97) with custom cubic ease-out
/// - Concentric corner radiuses
/// - Optical alignment of icons and text
/// - Multi-layer shadows with electric/danger accent halos
/// - Minimum accessible touch target (>= 44px height by default)
class TactileButton extends StatefulWidget {
  final VoidCallback? onPressed;
  final Widget? icon;
  final String label;
  final Widget? child;
  final TactileButtonVariant variant;
  final double height;
  final double? width;
  final double borderRadius;
  final EdgeInsetsGeometry padding;
  final bool isLoading;
  final String? tooltip;

  const TactileButton({
    super.key,
    required this.onPressed,
    this.icon,
    this.label = '',
    this.child,
    this.variant = TactileButtonVariant.primary,
    this.height = 46.0,
    this.width,
    this.borderRadius = AppRadius.lg,
    this.padding = const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
    this.isLoading = false,
    this.tooltip,
  });

  @override
  State<TactileButton> createState() => _TactileButtonState();
}

class _TactileButtonState extends State<TactileButton> {
  bool _isHovered = false;
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final isEnabled = widget.onPressed != null && !widget.isLoading;

    Color bg;
    Color fg;
    Border? border;
    List<BoxShadow> shadows = [];

    switch (widget.variant) {
      case TactileButtonVariant.primary:
        bg = isEnabled
            ? (_isHovered ? const Color(0xFFD8FF78) : AppColors.accentLime)
            : AppColors.accentLime.withValues(alpha: 0.35);
        fg = AppColors.bgPrimary;
        border = Border.all(
          color: Colors.white.withValues(alpha: 0.3),
          width: 1.0,
        );
        if (isEnabled && (_isHovered || _isPressed)) {
          shadows = AppShadows.accentGlow(AppColors.accentLime, opacity: 0.45, blur: 16);
        } else if (isEnabled) {
          shadows = AppShadows.accentGlow(AppColors.accentLime, opacity: 0.25, blur: 10);
        }
        break;

      case TactileButtonVariant.danger:
        bg = isEnabled
            ? (_isHovered
                ? AppColors.accentRed.withValues(alpha: 0.22)
                : AppColors.accentRed.withValues(alpha: 0.12))
            : AppColors.accentRed.withValues(alpha: 0.05);
        fg = isEnabled ? AppColors.accentRed : AppColors.accentRed.withValues(alpha: 0.4);
        border = Border.all(
          color: isEnabled
              ? (_isHovered ? AppColors.accentRed : AppColors.accentRed.withValues(alpha: 0.6))
              : AppColors.accentRed.withValues(alpha: 0.25),
          width: 1.2,
        );
        if (isEnabled && _isHovered) {
          shadows = AppShadows.accentGlow(AppColors.accentRed, opacity: 0.3, blur: 14);
        }
        break;

      case TactileButtonVariant.secondary:
        bg = isEnabled
            ? (_isHovered
                ? AppColors.bgCardLight
                : AppColors.bgCardDark.withValues(alpha: 0.8))
            : AppColors.bgCardDark.withValues(alpha: 0.4);
        fg = isEnabled ? AppColors.textPrimary : AppColors.textMuted;
        border = Border.all(
          color: isEnabled
              ? (_isHovered ? AppColors.accentCyan.withValues(alpha: 0.5) : AppColors.glassBorder)
              : AppColors.borderSubtle,
          width: 1.0,
        );
        if (isEnabled && _isHovered) {
          shadows = [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.35),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ];
        }
        break;

      case TactileButtonVariant.ghost:
        bg = _isHovered ? AppColors.bgCardLight.withValues(alpha: 0.5) : Colors.transparent;
        fg = isEnabled ? AppColors.textPrimary : AppColors.textMuted;
        border = null;
        break;
    }

    final double scale = isEnabled
        ? (_isPressed ? 0.97 : (_isHovered ? 1.01 : 1.0))
        : 1.0;

    Widget content = widget.child ??
        Row(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (widget.isLoading) ...[
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2.2,
                  color: fg,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
            ] else if (widget.icon != null) ...[
              widget.icon!,
              const SizedBox(width: AppSpacing.sm),
            ],
            Flexible(
              child: Text(
                widget.label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontFamily: 'Segoe UI',
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.5,
                  color: fg,
                ),
              ),
            ),
          ],
        );

    Widget button = AnimatedScale(
      scale: scale,
      duration: AppMotion.press,
      curve: AppMotion.easeOut,
      child: MouseRegion(
        cursor: isEnabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
        onEnter: (_) {
          if (isEnabled) setState(() => _isHovered = true);
        },
        onExit: (_) {
          if (isEnabled) {
            setState(() {
              _isHovered = false;
              _isPressed = false;
            });
          }
        },
        child: GestureDetector(
          onTapDown: (_) {
            if (isEnabled) setState(() => _isPressed = true);
          },
          onTapUp: (_) {
            if (isEnabled) setState(() => _isPressed = false);
          },
          onTapCancel: () {
            if (isEnabled) setState(() => _isPressed = false);
          },
          onTap: isEnabled ? widget.onPressed : null,
          behavior: HitTestBehavior.opaque,
          child: AnimatedContainer(
            duration: AppMotion.fast,
            curve: AppMotion.easeOut,
            height: widget.height,
            width: widget.width,
            padding: widget.padding,
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(widget.borderRadius),
              border: border,
              boxShadow: shadows,
            ),
            alignment: Alignment.center,
            child: content,
          ),
        ),
      ),
    );

    if (widget.tooltip != null) {
      return Tooltip(
        message: widget.tooltip!,
        child: button,
      );
    }

    return button;
  }
}
