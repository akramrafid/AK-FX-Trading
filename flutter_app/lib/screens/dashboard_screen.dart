import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/header_nav.dart';
import '../widgets/market_chips.dart';
import '../widgets/trading_chart.dart';
import '../widgets/transactions_table.dart';
import '../widgets/account_card.dart';
import '../widgets/risk_meter_card.dart';
import '../widgets/glass_card.dart';
import '../widgets/tactile_wrapper.dart';
import 'settings_dialog.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  void _openSettings(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => const SettingsDialog(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TradingProvider>();
    final selectedTab = provider.selectedTabIndex;

    return Scaffold(
      backgroundColor: AppColors.bgPrimary,
      body: Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: const Alignment(0.4, -0.6),
            radius: 1.2,
            colors: [
              const Color(0xFF1E2A4A).withValues(alpha: 0.55),
              AppColors.bgPrimary,
            ],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              // Top Navigation Bar
              HeaderNav(
                selectedIndex: selectedTab,
                onTabSelected: (idx) => provider.selectTab(idx),
                onOpenSettings: () => _openSettings(context),
              ),

              const Divider(color: AppColors.borderSubtle, height: 1),
              if (!provider.isConnected)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 6, horizontal: AppSpacing.lg),
                  decoration: BoxDecoration(
                    color: AppColors.accentRed.withValues(alpha: 0.15),
                    border: const Border(bottom: BorderSide(color: AppColors.accentRed, width: 1)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.cloud_off_rounded, size: 14, color: AppColors.accentRed),
                      const SizedBox(width: 8),
                      Text(
                        'LOCAL API BRIDGE OFFLINE — Launch backend with scripts\\run_app.bat or python -m api.server',
                        style: AppTypography.mono(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: AppColors.accentRed,
                        ),
                      ),
                    ],
                  ),
                ),

              // Main Workspace Grid
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      // ── Left Main Panel (Dynamically switches based on tab) ──
                      Expanded(
                        flex: 7,
                        child: GlassCard(
                          backgroundColor: Colors.white.withValues(alpha: 0.03),
                          borderColor: Colors.white.withValues(alpha: 0.10),
                          padding: const EdgeInsets.all(AppSpacing.xl),
                          child: _buildMainContent(selectedTab),
                        ),
                      ),

                      const SizedBox(width: AppSpacing.lg),

                      // ── Right Side Control & Risk Panel ───────────────────────
                      const SizedBox(
                        width: 360,
                        child: SingleChildScrollView(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              // Account Balance, Lot Sizing & Start Bridge CTA
                              AccountCard(),
                              SizedBox(height: AppSpacing.md),

                              // Risk Meter & Watchdog Health
                              RiskMeterCard(),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMainContent(int tabIndex) {
    switch (tabIndex) {
      case 1: // Positions Tab
        return const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MarketChips(),
            SizedBox(height: AppSpacing.lg),
            Divider(color: AppColors.borderSubtle, height: 1),
            SizedBox(height: AppSpacing.md),
            Expanded(child: TransactionsTable()),
          ],
        );

      case 2: // Live Chart Tab
        return const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MarketChips(),
            SizedBox(height: AppSpacing.lg),
            Expanded(child: TradingChart()),
          ],
        );

      case 3: // Analytics Tab
        return _buildAnalyticsView();

      case 4: // History Tab
        return const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Historical Trade Ledger',
              style: TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.md),
            Expanded(child: TransactionsTable(initialSubTab: 1)),
          ],
        );

      case 0: // Overview Default
      default:
        return const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MarketChips(),
            SizedBox(height: AppSpacing.lg),
            Expanded(flex: 5, child: TradingChart()),
            SizedBox(height: AppSpacing.lg),
            Divider(color: AppColors.borderSubtle, height: 1),
            SizedBox(height: AppSpacing.md),
            Expanded(flex: 4, child: TransactionsTable()),
          ],
        );
    }
  }

  static Widget _buildAnalyticsView() {
    return Builder(
      builder: (context) {
        final provider = context.watch<TradingProvider>();
        final account = provider.account;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.analytics_outlined, size: 20, color: AppColors.accentCyan),
                SizedBox(width: 8),
                Text(
                  'Quant Strategy Performance & Confluence Analytics',
                  style: TextStyle(
                    fontFamily: 'Segoe UI',
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
            Row(
              children: [
                _buildAnalyticsCard(
                  'TODAY PROFIT',
                  '${account.profit >= 0 ? "+" : ""}\$${account.profit.toStringAsFixed(2)}',
                  '+0.75% Return',
                  AppColors.accentGreen,
                ),
                const SizedBox(width: AppSpacing.md),
                _buildAnalyticsCard(
                  'WIN RATIO',
                  '100%',
                  '1 / 1 Executed Orders',
                  AppColors.accentLime,
                ),
                const SizedBox(width: AppSpacing.md),
                _buildAnalyticsCard(
                  'AVG RISK:REWARD',
                  '10.0 : 1',
                  'Dynamic ATR Bracket',
                  AppColors.accentPurple,
                ),
                const SizedBox(width: AppSpacing.md),
                _buildAnalyticsCard(
                  'MT4 FILE LATENCY',
                  '< 100ms',
                  'Zero Slippage',
                  AppColors.accentBlue,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xl),
            const Divider(color: AppColors.borderSubtle, height: 1),
            const SizedBox(height: AppSpacing.lg),
            const Text(
              'LIVE POSITION AUDIT',
              style: TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: AppColors.textMuted,
                letterSpacing: 1.0,
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            const Expanded(child: TransactionsTable()),
          ],
        );
      },
    );
  }

  static Widget _buildAnalyticsCard(String label, String value, String sub, Color accent) {
    return Expanded(
      child: TactileWrapper(
        onTap: () {},
        pressScale: 0.98,
        hoverScale: 1.01,
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.lg),
          decoration: BoxDecoration(
            color: AppColors.bgCardLight.withValues(alpha: 0.35),
            borderRadius: BorderRadius.circular(AppRadius.lg),
            border: Border.all(color: AppColors.borderSubtle),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.2),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: AppColors.textMuted,
                letterSpacing: 0.8,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              value,
              style: AppTypography.mono(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              sub,
              style: TextStyle(
                fontFamily: 'Segoe UI',
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: accent,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
}
