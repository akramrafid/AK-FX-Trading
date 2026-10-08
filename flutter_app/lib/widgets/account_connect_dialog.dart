import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';
import 'tactile_button.dart';
import 'tactile_wrapper.dart';

class AccountConnectDialog extends StatefulWidget {
  const AccountConnectDialog({super.key});

  @override
  State<AccountConnectDialog> createState() => _AccountConnectDialogState();
}

class _AccountConnectDialogState extends State<AccountConnectDialog> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _accountCtrl;
  late TextEditingController _passwordCtrl;
  late TextEditingController _serverCtrl;

  bool _obscurePassword = true;
  bool _autoLaunch = true;
  bool _isConnecting = false;
  String? _statusMessage;
  bool _isSuccess = false;

  Map<String, dynamic>? _detectInfo;
  bool _isDetecting = true;

  final List<String> _popularServers = [
    'Exness-Real21',
    'Exness-Real',
    'Exness-Real2',
    'Exness-Trial',
    'Exness-Trial2',
  ];

  @override
  void initState() {
    super.initState();
    final provider = context.read<TradingProvider>();
    final account = provider.account;
    final currentAccStr = account.accountNumber > 0 ? account.accountNumber.toString() : '70702138';

    _accountCtrl = TextEditingController(text: currentAccStr);
    _passwordCtrl = TextEditingController();
    _serverCtrl = TextEditingController(text: account.company.isNotEmpty ? account.company : 'Exness-Real21');

    _runDetection();
  }

  Future<void> _runDetection() async {
    setState(() => _isDetecting = true);
    final provider = context.read<TradingProvider>();
    final info = await provider.detectMt4();
    if (mounted) {
      setState(() {
        _detectInfo = info;
        _isDetecting = false;
        if (info['current_server'] != null && (info['current_server'] as String).isNotEmpty) {
          _serverCtrl.text = info['current_server'] as String;
        }
      });
    }
  }

  @override
  void dispose() {
    _accountCtrl.dispose();
    _passwordCtrl.dispose();
    _serverCtrl.dispose();
    super.dispose();
  }

  Future<void> _submitConnect() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isConnecting = true;
      _statusMessage = null;
      _isSuccess = false;
    });

    final provider = context.read<TradingProvider>();
    final result = await provider.connectAccount(
      accountNumber: _accountCtrl.text.trim(),
      password: _passwordCtrl.text.trim(),
      server: _serverCtrl.text.trim(),
      autoStartBridge: _autoLaunch,
    );

    if (!mounted) return;

    if (result['status'] == 'connected') {
      setState(() {
        _isConnecting = false;
        _isSuccess = true;
        _statusMessage = 'MT4 Account #${_accountCtrl.text.trim()} connected successfully!';
      });

      Future.delayed(const Duration(milliseconds: 1400), () {
        if (mounted) Navigator.of(context).pop(true);
      });
    } else {
      setState(() {
        _isConnecting = false;
        _isSuccess = false;
        _statusMessage = result['message']?.toString() ?? 'Failed to connect MT4. Check credentials.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final terminalDetected = _detectInfo != null && (_detectInfo!['detected_files_dir'] as String? ?? '').isNotEmpty;
    final mt4Running = _detectInfo?['mt4_process_running'] == true;

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.xxl),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: GlassCard(
          backgroundColor: AppColors.bgCardDark.withValues(alpha: 0.95),
          borderColor: AppColors.glassBorder,
          padding: const EdgeInsets.all(AppSpacing.xxl),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // ── Title Bar ─────────────────────────────────────────
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: AppColors.accentLime.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(AppRadius.md),
                          border: Border.all(color: AppColors.accentLime.withValues(alpha: 0.3)),
                        ),
                        child: const Icon(Icons.link_rounded, color: AppColors.accentLime, size: 22),
                      ),
                      const SizedBox(width: AppSpacing.md),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Connect MT4 Account',
                              style: TextStyle(
                                fontFamily: 'Segoe UI',
                                fontSize: 18,
                                fontWeight: FontWeight.w700,
                                color: AppColors.textPrimary,
                              ),
                            ),
                            SizedBox(height: 2),
                            Text(
                              'Auto-links MetaTrader 4 and AK Quant Desk',
                              style: TextStyle(
                                fontFamily: 'Segoe UI',
                                fontSize: 12,
                                color: AppColors.textMuted,
                              ),
                            ),
                          ],
                        ),
                      ),
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
                  const Divider(color: AppColors.borderSubtle, height: 1),
                  const SizedBox(height: AppSpacing.lg),

                  // ── Auto-Detect Indicator ─────────────────────────────
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.bgCardLight.withValues(alpha: 0.6),
                      borderRadius: BorderRadius.circular(AppRadius.md),
                      border: Border.all(
                        color: terminalDetected ? AppColors.accentGreen.withValues(alpha: 0.35) : AppColors.borderSubtle,
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: terminalDetected ? AppColors.accentGreen : AppColors.accentOrange,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _isDetecting
                                    ? 'Scanning MetaTrader 4 directory...'
                                    : terminalDetected
                                        ? 'MT4 Terminal Auto-Detected & Ready'
                                        : 'Manual Directory Mode',
                                style: const TextStyle(
                                  fontFamily: 'Segoe UI',
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                              if (terminalDetected && _detectInfo != null)
                                Text(
                                  mt4Running ? 'Process: terminal.exe running' : 'Process: will auto-launch on connect',
                                  style: AppTypography.mono(
                                    fontSize: 10,
                                    color: AppColors.textMuted,
                                  ),
                                ),
                            ],
                          ),
                        ),
                        if (terminalDetected)
                          const Icon(Icons.check_circle_rounded, color: AppColors.accentGreen, size: 16),
                      ],
                    ),
                  ),

                  const SizedBox(height: AppSpacing.lg),

                  // ── Account Number Field ──────────────────────────────
                  _buildFieldLabel('ACCOUNT LOGIN / NUMBER'),
                  TextFormField(
                    controller: _accountCtrl,
                    keyboardType: TextInputType.number,
                    style: AppTypography.mono(fontSize: 14, color: AppColors.textPrimary),
                    decoration: _inputDecoration(
                      hint: 'e.g. 70702138',
                      icon: Icons.tag_rounded,
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Account number is required';
                      return null;
                    },
                  ),

                  const SizedBox(height: AppSpacing.md),

                  // ── Password Field ────────────────────────────────────
                  _buildFieldLabel('TRADER PASSWORD'),
                  TextFormField(
                    controller: _passwordCtrl,
                    obscureText: _obscurePassword,
                    style: AppTypography.mono(fontSize: 14, color: AppColors.textPrimary),
                    decoration: _inputDecoration(
                      hint: 'Enter MT4 trader password',
                      icon: Icons.lock_outline_rounded,
                      suffix: IconButton(
                        icon: Icon(
                          _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                          color: AppColors.textMuted,
                          size: 18,
                        ),
                        onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                      ),
                    ),
                  ),

                  const SizedBox(height: AppSpacing.md),

                  // ── Server Field ──────────────────────────────────────
                  _buildFieldLabel('BROKER SERVER'),
                  TextFormField(
                    controller: _serverCtrl,
                    style: const TextStyle(fontFamily: 'Segoe UI', fontSize: 13, color: AppColors.textPrimary),
                    decoration: _inputDecoration(
                      hint: 'e.g. Exness-Real21',
                      icon: Icons.dns_outlined,
                    ),
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Broker server is required';
                      return null;
                    },
                  ),

                  const SizedBox(height: AppSpacing.xs),

                  // Quick Server Select Chips
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: _popularServers.map((srv) {
                      final isSelected = _serverCtrl.text == srv;
                      return TactileWrapper(
                        onTap: () => setState(() => _serverCtrl.text = srv),
                        pressScale: 0.95,
                        hoverScale: 1.05,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: isSelected ? AppColors.accentLime.withValues(alpha: 0.2) : AppColors.bgSurface,
                            borderRadius: BorderRadius.circular(AppRadius.sm),
                            border: Border.all(
                              color: isSelected ? AppColors.accentLime : AppColors.glassBorder,
                            ),
                          ),
                          child: Text(
                            srv,
                            style: TextStyle(
                              fontFamily: 'Segoe UI',
                              fontSize: 11,
                              fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                              color: isSelected ? AppColors.accentLime : AppColors.textMuted,
                            ),
                          ),
                        ),
                      );
                    }).toList(),
                  ),

                  const SizedBox(height: AppSpacing.lg),

                  // ── Auto-Launch Switch ────────────────────────────────
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppColors.bgCardLight.withValues(alpha: 0.4),
                      borderRadius: BorderRadius.circular(AppRadius.md),
                      border: Border.all(color: AppColors.glassBorder),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.flash_on_rounded, color: AppColors.accentLime, size: 18),
                        const SizedBox(width: AppSpacing.sm),
                        const Expanded(
                          child: Text(
                            'Launch MT4 & Auto-Sync Bridge',
                            style: TextStyle(
                              fontFamily: 'Segoe UI',
                              fontSize: 12.5,
                              fontWeight: FontWeight.w600,
                              color: AppColors.textPrimary,
                            ),
                          ),
                        ),
                        Switch(
                          value: _autoLaunch,
                          activeColor: AppColors.accentLime,
                          activeTrackColor: AppColors.accentLime.withValues(alpha: 0.3),
                          onChanged: (val) => setState(() => _autoLaunch = val),
                        ),
                      ],
                    ),
                  ),

                  // ── Feedback Banner ───────────────────────────────────
                  if (_statusMessage != null) ...[
                    const SizedBox(height: AppSpacing.md),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(AppSpacing.md),
                      decoration: BoxDecoration(
                        color: _isSuccess
                            ? AppColors.accentGreen.withValues(alpha: 0.15)
                            : AppColors.accentRed.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(AppRadius.md),
                        border: Border.all(
                          color: _isSuccess ? AppColors.accentGreen : AppColors.accentRed,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _isSuccess ? Icons.check_circle_outline_rounded : Icons.error_outline_rounded,
                            color: _isSuccess ? AppColors.accentGreen : AppColors.accentRed,
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _statusMessage!,
                              style: TextStyle(
                                fontFamily: 'Segoe UI',
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: _isSuccess ? AppColors.accentGreen : AppColors.accentRed,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],

                  const SizedBox(height: AppSpacing.xl),

                  // ── CTA Connect Button ────────────────────────────────
                  TactileButton(
                    onPressed: _isConnecting ? null : _submitConnect,
                    variant: TactileButtonVariant.primary,
                    height: 48,
                    width: double.infinity,
                    borderRadius: AppRadius.lg,
                    child: _isConnecting
                        ? const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2.2,
                                  color: AppColors.bgPrimary,
                                ),
                              ),
                              SizedBox(width: 10),
                              Text(
                                'Connecting to MT4...',
                                style: TextStyle(
                                  fontFamily: 'Segoe UI',
                                  fontSize: 14,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.bgPrimary,
                                ),
                              ),
                            ],
                          )
                        : const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.bolt_rounded, size: 20, color: AppColors.bgPrimary),
                              SizedBox(width: 8),
                              Text(
                                'Connect & Sync MT4',
                                style: TextStyle(
                                  fontFamily: 'Segoe UI',
                                  fontSize: 14,
                                  fontWeight: FontWeight.w800,
                                  color: AppColors.bgPrimary,
                                  letterSpacing: 0.3,
                                ),
                              ),
                            ],
                          ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFieldLabel(String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(
        label,
        style: const TextStyle(
          fontFamily: 'Segoe UI',
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: AppColors.textMuted,
          letterSpacing: 1.2,
        ),
      ),
    );
  }

  InputDecoration _inputDecoration({
    required String hint,
    required IconData icon,
    Widget? suffix,
  }) {
    return InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(fontFamily: 'Segoe UI', fontSize: 12.5, color: AppColors.textMuted),
      prefixIcon: Icon(icon, color: AppColors.textSecondary, size: 18),
      suffixIcon: suffix,
      filled: true,
      fillColor: AppColors.bgSurface.withValues(alpha: 0.6),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.md),
        borderSide: const BorderSide(color: AppColors.borderSubtle),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.md),
        borderSide: const BorderSide(color: AppColors.borderSubtle),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.md),
        borderSide: const BorderSide(color: AppColors.accentLime, width: 1.5),
      ),
    );
  }
}
