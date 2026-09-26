import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import '../widgets/glass_card.dart';

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

  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    final settings = context.read<TradingProvider>().settings;

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
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close_rounded, color: AppColors.textMuted),
                    splashRadius: 18,
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
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel', style: TextStyle(color: AppColors.textSecondary)),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  ElevatedButton(
                    onPressed: _isSaving ? null : _save,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.accentLime,
                      foregroundColor: AppColors.bgPrimary,
                      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.md),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.md)),
                    ),
                    child: _isSaving
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Save Configuration', style: TextStyle(fontWeight: FontWeight.w700)),
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
