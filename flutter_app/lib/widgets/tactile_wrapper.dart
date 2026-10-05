import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Reusable micro-interaction wrapper for cards, chips, pills, and custom components.
/// Provides physical scale-on-press (0.97), subtle hover scale, and pointer cursor.
class TactileWrapper extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final double pressScale;
  final double hoverScale;
  final Duration duration;
  final Curve curve;
  final bool enableHover;
  final HitTestBehavior behavior;

  const TactileWrapper({
    super.key,
    required this.child,
    this.onTap,
    this.pressScale = 0.97,
    this.hoverScale = 1.01,
    this.duration = AppMotion.press,
    this.curve = AppMotion.easeOut,
    this.enableHover = true,
    this.behavior = HitTestBehavior.opaque,
  });

  @override
  State<TactileWrapper> createState() => _TactileWrapperState();
}

class _TactileWrapperState extends State<TactileWrapper> {
  bool _isHovered = false;
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final isInteractive = widget.onTap != null;

    final double scale = isInteractive
        ? (_isPressed
            ? widget.pressScale
            : (_isHovered && widget.enableHover ? widget.hoverScale : 1.0))
        : 1.0;

    return AnimatedScale(
      scale: scale,
      duration: widget.duration,
      curve: widget.curve,
      child: isInteractive
          ? MouseRegion(
              cursor: SystemMouseCursors.click,
              onEnter: (_) => setState(() => _isHovered = true),
              onExit: (_) => setState(() {
                _isHovered = false;
                _isPressed = false;
              }),
              child: GestureDetector(
                behavior: widget.behavior,
                onTapDown: (_) => setState(() => _isPressed = true),
                onTapUp: (_) => setState(() => _isPressed = false),
                onTapCancel: () => setState(() => _isPressed = false),
                onTap: widget.onTap,
                child: widget.child,
              ),
            )
          : widget.child,
    );
  }
}
