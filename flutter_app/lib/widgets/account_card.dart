import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class AccountCard extends StatelessWidget {
  const AccountCard({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final account = provider.account;
    final bridge = provider.bridgeState;
    final isRunning = bridge.isRunning;
    final isHalted = bridge.emergencyHalt;

    final profitPercent = account.balance > 0 ? (account.profit / account.balance) * 100 : 0.0;
    final isProfitPositive = account.profit >= 0;

    return GlassCard(
      backgroundColor: AppColors.bgCardDark.withValues(alpha: 0.92),
      borderColor: AppColors.glassBorder,
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header: Account Title + Exness Broker Badge ────────────
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Row(
                children: [
                  Icon(Icons.account_balance_wallet_outlined, size: 16, color: AppColors.accentLime),
                  SizedBox(width: 8),
                  Text(
                    'Trading Account',
                    style: TextStyle(
                      fontFamily: 'Segoe UI',
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ],
              ),
              Flexible(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.accentLime.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(AppRadius.sm),
                    border: Border.all(color: AppColors.accentLime.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          color: AppColors.accentLime,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 5),
                      Flexible(
                        child: Text(
                          '${account.company} #${account.accountNumber}',
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 10.5,
                            fontWeight: FontWeight.w700,
                            color: AppColors.accentLime,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSpacing.lg),

          // ── Big Bold Equity Display with Floating PnL Pill ──────────
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: AppSpacing.sm,
            runSpacing: 4,
            children: [
              Text(
                '\$${account.equity.toStringAsFixed(2)}',
                style: AppTypography.mono(
                  fontSize: 34,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                  letterSpacing: -1.0,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: isProfitPositive
                      ? AppColors.accentGreen.withValues(alpha: 0.15)
                      : AppColors.accentRed.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(AppRadius.sm),
                  border: Border.all(
                    color: isProfitPositive
                        ? AppColors.accentGreen.withValues(alpha: 0.4)
                        : AppColors.accentRed.withValues(alpha: 0.4),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      isProfitPositive ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
                      size: 11,
                      color: isProfitPositive ? AppColors.accentGreen : AppColors.accentRed,
                    ),
                    const SizedBox(width: 2),
                    Text(
                      '${isProfitPositive ? '+' : ''}\$${account.profit.toStringAsFixed(2)} (${profitPercent.toStringAsFixed(2)}%)',
                      style: AppTypography.mono(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: isProfitPositive ? AppColors.accentGreen : AppColors.accentRed,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: 2),

          const Text(
            'TOTAL ACCOUNT EQUITY (USD)',
            style: TextStyle(
              fontFamily: 'Segoe UI',
              fontSize: 9.5,
              fontWeight: FontWeight.w700,
              color: AppColors.textMuted,
              letterSpacing: 1.2,
            ),
          ),

          const SizedBox(height: AppSpacing.lg),

          // ── Metrics Strip: Balance, Free Margin, Margin, Level ────────
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.bgCardLight.withValues(alpha: 0.35),
              borderRadius: BorderRadius.circular(AppRadius.md),
              border: Border.all(color: AppColors.borderSubtle),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(child: _buildMetricColumn('BALANCE', '\$${account.balance.toStringAsFixed(2)}')),
                _buildDivider(),
                Expanded(child: _buildMetricColumn('FREE', '\$${account.freeMargin.toStringAsFixed(2)}')),
                _buildDivider(),
                Expanded(child: _buildMetricColumn('MARGIN', '\$${account.margin.toStringAsFixed(2)}')),
                _buildDivider(),
                Expanded(
                  child: _buildMetricColumn(
                    'LEVEL',
                    account.marginLevel > 0 ? '${account.marginLevel.toStringAsFixed(0)}%' : '∞',
                    color: account.marginLevel > 200 ? AppColors.accentGreen : AppColors.accentOrange,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: AppSpacing.lg),

          // ── Trade Sizing Box 1: "Risk Budget" (TrendWise upper card) ─
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.bgCardLight.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(AppRadius.lg),
              border: Border.all(color: AppColors.borderSubtle),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Expanded(
                      child: Text(
                        'Per-Trade Risk Budget (1.5%)',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: 'Segoe UI',
                          fontSize: 11,
                          color: AppColors.textSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppColors.accentLime.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(AppRadius.xs),
                      ),
                      child: const Text(
                        'Strict 1.5% Rule',
                        style: TextStyle(
                          fontFamily: 'Segoe UI',
                          fontSize: 9.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.accentLime,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '\$${(account.balance * 0.015).toStringAsFixed(2)}',
                      style: AppTypography.mono(
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppColors.bgCardDark,
                        borderRadius: BorderRadius.circular(AppRadius.sm),
                        border: Border.all(color: AppColors.glassBorder),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.attach_money_rounded, size: 14, color: AppColors.accentLime),
                          Text(
                            'USD',
                            style: TextStyle(
                              fontFamily: 'Segoe UI',
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary,
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

          // ── Overlapping Center Action / Swap Pill ───────────────────
          Center(
            child: Transform.translate(
              offset: const Offset(0, 0),
              child: Container(
                margin: const EdgeInsets.symmetric(vertical: 4),
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: AppColors.bgPrimary,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.accentCyan.withValues(alpha: 0.4), width: 1.5),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.accentCyan.withValues(alpha: 0.2),
                      blurRadius: 8,
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.swap_vert_rounded,
                  size: 18,
                  color: AppColors.accentCyan,
                ),
              ),
            ),
          ),

          // ── Trade Sizing Box 2: "Target Execution Sizing" (TrendWise lower card)
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.bgCardLight.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(AppRadius.lg),
              border: Border.all(color: AppColors.borderSubtle),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Expanded(
                      child: Text(
                        'Calculated Position Size',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: 'Segoe UI',
                          fontSize: 11,
                          color: AppColors.textSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppColors.accentCyan.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(AppRadius.xs),
                      ),
                      child: const Text(
                        'Dynamic ATR',
                        style: TextStyle(
                          fontFamily: 'Segoe UI',
                          fontSize: 9.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.accentCyan,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Flexible(
                      child: Text(
                        '${account.orders.isNotEmpty ? account.orders.first.lots.toStringAsFixed(2) : "0.11"} Lots',
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.mono(
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppColors.bgCardDark,
                        borderRadius: BorderRadius.circular(AppRadius.sm),
                        border: Border.all(color: AppColors.glassBorder),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.euro_rounded, size: 14, color: AppColors.accentBlue),
                          const SizedBox(width: 4),
                          Text(
                            account.symbol,
                            style: const TextStyle(
                              fontFamily: 'Segoe UI',
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary,
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

          const SizedBox(height: AppSpacing.xl),

          // ── Prominent Electric Lime CTA Button (TrendWise "Swap Now") ──
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton(
              onPressed: () {
                if (isRunning) {
                  provider.stopBridge();
                } else {
                  provider.startBridge();
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: isRunning ? AppColors.accentOrange : AppColors.accentLime,
                foregroundColor: AppColors.bgPrimary,
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.lg),
                ),
                elevation: isRunning ? 0 : 8,
                shadowColor: AppColors.accentLime.withValues(alpha: 0.4),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    isRunning ? Icons.pause_circle_filled_rounded : Icons.play_arrow_rounded,
                    color: AppColors.bgPrimary,
                    size: 22,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    isRunning ? 'PAUSE BRIDGE EXECUTION' : 'Start Live Trading',
                    style: const TextStyle(
                      fontFamily: 'Segoe UI',
                      fontSize: 13.5,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0.6,
                      color: AppColors.bgPrimary,
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: AppSpacing.sm),

          // ── Emergency Kill-Switch Button ────────────────────────────
          SizedBox(
            width: double.infinity,
            height: 38,
            child: OutlinedButton(
              onPressed: () => provider.toggleEmergencyHalt(),
              style: OutlinedButton.styleFrom(
                foregroundColor: isHalted ? AppColors.accentGreen : AppColors.accentRed,
                side: BorderSide(
                  color: isHalted
                      ? AppColors.accentGreen.withValues(alpha: 0.6)
                      : AppColors.accentRed.withValues(alpha: 0.6),
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.md),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    isHalted ? Icons.lock_open_rounded : Icons.shield_rounded,
                    size: 15,
                  ),
                  const SizedBox(width: AppSpacing.xs),
                  Text(
                    isHalted ? 'RESUME FROM EMERGENCY HALT' : 'Emergency Kill-Switch',
                    style: const TextStyle(
                      fontFamily: 'Segoe UI',
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetricColumn(String label, String value, {Color? color}) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            overflow: TextOverflow.ellipsis,
            maxLines: 1,
            style: const TextStyle(
              fontFamily: 'Segoe UI',
              fontSize: 9,
              fontWeight: FontWeight.w700,
              color: AppColors.textMuted,
              letterSpacing: 0.6,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            overflow: TextOverflow.ellipsis,
            maxLines: 1,
            style: AppTypography.mono(
              fontSize: 11.5,
              fontWeight: FontWeight.w700,
              color: color ?? AppColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDivider() {
    return Container(
      width: 1,
      height: 24,
      color: AppColors.borderSubtle,
    );
  }
}
