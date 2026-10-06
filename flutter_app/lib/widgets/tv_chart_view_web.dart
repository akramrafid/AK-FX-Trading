// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;
import 'package:flutter/material.dart';

/// Web implementation of TradingView Lightweight Charts embedded view.
class TvChartPlatformWidget extends StatefulWidget {
  final String symbol;
  final String timeframe;

  const TvChartPlatformWidget({
    super.key,
    required this.symbol,
    required this.timeframe,
  });

  @override
  State<TvChartPlatformWidget> createState() => _TvChartPlatformWidgetState();
}

class _TvChartPlatformWidgetState extends State<TvChartPlatformWidget> {
  static final Set<String> _registeredTypes = {};
  late final String _viewType;
  html.IFrameElement? _iframe;

  @override
  void initState() {
    super.initState();
    _viewType = 'tv-chart-view-${widget.symbol}-${widget.timeframe}';

    if (!_registeredTypes.contains(_viewType)) {
      _registeredTypes.add(_viewType);
      ui_web.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
        final iframe = html.IFrameElement()
          ..id = 'tv-iframe-$viewId'
          ..src = '/tv_chart.html?symbol=${Uri.encodeComponent(widget.symbol)}&tf=${Uri.encodeComponent(widget.timeframe)}'
          ..style.border = 'none'
          ..style.width = '100%'
          ..style.height = '100%'
          ..allow = 'fullscreen';
        _iframe = iframe;
        return iframe;
      });
    }
  }

  @override
  void didUpdateWidget(covariant TvChartPlatformWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.symbol != widget.symbol || oldWidget.timeframe != widget.timeframe) {
      _iframe?.contentWindow?.postMessage({
        'type': 'set_pair',
        'symbol': widget.symbol,
      }, '*');
      _iframe?.contentWindow?.postMessage({
        'type': 'set_timeframe',
        'timeframe': widget.timeframe,
      }, '*');
    }
  }

  @override
  Widget build(BuildContext context) {
    return HtmlElementView(viewType: _viewType);
  }
}
