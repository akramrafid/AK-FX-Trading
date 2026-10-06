import 'package:flutter/material.dart';

/// Desktop / Non-web stub fallback for TradingView chart.
class TvChartPlatformWidget extends StatelessWidget {
  final String symbol;
  final String timeframe;

  const TvChartPlatformWidget({
    super.key,
    required this.symbol,
    required this.timeframe,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0B0F19),
      alignment: Alignment.center,
      child: const Text(
        'TradingView Lightweight Chart (Running in Web Desktop mode)',
        style: TextStyle(color: Colors.white70, fontSize: 13),
      ),
    );
  }
}
