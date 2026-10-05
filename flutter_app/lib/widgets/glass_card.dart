import 'dart:ui';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Ultra-refined frosted glassmorphic card with backdrop blur, dual-layer shadows,
/// optical highlight borders, and tactile scale-on-press micro-interactions.
class GlassCard extends StatefulWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final double borderRadius;
  final Color? backgroundColor;
  final Color? borderColor;
  final double borderWidth;
  final double blurSigma;
  final VoidCallback? onTap;

  const GlassCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(AppSpacing.lg),
    this.borderRadius = AppRadius.xl,
    this.backgroundColor,
    this.borderColor,
    this.borderWidth = 1.0,
    this.blurSigma = 16.0,
    this.onTap,
  });

  @override
  State<GlassCard> createState() => _GlassCardState();
}

class _GlassCardState extends State<GlassCard> {
  bool _isHovered = false;
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final isInteractive = widget.onTap != null;
    final defaultBg = const Color(0xFF131B2E).withValues(alpha: 0.75);
    final bg = widget.backgroundColor ?? defaultBg;
    final defaultBorder = _isHovered
        ? const Color(0xFF3B4D75).withValues(alpha: 0.8)
        : const Color(0xFF283654).withValues(alpha: 0.6);
    final border = widget.borderColor ?? defaultBorder;

    final scale = isInteractive
        ? (_isPressed ? 0.985 : (_isHovered ? 1.005 : 1.0))
        : 1.0;

    return AnimatedScale(
      scale: scale,
      duration: AppMotion.press,
      curve: AppMotion.easeOut,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(widget.borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: widget.blurSigma, sigmaY: widget.blurSigma),
          child: Container(
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(widget.borderRadius),
              border: Border.all(color: border, width: widget.borderWidth),
              boxShadow: isInteractive && _isHovered
                  ? AppShadows.floating
                  : AppShadows.card,
            ),
            child: Material(
              color: Colors.transparent,
              borderRadius: BorderRadius.circular(widget.borderRadius),
              child: isInteractive
                  ? MouseRegion(
                      cursor: SystemMouseCursors.click,
                      onEnter: (_) => setState(() => _isHovered = true),
                      onExit: (_) => setState(() {
                        _isHovered = false;
                        _isPressed = false;
                      }),
                      child: GestureDetector(
                        onTapDown: (_) => setState(() => _isPressed = true),
                        onTapUp: (_) => setState(() => _isPressed = false),
                        onTapCancel: () => setState(() => _isPressed = false),
                        onTap: widget.onTap,
                        behavior: HitTestBehavior.opaque,
                        child: Padding(
                          padding: widget.padding,
                          child: widget.child,
                        ),
                      ),
                    )
                  : Padding(
                      padding: widget.padding,
                      child: widget.child,
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
