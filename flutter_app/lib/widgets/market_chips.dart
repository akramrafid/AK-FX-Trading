import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';

class MarketChips extends StatelessWidget {
  const MarketChips({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final activePair = provider.activePair;
    final account = provider.account;

    final pairsMap = account.pairs;
    final eurMap = pairsMap['EURUSDm'] is Map<String, dynamic>
        ? (pairsMap['EURUSDm'] as Map<String, dynamic>)
        : (pairsMap['EURUSD'] as Map<String, dynamic>?);
    final cadMap = pairsMap['USDCADm'] is Map<String, dynamic>
        ? (pairsMap['USDCADm'] as Map<String, dynamic>)
        : (pairsMap['USDCAD'] as Map<String, dynamic>?);

    final eurBid = (eurMap?['bid'] as num?)?.toDouble() ??
        (activePair.contains('EUR') ? account.bid : 1.13737);
    final eurSpread = (eurMap?['spread_pips'] as num?)?.toDouble() ??
        (activePair.contains('EUR') ? account.spreadPips : 0.8);

    final cadBid = (cadMap?['bid'] as num?)?.toDouble() ??
        (activePair.contains('CAD') ? account.bid : 1.41420);
    final cadSpread = (cadMap?['spread_pips'] as num?)?.toDouble() ??
        (activePair.contains('CAD') ? account.spreadPips : 1.4);

    final pairs = [
      {
        'symbol': 'EURUSDm',
        'displaySymbol': 'EUR / USD',
        'name': 'Euro / US Dollar',
        'price': eurBid.toStringAsFixed(5),
        'spread': eurSpread.toStringAsFixed(1),
        'change': '+0.42%',
        'isUp': true,
        'icon': Icons.euro_rounded,
        'color': AppColors.accentBlue,
      },
      {
        'symbol': 'USDCADm',
        'displaySymbol': 'USD / CAD',
        'name': 'US Dollar / Canadian Dollar',
        'price': cadBid.toStringAsFixed(5),
        'spread': cadSpread.toStringAsFixed(1),
        'change': '+0.15%',
        'isUp': true,
        'icon': Icons.attach_money_rounded,
        'color': AppColors.accentCyan,
      },
    ];

    return Row(
      children: pairs.map((pair) {
        final symbol = pair['symbol'] as String;
        final isSelected = activePair == symbol;
        final isUp = pair['isUp'] as bool;
        final color = pair['color'] as Color;

        return Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            child: InkWell(
              onTap: () => provider.selectPair(symbol),
              borderRadius: BorderRadius.circular(AppRadius.lg),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                padding: const EdgeInsets.all(AppSpacing.md),
                decoration: BoxDecoration(
                  color: isSelected
                      ? AppColors.bgCardLight
                      : AppColors.bgCardDark.withValues(alpha: 0.65),
                  borderRadius: BorderRadius.circular(AppRadius.lg),
                  border: Border.all(
                    color: isSelected ? AppColors.accentLime : AppColors.borderSubtle,
                    width: isSelected ? 1.5 : 1.0,
                  ),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: AppColors.accentLime.withValues(alpha: 0.12),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                        ]
                      : null,
                ),
                child: Row(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(AppRadius.md),
                      ),
                      child: Icon(pair['icon'] as IconData, size: 17, color: color),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Text(
                                (pair['displaySymbol'] ?? symbol) as String,
                                style: TextStyle(
                                  fontFamily: 'Segoe UI',
                                  fontSize: 13,
                                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                              const SizedBox(width: 6),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                                decoration: BoxDecoration(
                                  color: AppColors.bgSurface.withValues(alpha: 0.6),
                                  borderRadius: BorderRadius.circular(AppRadius.sm),
                                ),
                                child: Text(
                                  symbol,
                                  style: AppTypography.mono(
                                    fontSize: 9.5,
                                    color: AppColors.textMuted,
                                  ),
                                ),
                              ),
                              const Spacer(),
                              Text(
                                pair['change'] as String,
                                style: TextStyle(
                                  fontFamily: 'Segoe UI',
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  color: isUp ? AppColors.accentGreen : AppColors.accentRed,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 3),
                          Row(
                            children: [
                              Text(
                                pair['price'] as String,
                                style: AppTypography.mono(
                                  fontSize: 11.5,
                                  fontWeight: FontWeight.w500,
                                  color: isSelected ? AppColors.textPrimary : AppColors.textSecondary,
                                ),
                              ),
                              const Spacer(),
                              Text(
                                '${pair['spread']}p',
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
                  ],
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}
