import 'dart:async';
import 'package:flutter/material.dart';
import '../models/trade_model.dart';
import '../services/api_service.dart';

class TradingProvider extends ChangeNotifier {
  final ApiService api;

  BridgeState _bridgeState = BridgeState();
  AccountSummary _account = AccountSummary();
  List<TradeRecord> _trades = [];
  List<CandleData> _candles = [];
  Map<String, dynamic> _stats = {};
  Map<String, String> _settings = {};

  String _activePair = 'USDCADm';
  String _activeTimeframe = '5m';
  String _chartMode = 'Candles';
  int _selectedTabIndex = 0;
  bool _isLoading = false;
  final List<String> _activityLogs = [];
  StreamSubscription? _eventSub;
  Timer? _poller;

  TradingProvider({required this.api}) {
    init();
  }

  // ── Getters ──────────────────────────────────────────────────────────
  BridgeState get bridgeState => _bridgeState;
  AccountSummary get account => _account;
  List<TradeRecord> get trades => _trades;
  List<CandleData> get candles => _candles;
  Map<String, dynamic> get stats => _stats;
  Map<String, String> get settings => _settings;
  String get activePair => _activePair;
  String get activeTimeframe => _activeTimeframe;
  String get chartMode => _chartMode;
  int get selectedTabIndex => _selectedTabIndex;
  bool get isLoading => _isLoading;
  bool get isConnected => api.isConnected || _bridgeState.isRunning;
  List<String> get activityLogs => List.unmodifiable(_activityLogs);

  void selectTab(int index) {
    _selectedTabIndex = index;
    notifyListeners();
  }

  // ── Initialization ───────────────────────────────────────────────────

  void init() {
    api.onConnectionChange = (_) {
      notifyListeners();
    };

    api.connectWebSocket();

    _eventSub = api.eventStream.listen((event) {
      _handleWsEvent(event);
    });

    refreshAll();

    // 2-second background poll to ensure real-time precision with MT4
    _poller = Timer.periodic(const Duration(seconds: 2), (_) {
      _pollUpdates();
    });
  }

  void _handleWsEvent(Map<String, dynamic> event) {
    final type = event['event'] as String?;
    final data = event['data'] as Map<String, dynamic>? ?? {};

    switch (type) {
      case 'status':
        _bridgeState = BridgeState.fromJson(data);
        notifyListeners();
        break;

      case 'account_update':
        _account = AccountSummary.fromJson(data);
        refreshTrades();
        break;

      case 'order_update':
        final symbol = data['symbol'] ?? '';
        final dir = data['direction'] ?? '';
        final status = data['status'] ?? '';
        final lots = data['lots'] ?? '';
        _logActivity('Order $dir $lots $symbol: $status');
        refreshTrades();
        refreshAccount();
        break;

      case 'risk_rejection':
        final msg = data['message'] ?? 'Risk guardrail rejection';
        _logActivity('⚠️ Guardrail: $msg');
        notifyListeners();
        break;

      case 'watchdog_alert':
        final state = data['state'] ?? '';
        final msg = data['message'] ?? '';
        _logActivity('Watchdog [$state]: $msg');
        notifyListeners();
        break;

      case 'bridge_started':
        _bridgeState = _bridgeState.copyWith(
          isRunning: true,
          symbol: data['symbol'] ?? _activePair,
          timeframe: data['timeframe'] ?? 'M5',
        );
        _logActivity('Bridge Started for ${_bridgeState.symbol} ${_bridgeState.timeframe}');
        notifyListeners();
        refreshStatus();
        break;

      case 'bridge_stopped':
        _bridgeState = _bridgeState.copyWith(isRunning: false);
        _logActivity('Bridge Stopped');
        notifyListeners();
        refreshStatus();
        break;

      case 'system_notice':
        final msg = data['message'] ?? '';
        if (msg.toString().isNotEmpty) {
          _logActivity('ℹ️ $msg');
          notifyListeners();
        }
        break;

      case 'emergency_halt':
        final active = data['active'] == true;
        _logActivity(active ? '🛑 EMERGENCY HALT ACTIVATED' : 'Emergency Halt Cleared');
        refreshStatus();
        break;
    }
  }

  void _logActivity(String message) {
    final timeStr = DateTime.now().toIso8601String().substring(11, 19);
    _activityLogs.insert(0, '[$timeStr] $message');
    if (_activityLogs.length > 50) {
      _activityLogs.removeLast();
    }
    notifyListeners();
  }

  Future<void> _pollUpdates() async {
    final status = await api.getStatus();
    _bridgeState = status;

    final acc = await api.getAccount(symbol: _activePair);
    _account = acc;

    final updatedTrades = await api.getTrades();
    if (updatedTrades.isNotEmpty) {
      _trades = updatedTrades;
    } else if (_account.orders.isNotEmpty) {
      _trades = _account.orders;
    }

    final newCandles = await api.getCandles(symbol: _activePair, timeframe: _activeTimeframe);
    if (newCandles.isNotEmpty) {
      _candles = newCandles;
    }
    notifyListeners();
  }

