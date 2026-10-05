import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import 'tactile_wrapper.dart';

class HeaderNav extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onTabSelected;
  final VoidCallback onOpenSettings;

  const HeaderNav({
    super.key,
    required this.selectedIndex,
    required this.onTabSelected,
    required this.onOpenSettings,
  });

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final bridge = provider.bridgeState;
    final account = provider.account;

    final tabs = [
      {'icon': Icons.dashboard_rounded, 'label': 'Overview'},
      {'icon': Icons.trending_up_rounded, 'label': 'Positions'},
      {'icon': Icons.show_chart_rounded, 'label': 'Live Chart'},
      {'icon': Icons.analytics_outlined, 'label': 'Analytics'},
      {'icon': Icons.history_rounded, 'label': 'History'},
    ];

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.bgPrimary.withValues(alpha: 0.8),
        border: const Border(bottom: BorderSide(color: AppColors.borderSubtle)),
      ),
      child: Row(
        children: [
          // ── Brand Logo ───────────────────────────────────────────────
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AppColors.accentLime,
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.accentLime.withValues(alpha: 0.35),
                      blurRadius: 14,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Icon(Icons.bolt_rounded, color: AppColors.bgPrimary, size: 24),
              ),
              const SizedBox(width: AppSpacing.md),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  RichText(
                    text: const TextSpan(
                      children: [
                        TextSpan(
                          text: 'AK',
                          style: TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            color: AppColors.textPrimary,
                            letterSpacing: -0.5,
                          ),
                        ),
                        TextSpan(
                          text: 'Forex',
                          style: TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 18,
                            fontWeight: FontWeight.w400,
                            color: AppColors.accentLime,
                            letterSpacing: -0.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Text(
                    'QUANT TRADING DESK',
                    style: TextStyle(
                      fontFamily: 'Segoe UI',
                      fontSize: 8.5,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textMuted,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
            ],
          ),

          const SizedBox(width: AppSpacing.xl),

          // ── Center Navigation Pills ──────────────────────────────────
          Expanded(
            child: Center(
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Container(
                  padding: const EdgeInsets.all(AppSpacing.xs),
                  decoration: BoxDecoration(
                    color: AppColors.bgCardDark.withValues(alpha: 0.8),
                    borderRadius: BorderRadius.circular(AppRadius.xxl),
                    border: Border.all(color: AppColors.borderSubtle),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: List.generate(tabs.length, (idx) {
                      final isSelected = selectedIndex == idx;
                      final item = tabs[idx];

                      return TactileWrapper(
                        onTap: () => onTabSelected(idx),
                        pressScale: 0.96,
                        hoverScale: 1.02,
                        child: AnimatedContainer(
                          duration: AppMotion.fast,
                          curve: AppMotion.easeOut,
                          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
                          decoration: BoxDecoration(
                            color: isSelected ? AppColors.bgCardLight : Colors.transparent,
                            borderRadius: BorderRadius.circular(AppRadius.xl),
                            border: isSelected ? Border.all(color: AppColors.glassBorder) : null,
                            boxShadow: isSelected
                                ? [
                                    BoxShadow(
                                      color: Colors.black.withValues(alpha: 0.25),
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
                                item['icon'] as IconData,
                                size: 16,
                                color: isSelected ? AppColors.accentLime : AppColors.textSecondary,
                              ),
                              const SizedBox(width: AppSpacing.sm),
                              Text(
                                item['label'] as String,
                                style: TextStyle(
                                  fontFamily: 'Segoe UI',
                                  fontSize: 12.5,
                                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                                  color: isSelected ? AppColors.textPrimary : AppColors.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    }),
                  ),
                ),
              ),
            ),
          ),

          const SizedBox(width: AppSpacing.lg),

          // ── Right Status & Controls ──────────────────────────────────
          Row(
            children: [
              // MT4 Account Tag
              Container(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.bgCardDark,
                  borderRadius: BorderRadius.circular(AppRadius.lg),
                  border: Border.all(color: AppColors.glassBorder),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        color: AppColors.accentGreen,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${account.company} #${account.accountNumber}',
                          style: const TextStyle(
                            fontFamily: 'Segoe UI',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        Text(
                          '\$${account.balance.toStringAsFixed(2)} ${account.currency}',
                          style: AppTypography.mono(
                            fontSize: 10,
                            color: AppColors.accentLime,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),

              const SizedBox(width: AppSpacing.md),

              // Pair + Spread Tag
              Container(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.accentBlue.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppRadius.lg),
                  border: Border.all(color: AppColors.accentBlue.withValues(alpha: 0.3)),
                ),
                child: Row(
                  children: [
                    Text(
                      provider.activePair,
                      style: const TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '${account.spreadPips.toStringAsFixed(1)} pips',
                      style: AppTypography.mono(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: AppColors.accentCyan,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(width: AppSpacing.md),

              // Bridge Status Chip
              Container(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 8),
                decoration: BoxDecoration(
                  color: bridge.emergencyHalt
                      ? AppColors.accentRed.withValues(alpha: 0.15)
                      : bridge.isRunning
                          ? AppColors.accentGreen.withValues(alpha: 0.15)
                          : AppColors.textMuted.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppRadius.lg),
                  border: Border.all(
                    color: bridge.emergencyHalt
                        ? AppColors.accentRed.withValues(alpha: 0.5)
                        : bridge.isRunning
                            ? AppColors.accentGreen.withValues(alpha: 0.5)
                            : AppColors.borderSubtle,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 7,
                      height: 7,
                      decoration: BoxDecoration(
                        color: bridge.emergencyHalt
                            ? AppColors.accentRed
                            : bridge.isRunning
                                ? AppColors.accentGreen
                                : AppColors.textMuted,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      bridge.emergencyHalt
                          ? 'HALTED'
                          : bridge.isRunning
                              ? 'LIVE'
                              : 'STANDBY',
                      style: TextStyle(
                        fontFamily: 'Segoe UI',
                        fontSize: 10.5,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.8,
                        color: bridge.emergencyHalt
                            ? AppColors.accentRed
                            : bridge.isRunning
                                ? AppColors.accentGreen
                                : AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(width: AppSpacing.sm),

              // Emergency Kill Switch
              TactileWrapper(
                onTap: () => provider.toggleEmergencyHalt(),
                pressScale: 0.90,
                hoverScale: 1.10,
                child: Tooltip(
                  message: bridge.emergencyHalt ? 'Resume Bridge' : 'Emergency Kill Switch',
                  child: Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: bridge.emergencyHalt
                          ? AppColors.accentGreen.withValues(alpha: 0.15)
                          : AppColors.accentRed.withValues(alpha: 0.15),
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: bridge.emergencyHalt
                            ? AppColors.accentGreen.withValues(alpha: 0.5)
                            : AppColors.accentRed.withValues(alpha: 0.5),
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: (bridge.emergencyHalt ? AppColors.accentGreen : AppColors.accentRed)
                              .withValues(alpha: 0.25),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Icon(
                      bridge.emergencyHalt ? Icons.play_arrow_rounded : Icons.stop_circle_outlined,
                      color: bridge.emergencyHalt ? AppColors.accentGreen : AppColors.accentRed,
                      size: 20,
                    ),
                  ),
                ),
              ),

              const SizedBox(width: AppSpacing.sm),

              // Settings Gear Button
              TactileWrapper(
                onTap: onOpenSettings,
                pressScale: 0.90,
                hoverScale: 1.10,
                child: Tooltip(
                  message: 'Trading Settings',
                  child: Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: AppColors.bgCardLight.withValues(alpha: 0.6),
                      shape: BoxShape.circle,
                      border: Border.all(color: AppColors.glassBorder),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.3),
                          blurRadius: 6,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Icon(Icons.settings_outlined, color: AppColors.textSecondary, size: 19),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
