import 'dart:ui';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Impeccable frosted glassmorphic card with backdrop blur and refined gradient stroke.
class GlassCard extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final bg = backgroundColor ?? const Color(0xFF131B2E).withValues(alpha: 0.75);
    final border = borderColor ?? const Color(0xFF283654).withValues(alpha: 0.6);

    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
        child: Container(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(borderRadius),
            border: Border.all(color: border, width: borderWidth),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.35),
                blurRadius: 24,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Material(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(borderRadius),
            child: InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(borderRadius),
              child: Padding(
                padding: padding,
                child: child,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
