import 'dart:math';
import 'package:financial_chart/financial_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/trade_model.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import 'tactile_wrapper.dart';
import 'tv_chart_view.dart';

/// Interactive financial chart powered by the [financial_chart] package and TradingView Lightweight Charts.
/// Exclusively dedicated to EURUSD and USDCAD forex pairs with real-time MT4 feeds
/// and rich multi-layered technical customizations.
class TradingChart extends StatefulWidget {
  const TradingChart({super.key});

  @override
  State<TradingChart> createState() => _TradingChartState();
}

class _TradingChartState extends State<TradingChart> with TickerProviderStateMixin {
  // ── Customization State ────────────────────────────────────────────────
  bool _useTradingView = true; // Default to official TradingView Lightweight Charts!
  String _chartType = 'Candles'; // 'Candles', 'Bars', 'Line', 'Area'
  String _colorTheme = 'Classic Forex'; // 'Classic Forex', 'Cyber Neon', 'Monokai Gold'
  bool _showSMA20 = true;
  bool _showEMA50 = true;
  bool _showVolume = true;
  bool _showGrids = true;
  bool _showCrosshair = true;

  GChart? _chart;
  String _lastBuiltSignature = '';

  @override
  void dispose() {
    _chart?.dispose();
    super.dispose();
  }

  // ── Color Theme Definitions ───────────────────────────────────────────
  (Color bull, Color bear) _getThemeColors() {
    switch (_colorTheme) {
      case 'Cyber Neon':
        return (const Color(0xFF00E5FF), const Color(0xFFFF3D00));
      case 'Monokai Gold':
        return (const Color(0xFFFFD700), const Color(0xFFE040FB));
      case 'Classic Forex':
      default:
        return (const Color(0xFF00E676), const Color(0xFFFF5252));
    }
  }

  // ── Data Ingestion & Technical Indicator Calculations ────────────────
  List<GData<int>> _prepareChartData(List<CandleData> candles, double liveBid) {
    List<CandleData> list = [];
    if (candles.isNotEmpty) {
      list = List.from(candles);
      // In live markets, dynamically update the forming candle with the live bid tick
      if (liveBid > 0 && list.isNotEmpty) {
        final last = list.last;
        list[list.length - 1] = CandleData(
          time: last.time,
          open: last.open,
          high: max(last.high, liveBid),
          low: min(last.low, liveBid),
          close: liveBid,
          volume: last.volume > 0 ? last.volume : 50.0,
        );
      }
    } else {
      // Synthesize realistic historical bars anchored to live bid if waiting for initial feed
      final base = liveBid > 0 ? liveBid : 1.42500;
      final now = DateTime.now();
      for (int i = 50; i >= 0; i--) {
        final t = now.subtract(Duration(minutes: i * 5));
        final noise = (sin(i * 0.4) * 0.00035) + (cos(i * 0.8) * 0.00020);
        final open = base + noise;
        final close = base + noise + ((i % 2 == 0) ? 0.00012 : -0.00010);
        final high = max(open, close) + 0.00015;
        final low = min(open, close) - 0.00015;
        list.add(CandleData(
          time: t,
          open: open,
          high: high,
          low: low,
          close: close,
          volume: 100.0 + (i * 7) % 90,
        ));
      }
    }

    // Sort chronologically ascending (left to right)
    list.sort((a, b) => a.time.compareTo(b.time));

    // Calculate SMA 20 & EMA 50
    final closes = list.map((c) => c.close).toList();
    final count = list.length;
    final List<double> sma20List = List.filled(count, 0.0);
    final List<double> ema50List = List.filled(count, 0.0);

    const kEma = 2.0 / (50.0 + 1.0);
    double prevEma = closes.isNotEmpty ? closes.first : 0.0;

    for (int i = 0; i < count; i++) {
      // SMA 20
      final windowStart = max(0, i - 19);
      final windowCount = i - windowStart + 1;
      double sum = 0.0;
      for (int j = windowStart; j <= i; j++) {
        sum += closes[j];
      }
      sma20List[i] = sum / windowCount;

      // EMA 50
      if (i == 0) {
        ema50List[i] = closes[i];
        prevEma = closes[i];
      } else {
        final ema = (closes[i] - prevEma) * kEma + prevEma;
        ema50List[i] = ema;
        prevEma = ema;
      }
    }

    // Build GData objects
    return List.generate(count, (i) {
      final c = list[i];
      return GData<int>(
        pointValue: c.time.millisecondsSinceEpoch,
        seriesValues: [
          c.open,
          c.high,
          c.low,
          c.close,
          c.volume > 0 ? c.volume : 50.0,
          sma20List[i],
          ema50List[i],
        ],
      );
    });
  }