  Future<void> refreshAll() async {
    _isLoading = true;
    notifyListeners();

    try {
      final futures = await Future.wait([
        api.getStatus(),
        api.getAccount(symbol: _activePair),
        api.getTrades(),
        api.getCandles(symbol: _activePair, timeframe: _activeTimeframe),
        api.getStats(),
        api.getSettings(),
      ]);

      _bridgeState = futures[0] as BridgeState;
      _account = futures[1] as AccountSummary;
      final fetchedTrades = futures[2] as List<TradeRecord>;
      _trades = fetchedTrades.isNotEmpty ? fetchedTrades : _account.orders;
      _candles = futures[3] as List<CandleData>;
      _stats = futures[4] as Map<String, dynamic>;
      _settings = futures[5] as Map<String, String>;
    } catch (e) {
      debugPrint('refreshAll failed: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> refreshTrades() async {
    final fetchedTrades = await api.getTrades();
    _trades = fetchedTrades.isNotEmpty ? fetchedTrades : _account.orders;
    _stats = await api.getStats();
    notifyListeners();
  }

  Future<void> refreshAccount() async {
    _account = await api.getAccount(symbol: _activePair);
    notifyListeners();
  }

  Future<void> refreshStatus() async {
    _bridgeState = await api.getStatus();
    notifyListeners();
  }

  // ── Actions ──────────────────────────────────────────────────────────

  Future<bool> startBridge() async {
    _logActivity('Checking MetaTrader 4 & Starting Live Bridge...');
    _bridgeState = _bridgeState.copyWith(
      isRunning: true,
      symbol: _activePair,
      mt4ProcessRunning: true,
      mt4Connected: true,
    );
    notifyListeners();

    final ok = await api.startBridge();
    if (ok) {
      _logActivity('Live Trading Bridge Active (MetaTrader 4 connected)');
      await refreshStatus();
      Future.delayed(const Duration(milliseconds: 1500), refreshStatus);
      Future.delayed(const Duration(milliseconds: 2500), refreshAccount);
    } else {
      _bridgeState = _bridgeState.copyWith(isRunning: false);
      _logActivity('Failed to start bridge. Verify terminal connection.');
      notifyListeners();
      await refreshStatus();
    }
    return ok;
  }

  Future<bool> launchMt4() async {
    _logActivity('Launching MetaTrader 4 terminal...');
    final ok = await api.launchMt4();
    if (ok) {
      _logActivity('MetaTrader 4 process active.');
      refreshStatus();
    }
    return ok;
  }

  Future<bool> stopBridge() async {
    _logActivity('Sending Stop Bridge command...');
    _bridgeState = _bridgeState.copyWith(isRunning: false);
    notifyListeners();

    final ok = await api.stopBridge();
    if (ok) {
      _logActivity('Bridge Stopped');
      await refreshStatus();
    } else {
      _logActivity('Failed to stop bridge.');
      await refreshStatus();
    }
    return ok;
  }

  Future<bool> toggleEmergencyHalt() async {
    if (_bridgeState.emergencyHalt) {
      _logActivity('Resuming from Emergency Halt...');
      _bridgeState = _bridgeState.copyWith(emergencyHalt: false);
      notifyListeners();
      final ok = await api.resumeBridge();
      await refreshStatus();
      return ok;
    } else {
      _logActivity('Activating Emergency Halt...');
      _bridgeState = _bridgeState.copyWith(emergencyHalt: true);
      notifyListeners();
      final ok = await api.emergencyHalt();
      await refreshStatus();
      return ok;
    }
  }

  Future<bool> updateSettings(Map<String, String> newSettings) async {
    final ok = await api.saveSettings(newSettings);
    if (ok) {
      _settings.addAll(newSettings);
      _logActivity('Settings saved to .env');
      notifyListeners();
    }
    return ok;
  }

  Future<Map<String, dynamic>> detectMt4() async {
    return await api.detectMt4();
  }

  Future<Map<String, dynamic>> connectAccount({
    required String accountNumber,
    required String password,
    required String server,
    String? terminalPath,
    bool autoStartBridge = true,
  }) async {
    _isLoading = true;
    _logActivity('Connecting MT4 account #$accountNumber ($server)...');
    notifyListeners();

    final result = await api.connectAccount(
      accountNumber: accountNumber,
      password: password,
      server: server,
      terminalPath: terminalPath,
      autoStartBridge: autoStartBridge,
    );

    _isLoading = false;
    if (result['status'] == 'connected') {
      _logActivity('MetaTrader 4 connected: Account #$accountNumber ($server)');
      await refreshAccount();
      await refreshStatus();
    } else {
      _logActivity('MT4 connection error: ${result['message'] ?? 'Failed'}');
      notifyListeners();
    }
    return result;
  }

  Future<void> selectPair(String pair) async {
    const normalized = 'USDCADm';
    if (_activePair != normalized) {
      _activePair = normalized;
      _candles = [];
      notifyListeners();
      await _pollUpdates();
    }
  }

  void selectTimeframe(String tf) {
    _activeTimeframe = tf;
    notifyListeners();
    _pollUpdates();
  }

  void selectChartMode(String mode) {
    _chartMode = mode;
    notifyListeners();
  }

  @override
  void dispose() {
    _eventSub?.cancel();
    _poller?.cancel();
    api.dispose();
    super.dispose();
  }
}
