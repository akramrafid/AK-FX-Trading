import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../models/trade_model.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import 'tactile_wrapper.dart';

class TransactionsTable extends StatefulWidget {
  const TransactionsTable({super.key});

  @override
  State<TransactionsTable> createState() => _TransactionsTableState();
}

class _TransactionsTableState extends State<TransactionsTable> {
  int _selectedSubTab = 0; // 0 = Open Positions, 1 = Order History

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final trades = provider.trades;

    // Separate open MT4 orders from historical closed orders
    final openOrders = trades.where((t) => t.status == TradeStatus.filled).toList();
    final closedOrders = trades.where((t) => t.status == TradeStatus.closed).toList();
    final displayOpenOrders = openOrders;
    final currentDisplayList = _selectedSubTab == 0 ? displayOpenOrders : closedOrders;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Filter Sub-Tabs Header ──────────────────────────────────
        Row(
          children: [
            _buildSubTab(0, 'Open Positions', displayOpenOrders.length, AppColors.accentGreen),
            const SizedBox(width: AppSpacing.sm),
            _buildSubTab(1, 'Order History', closedOrders.length, AppColors.accentBlue),
            const Spacer(),
            TextButton.icon(
              onPressed: () {
                provider.refreshTrades();
                provider.refreshAccount();
              },
              icon: const Icon(Icons.refresh_rounded, size: 14, color: AppColors.textMuted),
              label: const Text(
                'Sync MT4',
                style: TextStyle(
                  fontFamily: 'Segoe UI',
                  fontSize: 11.5,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textMuted,
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: AppSpacing.sm),

        // ── Table Column Headers ────────────────────────────────────
        Container(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
          decoration: BoxDecoration(
            color: AppColors.bgCardDark.withValues(alpha: 0.5),
            borderRadius: BorderRadius.circular(AppRadius.sm),
            border: Border.all(color: AppColors.borderSubtle.withValues(alpha: 0.5)),
          ),
          child: const Row(
            children: [
              Expanded(
                flex: 3,
                child: Text(
                  'ORDER & INSTRUMENT',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              Expanded(
                flex: 2,
                child: Text(
                  'LOTS / SL & TP',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              Expanded(
                flex: 3,
                child: Text(
                  'TERMINAL STATUS',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              Expanded(
                flex: 2,
                child: Text(
                  'OPEN / P&L (USD)',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                    letterSpacing: 0.8,
                  ),
                  textAlign: TextAlign.right,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: AppSpacing.xs),

        // ── Scrollable Rows ─────────────────────────────────────────
        Expanded(
          child: currentDisplayList.isEmpty
              ? _buildEmptyState()
              : ListView.builder(
                  itemCount: currentDisplayList.length,
                  padding: EdgeInsets.zero,
                  itemBuilder: (context, index) {
                    final trade = currentDisplayList[index];
                    final isBuy = trade.direction == Direction.buy;
                    final timeFormat = DateFormat('HH:mm:ss');
                    final isPositive = trade.pnl >= 0;

                    return TactileWrapper(
                      onTap: () {},
                      pressScale: 0.99,
                      hoverScale: 1.005,
                      child: Container(
                        margin: const EdgeInsets.only(bottom: AppSpacing.xs),
                        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 8),
                        decoration: BoxDecoration(
                          color: AppColors.bgCardLight.withValues(alpha: 0.28),
                          borderRadius: BorderRadius.circular(AppRadius.md),
                          border: Border.all(
                            color: isBuy
                                ? AppColors.accentGreen.withValues(alpha: 0.2)
                                : AppColors.accentPurple.withValues(alpha: 0.2),
                          ),
                        ),
                        child: Row(
                        children: [
                          // 1. Order + Pair
                          Expanded(
                            flex: 3,
                            child: Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: isBuy
                                        ? AppColors.accentGreen.withValues(alpha: 0.18)
                                        : AppColors.accentPurple.withValues(alpha: 0.18),
                                    borderRadius: BorderRadius.circular(AppRadius.xs),
                                  ),
                                  child: Text(
                                    isBuy ? 'BUY' : 'SELL',
                                    style: TextStyle(
                                      fontFamily: 'Segoe UI',
                                      fontSize: 10,
                                      fontWeight: FontWeight.w800,
                                      color: isBuy ? AppColors.accentGreen : AppColors.accentPurple,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: AppSpacing.sm),
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      trade.symbol,
                                      style: const TextStyle(
                                        fontFamily: 'Segoe UI',
                                        fontSize: 12,
                                        fontWeight: FontWeight.w700,
                                        color: AppColors.textPrimary,
                                      ),
                                    ),
                                    Text(
                                      '#${trade.ticket}',
                                      style: AppTypography.mono(
                                        fontSize: 9.5,
                                        color: AppColors.textMuted,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),

                          // 2. Lots + SL/TP
                          Expanded(
                            flex: 2,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '${trade.lots.toStringAsFixed(2)} lots',
                                  style: AppTypography.mono(
                                    fontSize: 11.5,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                                Text(
                                  'SL: ${trade.slPrice > 0 ? trade.slPrice.toStringAsFixed(5) : "-"}',
                                  style: AppTypography.mono(
                                    fontSize: 9.5,
                                    color: AppColors.textMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // 3. Status + Time
                          Expanded(
                            flex: 3,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      width: 6,
                                      height: 6,
                                      decoration: BoxDecoration(
                                        color: trade.status == TradeStatus.filled
                                            ? AppColors.accentGreen
                                            : AppColors.accentBlue,
                                        shape: BoxShape.circle,
                                      ),
                                    ),
                                    const SizedBox(width: 5),
                                    Text(
                                      trade.status == TradeStatus.filled ? 'MT4 Live Filled' : 'Closed',
                                      style: TextStyle(
                                        fontFamily: 'Segoe UI',
                                        fontSize: 10.5,
                                        fontWeight: FontWeight.w600,
                                        color: trade.status == TradeStatus.filled
                                            ? AppColors.accentGreen
                                            : AppColors.textSecondary,
                                      ),
                                    ),
                                  ],
                                ),
                                Text(
                                  'Opened ${timeFormat.format(trade.createdAt)}',
                                  style: const TextStyle(
                                    fontFamily: 'Segoe UI',
                                    fontSize: 9.5,
                                    color: AppColors.textMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // 4. Entry Price & PnL
                          Expanded(
                            flex: 2,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  trade.entryPrice.toStringAsFixed(5),
                                  style: AppTypography.mono(
                                    fontSize: 11.5,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                                Text(
                                  trade.pnl != 0
                                      ? '${isPositive ? "+" : ""}\$${trade.pnl.toStringAsFixed(2)}'
                                      : 'Active',
                                  style: AppTypography.mono(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    color: isPositive
                                        ? AppColors.accentGreen
                                        : AppColors.accentRed,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
                ),
        ),
      ],
    );
  }

  Widget _buildSubTab(int index, String label, int count, Color activeColor) {
    final isSelected = _selectedSubTab == index;

    return TactileWrapper(
      onTap: () => setState(() => _selectedSubTab = index),
      pressScale: 0.95,
      hoverScale: 1.02,
      child: AnimatedContainer(
        duration: AppMotion.fast,
        curve: AppMotion.easeOut,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: isSelected ? activeColor.withValues(alpha: 0.15) : Colors.transparent,
          borderRadius: BorderRadius.circular(AppRadius.md),
          border: Border.all(
            color: isSelected ? activeColor.withValues(alpha: 0.4) : Colors.transparent,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: activeColor.withValues(alpha: 0.15),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 12,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                color: isSelected ? AppColors.textPrimary : AppColors.textSecondary,
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              decoration: BoxDecoration(
                color: isSelected ? activeColor : AppColors.bgCardDark,
                borderRadius: BorderRadius.circular(AppRadius.xs),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  fontFamily: 'Segoe UI',
                  fontSize: 9.5,
                  fontWeight: FontWeight.w700,
                  color: isSelected ? AppColors.bgPrimary : AppColors.textMuted,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    final isOpenTab = _selectedSubTab == 0;
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isOpenTab ? Icons.radar_rounded : Icons.receipt_long_outlined,
              size: 36,
              color: isOpenTab
                  ? AppColors.accentLime.withValues(alpha: 0.6)
                  : AppColors.textMuted.withValues(alpha: 0.5),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              isOpenTab ? 'No Active Open Positions' : 'No Closed Orders in Ledger',
              style: const TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              isOpenTab
                  ? 'MT4 bridge is online & scanning broker M5 candles for TrendWise setups.'
                  : 'Closed trades and realized P&L will appear here.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 11,
                color: AppColors.textMuted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