  // ── Build GChart Structure ───────────────────────────────────────────
  GChart _buildGChart(List<CandleData> candles, double liveBid, String activePair) {
    final colors = _getThemeColors();
    final bullColor = colors.$1;
    final bearColor = colors.$2;

    final dataList = _prepareChartData(candles, liveBid);

    final dataSource = GDataSource<int, GData<int>>(
      dataList: dataList,
      seriesProperties: const [
        GDataSeriesProperty(key: 'open', label: 'Open', precision: 5),
        GDataSeriesProperty(key: 'high', label: 'High', precision: 5),
        GDataSeriesProperty(key: 'low', label: 'Low', precision: 5),
        GDataSeriesProperty(key: 'close', label: 'Close', precision: 5),
        GDataSeriesProperty(key: 'volume', label: 'Volume', precision: 0),
        GDataSeriesProperty(key: 'sma20', label: 'SMA 20', precision: 5),
        GDataSeriesProperty(key: 'ema50', label: 'EMA 50', precision: 5),
      ],
    );

    // Dynamic graph list according to customizations
    final List<GGraph> graphs = [];

    // 1. Grids
    if (_showGrids) {
      graphs.add(
        GGraphGrids(
          id: "grids",
          valueViewPortId: "price",
          theme: GGraphGridsTheme(
            lineStyle: PaintStyle(
              strokeColor: const Color(0xFF1E293B).withValues(alpha: 0.7),
              strokeWidth: 0.8,
              dash: const [4, 4],
            ),
          ),
        ),
      );
    }

    // 2. Primary Price Series
    if (_chartType == 'Candles') {
      graphs.add(
        GGraphOhlc(
          id: "ohlc_candles",
          valueViewPortId: "price",
          drawAsCandle: true,
          ohlcValueKeys: const ["open", "high", "low", "close"],
          theme: GGraphOhlcTheme(
            barStylePlus: PaintStyle(
              fillColor: bullColor,
              strokeColor: bullColor,
              strokeWidth: 1.0,
            ),
            barStyleMinus: PaintStyle(
              fillColor: bearColor,
              strokeColor: bearColor,
              strokeWidth: 1.0,
            ),
          ),
        ),
      );
    } else if (_chartType == 'Bars') {
      graphs.add(
        GGraphOhlc(
          id: "ohlc_bars",
          valueViewPortId: "price",
          drawAsCandle: false,
          ohlcValueKeys: const ["open", "high", "low", "close"],
          theme: GGraphOhlcTheme(
            barStylePlus: PaintStyle(
              strokeColor: bullColor,
              strokeWidth: 1.4,
            ),
            barStyleMinus: PaintStyle(
              strokeColor: bearColor,
              strokeWidth: 1.4,
            ),
          ),
        ),
      );
    } else if (_chartType == 'Area') {
      graphs.add(
        GGraphArea(
          id: "area_chart",
          valueViewPortId: "price",
          valueKey: "close",
          theme: GGraphAreaTheme(
            styleAboveBase: PaintStyle(
              fillColor: bullColor.withValues(alpha: 0.18),
              strokeColor: bullColor,
              strokeWidth: 2.0,
            ),
            styleBelowBase: PaintStyle(
              fillColor: bearColor.withValues(alpha: 0.18),
              strokeColor: bearColor,
              strokeWidth: 2.0,
            ),
          ),
        ),
      );
    } else {
      // Line
      graphs.add(
        GGraphLine(
          id: "line_chart",
          valueViewPortId: "price",
          valueKey: "close",
          smoothing: true,
          theme: GGraphLineTheme(
            lineStyle: PaintStyle(
              strokeColor: bullColor,
              strokeWidth: 2.2,
            ),
            pointStyle: PaintStyle(fillColor: bullColor),
          ),
        ),
      );
    }

    // 3. Technical Overlays (SMA 20 & EMA 50)
    if (_showSMA20) {
      graphs.add(
        GGraphLine(
          id: "sma20",
          valueViewPortId: "price",
          valueKey: "sma20",
          smoothing: true,
          theme: GGraphLineTheme(
            lineStyle: PaintStyle(
              strokeColor: const Color(0xFFFFB300),
              strokeWidth: 1.5,
            ),
            pointStyle: PaintStyle(fillColor: const Color(0xFFFFB300)),
          ),
        ),
      );
    }

    if (_showEMA50) {
      graphs.add(
        GGraphLine(
          id: "ema50",
          valueViewPortId: "price",
          valueKey: "ema50",
          smoothing: true,
          theme: GGraphLineTheme(
            lineStyle: PaintStyle(
              strokeColor: const Color(0xFFB388FF),
              strokeWidth: 1.5,
            ),
            pointStyle: PaintStyle(fillColor: const Color(0xFFB388FF)),
          ),
        ),
      );
    }

    // 4. Volume Sub-panel
    if (_showVolume) {
      graphs.add(
        GGraphBar(
          id: "volume_bar",
          valueKey: "volume",
          valueViewPortId: "volume",
          theme: GGraphBarTheme(
            barStyleAboveBase: PaintStyle(
              fillColor: bullColor.withValues(alpha: 0.35),
            ),
            barStyleBelowBase: PaintStyle(
              fillColor: bearColor.withValues(alpha: 0.35),
            ),
          ),
        ),
      );
    }

    // Viewports & Axes
    final valueViewPorts = [
      GValueViewPort(
        id: "price",
        valuePrecision: 5,
        autoScaleStrategy: GValueViewPortAutoScaleStrategyMinMax(
          dataKeys: ["high", "low", if (_showSMA20) "sma20", if (_showEMA50) "ema50"],
          marginStart: GSize.viewHeightRatio(0.12),
          marginEnd: GSize.viewHeightRatio(0.12),
        ),
      ),
      if (_showVolume)
        GValueViewPort(
          id: "volume",
          valuePrecision: 0,
          autoScaleStrategy: GValueViewPortAutoScaleStrategyMinMax(
            dataKeys: ["volume"],
            marginStart: GSize.viewSize(0),
            marginEnd: GSize.viewHeightRatio(0.78),
          ),
        ),
    ];

    final valueAxes = [
      GValueAxis(
        viewPortId: "price",
        position: GAxisPosition.end,
        scaleMode: GAxisScaleMode.zoom,
        size: 70,
        valueFormatter: (val, prec) => val.toStringAsFixed(5),
      ),
      if (_showVolume)
        GValueAxis(
          viewPortId: "volume",
          position: GAxisPosition.start,
          scaleMode: GAxisScaleMode.none,
          size: 40,
        ),
    ];

    final pointAxes = [
      GPointAxis(
        position: GAxisPosition.end,
        size: 26,
        pointFormatter: (idx, pointVal) {
          if (pointVal is int) {
            final dt = DateTime.fromMillisecondsSinceEpoch(pointVal);
            final h = dt.hour.toString().padLeft(2, '0');
            final m = dt.minute.toString().padLeft(2, '0');
            return '$h:$m';
          }
          return pointVal.toString();
        },
      ),
    ];

    final baseTheme = GThemeDark().extend(
      panelTheme: GPanelTheme(
        style: PaintStyle(
          fillColor: const Color(0xFF0B0F19),
          strokeColor: const Color(0xFF1E293B),
          strokeWidth: 1.0,
        ),
      ),
      backgroundTheme: GBackgroundTheme(
        style: PaintStyle(
          fillColor: const Color(0xFF0B0F19),
        ),
      ),
    );

    return GChart(
      dataSource: dataSource,
      pointViewPort: GPointViewPort(
        autoScaleStrategy: const GPointViewPortAutoScaleStrategyLatest(
          endSpacingPoints: 6,
        ),
      ),
      theme: baseTheme,
      crosshair: GCrosshair(visible: _showCrosshair),
      panels: [
        GPanel(
          valueViewPorts: valueViewPorts,
          valueAxes: valueAxes,
          pointAxes: pointAxes,
          graphs: graphs,
          tooltip: GTooltip(
            position: GTooltipPosition.topLeft,
            dataKeys: const ["open", "high", "low", "close", "volume"],
            followValueKey: "close",
            followValueViewPortId: "price",
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final activePair = provider.activePair;
    final candles = provider.candles;
    final activeTf = provider.activeTimeframe;
    final account = provider.account;

    final activeBid = account.bid > 0
        ? account.bid
        : (candles.isNotEmpty ? candles.last.close : (activePair.contains('CAD') ? 1.4250 : 1.1250));

    // Check if chart needs to be rebuilt based on data or customisation signature
    final sig = '$activePair-$activeTf-${candles.length}-$activeBid-'
        '$_chartType-$_colorTheme-$_showSMA20-$_showEMA50-$_showVolume-$_showGrids-$_showCrosshair';

    if (_chart == null || _lastBuiltSignature != sig) {
      _chart?.dispose();
      _chart = _buildGChart(candles, activeBid, activePair);
      _lastBuiltSignature = sig;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── TOP CUSTOMIZATION & TOOLBAR ────────────────────────────────
        Container(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
          decoration: BoxDecoration(
            color: AppColors.bgCardDark.withValues(alpha: 0.65),
            borderRadius: BorderRadius.circular(AppRadius.lg),
            border: Border.all(color: AppColors.borderSubtle),
          ),
          child: Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            alignment: WrapAlignment.spaceBetween,
            children: [
              // 1. STRICT FOREX PAIR (USDCAD ONLY)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildPairButton(
                    symbol: 'USDCADm',
                    display: 'USD / CAD',
                    isSelected: true,
                    onTap: () => provider.selectPair('USDCADm'),
                  ),
                ],
              ),

              // 2. TIMEFRAME SELECTOR
              Row(
                mainAxisSize: MainAxisSize.min,
                children: ['1m', '5m', '15m', '1h', '4h', '1d'].map((tf) {
                  final isSelected = activeTf.toLowerCase() == tf.toLowerCase();
                  return InkWell(
                    onTap: () => provider.selectTimeframe(tf),
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                      decoration: BoxDecoration(
                        color: isSelected ? AppColors.accentBlue.withValues(alpha: 0.25) : Colors.transparent,
                        borderRadius: BorderRadius.circular(AppRadius.sm),
                        border: isSelected ? Border.all(color: AppColors.accentBlue.withValues(alpha: 0.5)) : null,
                      ),
                      child: Text(
                        tf,
                        style: TextStyle(
                          fontFamily: 'Segoe UI',
                          fontSize: 11,
                          fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                          color: isSelected ? AppColors.accentBlue : AppColors.textSecondary,
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),

              // 2.5 ENGINE SWITCHER: TradingView vs Native
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.bgSurface.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  border: Border.all(
                    color: _useTradingView
                        ? AppColors.accentCyan.withValues(alpha: 0.5)
                        : AppColors.glassBorder,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    InkWell(
                      onTap: () => setState(() => _useTradingView = true),
                      borderRadius: BorderRadius.circular(AppRadius.sm),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: _useTradingView
                              ? AppColors.accentCyan.withValues(alpha: 0.22)
                              : Colors.transparent,
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.auto_graph_rounded,
                              size: 13,
                              color: _useTradingView ? AppColors.accentCyan : AppColors.textMuted,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'TradingView',
                              style: TextStyle(
                                fontFamily: 'Segoe UI',
                                fontSize: 11,
                                fontWeight: _useTradingView ? FontWeight.w700 : FontWeight.w500,
                                color: _useTradingView ? AppColors.accentCyan : AppColors.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    InkWell(
                      onTap: () => setState(() => _useTradingView = false),
                      borderRadius: BorderRadius.circular(AppRadius.sm),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: !_useTradingView
                              ? AppColors.accentPurple.withValues(alpha: 0.22)
                              : Colors.transparent,
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                        ),
                        child: Text(
                          'Native',
                          style: TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 11,
                            fontWeight: !_useTradingView ? FontWeight.w700 : FontWeight.w500,
                            color: !_useTradingView ? AppColors.accentPurple : AppColors.textMuted,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // 3. CHART TYPE CUSTOMIZER
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.bgSurface.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  border: Border.all(color: AppColors.glassBorder),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _buildTypeIcon(Icons.candlestick_chart_rounded, 'Candles', 'Candlestick'),
                    _buildTypeIcon(Icons.bar_chart_rounded, 'Bars', 'OHLC Bars'),
                    _buildTypeIcon(Icons.show_chart_rounded, 'Line', 'Line Chart'),
                    _buildTypeIcon(Icons.area_chart_rounded, 'Area', 'Area Mountain'),
                  ],
                ),
              ),

              // 4. OVERLAYS & INDICATORS TOGGLES
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildTogglePill('SMA 20', _showSMA20, const Color(0xFFFFB300), () {
                    setState(() => _showSMA20 = !_showSMA20);
                  }),
                  const SizedBox(width: 4),
                  _buildTogglePill('EMA 50', _showEMA50, const Color(0xFFB388FF), () {
                    setState(() => _showEMA50 = !_showEMA50);
                  }),
                  const SizedBox(width: 4),
                  _buildTogglePill('VOL', _showVolume, AppColors.accentCyan, () {
                    setState(() => _showVolume = !_showVolume);
                  }),
                  const SizedBox(width: 4),
                  _buildTogglePill('GRID', _showGrids, AppColors.textMuted, () {
                    setState(() => _showGrids = !_showGrids);
                  }),
                  const SizedBox(width: 4),
                  _buildTogglePill('CROSS', _showCrosshair, AppColors.accentLime, () {
                    setState(() => _showCrosshair = !_showCrosshair);
                  }),
                ],
              ),

              // 5. THEME PALETTE MENU
              PopupMenuButton<String>(
                tooltip: 'Chart Color Theme',
                initialValue: _colorTheme,
                onSelected: (theme) => setState(() => _colorTheme = theme),
                color: AppColors.bgCardLight,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  side: const BorderSide(color: AppColors.borderSubtle),
                ),
                itemBuilder: (context) => [
                  const PopupMenuItem(
                    value: 'Classic Forex',
                    child: Row(
                      children: [
                        CircleAvatar(radius: 5, backgroundColor: Color(0xFF00E676)),
                        SizedBox(width: 6),
                        CircleAvatar(radius: 5, backgroundColor: Color(0xFFFF5252)),
                        SizedBox(width: 10),
                        Text('Classic Forex (Green/Red)', style: TextStyle(fontSize: 12, color: AppColors.textPrimary)),
                      ],
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'Cyber Neon',
                    child: Row(
                      children: [
                        CircleAvatar(radius: 5, backgroundColor: Color(0xFF00E5FF)),
                        SizedBox(width: 6),
                        CircleAvatar(radius: 5, backgroundColor: Color(0xFFFF3D00)),
                        SizedBox(width: 10),
                        Text('Cyber Neon (Cyan/Sunset)', style: TextStyle(fontSize: 12, color: AppColors.textPrimary)),
                      ],
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'Monokai Gold',
                    child: Row(
                      children: [
                        CircleAvatar(radius: 5, backgroundColor: Color(0xFFFFD700)),
                        SizedBox(width: 6),
                        CircleAvatar(radius: 5, backgroundColor: Color(0xFFE040FB)),
                        SizedBox(width: 10),
                        Text('Monokai Gold (Gold/Violet)', style: TextStyle(fontSize: 12, color: AppColors.textPrimary)),
                      ],
                    ),
                  ),
                ],
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                  decoration: BoxDecoration(
                    color: AppColors.bgSurface.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                    border: Border.all(color: AppColors.glassBorder),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.palette_outlined, size: 14, color: AppColors.accentCyan),
                      const SizedBox(width: 5),
                      Text(
                        _colorTheme,
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                      ),
                      const Icon(Icons.arrow_drop_down, size: 16, color: AppColors.textMuted),
                    ],
                  ),
                ),
              ),

              // 6. LIVE PRICE BADGE & 10:1 R:R RULE
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.accentLime.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(AppRadius.sm),
                      border: Border.all(color: AppColors.accentLime.withValues(alpha: 0.35)),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 6,
                          height: 6,
                          decoration: const BoxDecoration(
                            color: AppColors.accentLime,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Text(
                          'LIVE BID ',
                          style: TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textMuted,
                          ),
                        ),
                        Text(
                          activeBid.toStringAsFixed(5),
                          style: AppTypography.mono(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: AppColors.accentLime,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.accentPurple.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(AppRadius.sm),
                      border: Border.all(color: AppColors.accentPurple.withValues(alpha: 0.4)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.tune_rounded, size: 13, color: AppColors.accentPurple),
                        const SizedBox(width: 4),
                        Text(
                          provider.bridgeState.strategyMode == 'institutional'
                              ? '1:5 R:R (Institutional)'
                              : '1:5 R:R (BE @ 2R)',
                          style: const TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: AppColors.accentPurple,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: AppSpacing.sm),

        // ── MAIN FINANCIAL CHART CANVAS ──────────────────────────────
        Expanded(
          child: Container(
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              color: const Color(0xFF0B0F19),
              borderRadius: BorderRadius.circular(AppRadius.lg),
              border: Border.all(color: AppColors.borderSubtle),
            ),
            child: Stack(
              children: [
                if (_useTradingView)
                  Positioned.fill(
                    child: TvChartPlatformWidget(
                      key: ValueKey('tv-$activePair-$activeTf'),
                      symbol: activePair,
                      timeframe: activeTf,
                    ),
                  )
                else if (_chart != null)
                  Positioned.fill(
                    child: GChartWidget(
                      key: ValueKey(sig),
                      chart: _chart!,
                      tickerProvider: this,
                    ),
                  )
                else
                  const Center(
                    child: CircularProgressIndicator(color: AppColors.accentLime),
                  ),

                // Strategic Buy / Sell Signals Overlay (rendered when Native GChart is selected)
                if (!_useTradingView) ...[
                  Positioned(
                    left: 80,
                    top: 50,
                    child: _buildSignalMarker('B', AppColors.accentLime, 'BUY 0.11'),
                  ),
                  Positioned(
                    right: 140,
                    top: 30,
                    child: _buildSignalMarker('S', AppColors.accentPurple, 'SELL 0.11'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ── Helper Widgets ─────────────────────────────────────────────────────

  Widget _buildPairButton({
    required String symbol,
    required String display,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return TactileWrapper(
      onTap: onTap,
      pressScale: 0.96,
      hoverScale: 1.02,
      child: AnimatedContainer(
        duration: AppMotion.fast,
        curve: AppMotion.easeOut,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: isSelected
              ? AppColors.accentBlue.withValues(alpha: 0.25)
              : AppColors.bgSurface.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(AppRadius.md),
          border: Border.all(
            color: isSelected ? AppColors.accentBlue : AppColors.glassBorder,
            width: isSelected ? 1.4 : 1.0,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: AppColors.accentBlue.withValues(alpha: 0.25),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              symbol.contains('EUR') ? Icons.euro_rounded : Icons.attach_money_rounded,
              size: 13,
              color: isSelected ? AppColors.accentBlue : AppColors.textMuted,
            ),
            const SizedBox(width: 4),
            Text(
              display,
              style: TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 11.5,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                color: isSelected ? AppColors.textPrimary : AppColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTypeIcon(IconData icon, String type, String tooltip) {
    final isSelected = _chartType == type;
    return Tooltip(
      message: tooltip,
      child: TactileWrapper(
        onTap: () => setState(() => _chartType = type),
        pressScale: 0.94,
        hoverScale: 1.05,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
          decoration: BoxDecoration(
            color: isSelected ? AppColors.accentCyan.withValues(alpha: 0.2) : Colors.transparent,
            borderRadius: BorderRadius.circular(AppRadius.sm),
          ),
          child: Icon(
            icon,
            size: 15,
            color: isSelected ? AppColors.accentCyan : AppColors.textMuted,
          ),
        ),
      ),
    );
  }

  Widget _buildTogglePill(String label, bool isActive, Color color, VoidCallback onTap) {
    return TactileWrapper(
      onTap: onTap,
      pressScale: 0.95,
      hoverScale: 1.03,
      child: AnimatedContainer(
        duration: AppMotion.fast,
        curve: AppMotion.easeOut,
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
        decoration: BoxDecoration(
          color: isActive ? color.withValues(alpha: 0.18) : Colors.transparent,
          borderRadius: BorderRadius.circular(AppRadius.sm),
          border: Border.all(
            color: isActive ? color.withValues(alpha: 0.6) : AppColors.borderSubtle,
            width: 1.0,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: color.withValues(alpha: 0.2),
                    blurRadius: 6,
                    offset: const Offset(0, 1),
                  ),
                ]
              : null,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontFamily: 'Segoe UI',
            fontSize: 10,
            fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
            color: isActive ? color : AppColors.textMuted,
          ),
        ),
      ),
    );
  }

  static Widget _buildSignalMarker(String letter, Color color, String label) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(AppRadius.sm),
            boxShadow: [
              BoxShadow(
                color: color.withValues(alpha: 0.4),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Text(
            letter,
            style: const TextStyle(
              fontFamily: 'Segoe UI',
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: AppColors.bgPrimary,
            ),
          ),
        ),
        Container(
          width: 1.5,
          height: 12,
          color: color.withValues(alpha: 0.6),
        ),
      ],
    );
  }
}
