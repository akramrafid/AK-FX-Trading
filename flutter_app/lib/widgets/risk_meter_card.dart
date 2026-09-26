import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

class RiskMeterCard extends StatelessWidget {
  const RiskMeterCard({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final bridge = provider.bridgeState;
    final account = provider.account;

    final tradesToday = bridge.ordersToday > 0 ? bridge.ordersToday : (account.tradesToday > 0 ? account.tradesToday : 1);
    const maxTrades = 3;
    final tradeRatio = (tradesToday / maxTrades).clamp(0.0, 1.0);

    return GlassCard(
      backgroundColor: AppColors.bgCardDark.withValues(alpha: 0.92),
      borderColor: AppColors.glassBorder,
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header: Risk & Health Guardrails ─────────────────────
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Expanded(
                child: Row(
                  children: [
                    Icon(Icons.shield_outlined, size: 15, color: AppColors.accentCyan),
                    SizedBox(width: 7),
                    Flexible(
                      child: Text(
                        'Risk Guardrails & Health',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: 'Segoe UI',
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.bgCardLight,
                  borderRadius: BorderRadius.circular(AppRadius.xs),
                  border: Border.all(color: AppColors.borderSubtle),
                ),
                child: const Text(
                  'DAY CEILINGS',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 8.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textMuted,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSpacing.md),

          // ── Three Metric Columns ──────────────────────────────────
          Row(
            children: [
              // 1. Trades Today
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$tradesToday / $maxTrades',
                      style: AppTypography.mono(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const Text(
                      'Trades Today',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 10,
                        color: AppColors.textMuted,
                      ),
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'Max: 3 orders',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w600,
                        color: AppColors.accentLime,
                      ),
                    ),
                  ],
                ),
              ),

              // 2. Daily Loss
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '0.0%',
                      style: AppTypography.mono(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const Text(
                      'Daily Drawdown',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 10,
                        color: AppColors.textMuted,
                      ),
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'Ceiling: 3.0%',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w600,
                        color: AppColors.accentCyan,
                      ),
                    ),
                  ],
                ),
              ),

              // 3. Watchdog & Spread
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${account.spreadPips.toStringAsFixed(1)} p',
                      style: AppTypography.mono(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: account.spreadPips <= 2.5 ? AppColors.accentGreen : AppColors.accentOrange,
                      ),
                    ),
                    const Text(
                      'Live Spread',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 10,
                        color: AppColors.textMuted,
                      ),
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'Cap: 2.5 pips',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w600,
                        color: AppColors.accentPurple,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: AppSpacing.md),

          // ── Multi-segmented Progress Bar ───────────────────────────
          ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.xs),
            child: SizedBox(
              height: 6,
              child: Row(
                children: [
                  Expanded(
                    flex: (tradeRatio * 100).toInt().clamp(15, 100),
                    child: Container(color: AppColors.accentLime),
                  ),
                  const SizedBox(width: 3),
                  Expanded(
                    flex: 25,
                    child: Container(color: AppColors.accentPurple),
                  ),
                  const SizedBox(width: 3),
                  Expanded(
                    flex: 35,
                    child: Container(color: AppColors.accentCyan.withValues(alpha: 0.4)),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: AppSpacing.sm),

          // ── Watchdog Status & MQL4 File Sync ──────────────────────
          Row(
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: const BoxDecoration(
                  color: AppColors.accentGreen,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 6),
              const Expanded(
                child: Text(
                  'Watchdog: MT4 Sync < 1.0s • Session: 07:00-17:00 UTC Active',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 10.5,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textSecondary,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
