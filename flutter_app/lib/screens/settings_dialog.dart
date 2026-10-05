import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/glass_card.dart';
import '../widgets/tactile_button.dart';
import '../widgets/tactile_wrapper.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key});

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late TextEditingController _symbolCtrl;
  late TextEditingController _timeframeCtrl;
  late TextEditingController _riskPctCtrl;
  late TextEditingController _maxDailyLossCtrl;
  late TextEditingController _maxDailyTradesCtrl;
  late TextEditingController _maxSpreadCtrl;
  late TextEditingController _mt4PathCtrl;
  late TextEditingController _telegramTokenCtrl;
  late TextEditingController _telegramChatIdCtrl;

  String _strategyMode = 'c1_wickswap';
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    final settings = context.read<TradingProvider>().settings;

    _strategyMode = settings['STRATEGY_MODE'] ?? 'c1_wickswap';
    _symbolCtrl = TextEditingController(text: settings['TRADING_SYMBOL'] ?? 'EURUSDm');
    _timeframeCtrl = TextEditingController(text: settings['TRADING_TIMEFRAME'] ?? 'M5');
    _riskPctCtrl = TextEditingController(text: settings['RISK_PER_TRADE_PCT'] ?? '0.015');
    _maxDailyLossCtrl = TextEditingController(text: settings['MAX_DAILY_LOSS_PCT'] ?? '0.03');
    _maxDailyTradesCtrl = TextEditingController(text: settings['MAX_DAILY_TRADES'] ?? '3');
    _maxSpreadCtrl = TextEditingController(text: settings['MAX_SPREAD_PIPS'] ?? '2.5');
    _mt4PathCtrl = TextEditingController(
      text: settings['MT4_FILES_DIR'] ?? r'C:\Users\MSI\AppData\Roaming\MetaQuotes\Terminal\50CA3DFB510CC5A8F28B48D1BF2A5702\MQL4\Files',
    );
    _telegramTokenCtrl = TextEditingController(text: settings['TELEGRAM_BOT_TOKEN'] ?? '');
    _telegramChatIdCtrl = TextEditingController(text: settings['TELEGRAM_CHAT_ID'] ?? '');
  }

  @override
  void dispose() {
    _symbolCtrl.dispose();
    _timeframeCtrl.dispose();
    _riskPctCtrl.dispose();
    _maxDailyLossCtrl.dispose();
    _maxDailyTradesCtrl.dispose();
    _maxSpreadCtrl.dispose();
    _mt4PathCtrl.dispose();
    _telegramTokenCtrl.dispose();
    _telegramChatIdCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _isSaving = true);
    final provider = context.read<TradingProvider>();

    final Map<String, String> newSettings = {
      'STRATEGY_MODE': _strategyMode,
      'TRADING_SYMBOL': _symbolCtrl.text.trim(),
      'TRADING_TIMEFRAME': _timeframeCtrl.text.trim(),
      'RISK_PER_TRADE_PCT': _riskPctCtrl.text.trim(),
      'MAX_DAILY_LOSS_PCT': _maxDailyLossCtrl.text.trim(),
      'MAX_DAILY_TRADES': _maxDailyTradesCtrl.text.trim(),
      'MAX_SPREAD_PIPS': _maxSpreadCtrl.text.trim(),
      'MT4_FILES_DIR': _mt4PathCtrl.text.trim(),
      'TELEGRAM_BOT_TOKEN': _telegramTokenCtrl.text.trim(),
      'TELEGRAM_CHAT_ID': _telegramChatIdCtrl.text.trim(),
    };

    final ok = await provider.updateSettings(newSettings);
    setState(() => _isSaving = false);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok ? 'Settings saved to .env successfully' : 'Failed to save settings'),
          backgroundColor: ok ? AppColors.accentGreen : AppColors.accentRed,
        ),
      );
      if (ok) Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.all(AppSpacing.xxl),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 680, maxHeight: 720),
        child: GlassCard(
          backgroundColor: AppColors.bgCardDark.withValues(alpha: 0.95),
          borderColor: AppColors.glassBorder,
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Title Bar
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: AppColors.accentLime.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(AppRadius.md),
                    ),
                    child: const Icon(Icons.settings_outlined, color: AppColors.accentLime, size: 20),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  const Text(
                    'Trading Desk Configuration',
                    style: TextStyle(
                      fontFamily: 'Segoe UI',
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const Spacer(),
                  TactileWrapper(
                    onTap: () => Navigator.of(context).pop(),
                    pressScale: 0.90,
                    hoverScale: 1.10,
                    child: Container(
                      width: 32,
                      height: 32,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: AppColors.bgCardLight.withValues(alpha: 0.5),
                        shape: BoxShape.circle,
                        border: Border.all(color: AppColors.glassBorder),
                      ),
                      child: const Icon(Icons.close_rounded, color: AppColors.textMuted, size: 18),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: AppSpacing.lg),
              const Divider(color: AppColors.borderSubtle),
              const SizedBox(height: AppSpacing.md),

              // Form Scrollable
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _sectionTitle('STRATEGY PRESET & EXECUTION MODEL'),
                      Padding(
                        padding: const EdgeInsets.only(bottom: AppSpacing.md),
                        child: Container(
                          padding: const EdgeInsets.all(4),
                          decoration: BoxDecoration(
                            color: AppColors.bgCardLight.withValues(alpha: 0.4),
                            borderRadius: BorderRadius.circular(AppRadius.md),
                            border: Border.all(color: AppColors.borderSubtle),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: InkWell(
                                  onTap: () => setState(() => _strategyMode = 'c1_wickswap'),
                                  borderRadius: BorderRadius.circular(AppRadius.sm),
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
                                    decoration: BoxDecoration(
                                      color: _strategyMode == 'c1_wickswap'
                                          ? AppColors.accentLime.withValues(alpha: 0.2)
                                          : Colors.transparent,
                                      borderRadius: BorderRadius.circular(AppRadius.sm),
                                      border: _strategyMode == 'c1_wickswap'
                                          ? Border.all(color: AppColors.accentLime)
                                          : null,
                                    ),
                                    child: Column(
                                      children: [
                                        Text(
                                          'C1 Wick-Swap (Active Test)',
                                          style: TextStyle(
                                            fontFamily: 'Segoe UI',
                                            fontSize: 12,
                                            fontWeight: FontWeight.w700,
                                            color: _strategyMode == 'c1_wickswap'
                                                ? AppColors.accentLime
                                                : AppColors.textSecondary,
                                          ),
                                        ),
                                        const SizedBox(height: 2),
                                        const Text(
                                          '1:5 R:R • BE @ 2.0R • C1 Stop',
                                          style: TextStyle(fontSize: 10, color: AppColors.textMuted),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 4),
                              Expanded(
                                child: InkWell(
                                  onTap: () => setState(() => _strategyMode = 'institutional'),
                                  borderRadius: BorderRadius.circular(AppRadius.sm),
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
                                    decoration: BoxDecoration(
                                      color: _strategyMode == 'institutional'
                                          ? AppColors.accentBlue.withValues(alpha: 0.2)
                                          : Colors.transparent,
                                      borderRadius: BorderRadius.circular(AppRadius.sm),
                                      border: _strategyMode == 'institutional'
                                          ? Border.all(color: AppColors.accentBlue)
                                          : null,
                                    ),
                                    child: Column(
                                      children: [
                                        Text(
                                          'Institutional Mode',
                                          style: TextStyle(
                                            fontFamily: 'Segoe UI',
                                            fontSize: 12,
                                            fontWeight: FontWeight.w700,
                                            color: _strategyMode == 'institutional'
                                                ? AppColors.accentBlue
                                                : AppColors.textSecondary,
                                          ),
                                        ),
                                        const SizedBox(height: 2),
                                        const Text(
                                          '5 Pillars • Asian Sweeps • 70% @ 2R',
                                          style: TextStyle(fontSize: 10, color: AppColors.textMuted),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.sm),
                      _sectionTitle('INSTRUMENT & SIZING'),
                      Row(
                        children: [
                          Expanded(child: _field('Broker Symbol', _symbolCtrl, 'e.g. EURUSDm (case-sensitive)')),
                          const SizedBox(width: AppSpacing.md),
                          Expanded(child: _field('Timeframe', _timeframeCtrl, 'e.g. M5')),
                        ],
                      ),
                      Row(
                        children: [
                          Expanded(child: _field('Risk Per Trade (Dec)', _riskPctCtrl, '0.015 = 1.5%')),
                          const SizedBox(width: AppSpacing.md),
                          Expanded(child: _field('Spread Limit (Pips)', _maxSpreadCtrl, 'e.g. 2.5')),
                        ],
                      ),

                      const SizedBox(height: AppSpacing.lg),
                      _sectionTitle('RISK GUARDRAILS'),
                      Row(
                        children: [
                          Expanded(child: _field('Max Daily Loss (Dec)', _maxDailyLossCtrl, '0.03 = 3.0%')),
                          const SizedBox(width: AppSpacing.md),
                          Expanded(child: _field('Max Daily Trades', _maxDailyTradesCtrl, 'e.g. 3')),
                        ],
                      ),

                      const SizedBox(height: AppSpacing.lg),
                      _sectionTitle('MT4 TERMINAL & BRIDGE PATH'),
                      _field('MQL4 Files Directory', _mt4PathCtrl, r'C:\Users\...\Terminal\<ID>\MQL4\Files'),

                      const SizedBox(height: AppSpacing.lg),
                      _sectionTitle('TELEGRAM ALERTS (OPTIONAL)'),
                      _field('Telegram Bot Token', _telegramTokenCtrl, 'Optional bot token'),
                      _field('Telegram Chat ID', _telegramChatIdCtrl, 'Optional chat ID'),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: AppSpacing.md),
              const Divider(color: AppColors.borderSubtle),
              const SizedBox(height: AppSpacing.md),

              // Action Buttons
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TactileButton(
                    onPressed: () => Navigator.of(context).pop(),
                    variant: TactileButtonVariant.ghost,
                    label: 'Cancel',
                    height: 42,
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  TactileButton(
                    onPressed: _isSaving ? null : _save,
                    variant: TactileButtonVariant.primary,
                    label: 'Save Configuration',
                    isLoading: _isSaving,
                    height: 42,
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Text(
        title,
        style: const TextStyle(
          fontFamily: 'Segoe UI',
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color: AppColors.accentLime,
          letterSpacing: 1.2,
        ),
      ),
    );
  }

  Widget _field(String label, TextEditingController ctrl, String hint) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontFamily: 'Segoe UI', fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.textSecondary)),
          const SizedBox(height: 6),
          TextField(
            controller: ctrl,
            style: const TextStyle(fontFamily: 'Segoe UI', fontSize: 13, color: AppColors.textPrimary),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(fontFamily: 'Segoe UI', fontSize: 12, color: AppColors.textMuted),
              filled: true,
              fillColor: AppColors.bgCardLight.withValues(alpha: 0.4),
              contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md), borderSide: const BorderSide(color: AppColors.borderSubtle)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md), borderSide: const BorderSide(color: AppColors.borderSubtle)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(AppRadius.md), borderSide: const BorderSide(color: AppColors.accentLime)),
            ),
          ),
        ],
      ),
    );
  }
}
