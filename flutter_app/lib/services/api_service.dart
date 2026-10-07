import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/trade_model.dart';

/// Communication client connecting the Flutter Desktop UI to the Python backend.
class ApiService {
  final String baseUrl;
  final String wsUrl;

  WebSocketChannel? _channel;
  StreamController<Map<String, dynamic>>? _eventStreamController;
  Timer? _reconnectTimer;
  Timer? _pingTimer;
  bool _isConnected = false;
  bool _isDisposed = false;

  void Function(bool connected)? onConnectionChange;

  ApiService({
    this.baseUrl = 'http://127.0.0.1:8642',
    this.wsUrl = 'ws://127.0.0.1:8642/ws',
  }) {
    _eventStreamController = StreamController<Map<String, dynamic>>.broadcast();
  }

  /// Automatically resolves endpoints based on runtime platform and query parameters.
  factory ApiService.createAuto() {
    String base = 'http://127.0.0.1:8642';
    if (kIsWeb) {
      final uri = Uri.base;
      if (uri.queryParameters.containsKey('api') && uri.queryParameters['api']!.isNotEmpty) {
        base = uri.queryParameters['api']!;
      } else if (uri.host == 'localhost' || uri.host == '127.0.0.1') {
        base = '${uri.scheme}://${uri.host}:${uri.port != 0 ? uri.port : 8642}';
      } else {
        base = uri.origin;
      }
    }
    while (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    String ws;
    if (base.startsWith('https://')) {
      ws = 'wss://${base.substring(8)}/ws';
    } else if (base.startsWith('http://')) {
      ws = 'ws://${base.substring(7)}/ws';
    } else {
      ws = 'ws://$base/ws';
    }
    return ApiService(baseUrl: base, wsUrl: ws);
  }

  Stream<Map<String, dynamic>> get eventStream => _eventStreamController!.stream;
  bool get isConnected => _isConnected;

  // ── WebSocket Lifecycle ──────────────────────────────────────────────

  void connectWebSocket() {
    if (_isDisposed) return;
    _disconnectWebSocket();
    try {
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));

      _channel!.stream.listen(
        (message) {
          if (!_isConnected) {
            _isConnected = true;
            onConnectionChange?.call(true);
          }
          try {
            final data = json.decode(message as String) as Map<String, dynamic>;
            _eventStreamController?.add(data);
          } catch (e) {
            debugPrint('Error parsing WS message: $e');
          }
        },
        onError: (error) {
          debugPrint('WebSocket error: $error');
          _onDisconnect();
        },
        onDone: () {
          debugPrint('WebSocket closed');
          _onDisconnect();
        },
      );

      // Keepalive ping every 10 seconds
      _pingTimer?.cancel();
      _pingTimer = Timer.periodic(const Duration(seconds: 10), (_) {
        if (_isConnected && !_isDisposed) {
          _channel?.sink.add('ping');
        }
      });
    } catch (e) {
      debugPrint('WebSocket connection failed: $e');
      _onDisconnect();
    }
  }

  void _onDisconnect() {
    final wasConnected = _isConnected;
    _isConnected = false;
    _channel = null;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    if (wasConnected) {
      onConnectionChange?.call(false);
    }
    if (_isDisposed) return;
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (!_isDisposed) {
        connectWebSocket();
      }
    });
  }

  void _disconnectWebSocket() {
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _channel = null;
    _isConnected = false;
  }

  void dispose() {
    _isDisposed = true;
    _disconnectWebSocket();
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _eventStreamController?.close();
  }

  // ── HTTP Endpoints ───────────────────────────────────────────────────

  Future<BridgeState> getStatus() async {
    try {
      final res = await http.get(Uri.parse('$baseUrl/api/status')).timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        return BridgeState.fromJson(json.decode(res.body));
      }
    } catch (e) {
      debugPrint('getStatus failed: $e');
    }
    return BridgeState();
  }

  Future<AccountSummary> getAccount({String? symbol}) async {
    try {
      final uri = symbol != null && symbol.isNotEmpty
          ? Uri.parse('$baseUrl/api/account').replace(queryParameters: {'symbol': symbol})
          : Uri.parse('$baseUrl/api/account');
      final res = await http.get(uri).timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        return AccountSummary.fromJson(json.decode(res.body));
      }
    } catch (e) {
      debugPrint('getAccount failed: $e');
    }
    return AccountSummary();
  }

  Future<List<TradeRecord>> getTrades() async {
    try {
      final res = await http.get(Uri.parse('$baseUrl/api/trades')).timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        final list = json.decode(res.body) as List;
        return list.map((item) => TradeRecord.fromJson(item)).toList();
      }
    } catch (e) {
      debugPrint('getTrades failed: $e');
    }
    return [];
  }

  Future<List<CandleData>> getCandles({String? symbol, String? timeframe}) async {
    try {
      final query = <String, String>{};
      if (symbol != null && symbol.isNotEmpty) query['symbol'] = symbol;
      if (timeframe != null && timeframe.isNotEmpty) query['timeframe'] = timeframe;
      final uri = query.isNotEmpty
          ? Uri.parse('$baseUrl/api/candles').replace(queryParameters: query)
          : Uri.parse('$baseUrl/api/candles');
      final res = await http.get(uri).timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        final list = json.decode(res.body) as List;
        return list.map((item) => CandleData.fromJson(item)).toList();
      }
    } catch (e) {
      debugPrint('getCandles failed: $e');
    }
    return [];
  }

  Future<Map<String, dynamic>> getStats() async {
    try {
      final res = await http.get(Uri.parse('$baseUrl/api/stats')).timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        return json.decode(res.body);
      }
    } catch (e) {
      debugPrint('getStats failed: $e');
    }
    return {};
  }

  Future<Map<String, String>> getSettings() async {
    try {
      final res = await http.get(Uri.parse('$baseUrl/api/settings')).timeout(const Duration(seconds: 3));
      if (res.statusCode == 200) {
        final map = json.decode(res.body) as Map<String, dynamic>;
        return map.map((key, value) => MapEntry(key, value.toString()));
      }
    } catch (e) {
      debugPrint('getSettings failed: $e');
    }
    return {};
  }

  Future<bool> saveSettings(Map<String, String> settings) async {
    try {
      final res = await http.post(
        Uri.parse('$baseUrl/api/settings'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(settings),
      ).timeout(const Duration(seconds: 4));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('saveSettings failed: $e');
      return false;
    }
  }

  // ── Bridge Actions ───────────────────────────────────────────────────

  Future<bool> startBridge() async {
    try {
      final res = await http.post(Uri.parse('$baseUrl/api/bridge/start')).timeout(const Duration(seconds: 15));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('startBridge failed: $e');
      return false;
    }
  }

  Future<bool> launchMt4() async {
    try {
      final res = await http.post(Uri.parse('$baseUrl/api/mt4/launch')).timeout(const Duration(seconds: 10));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('launchMt4 failed: $e');
      return false;
    }
  }

  Future<bool> stopBridge() async {
    try {
      final res = await http.post(Uri.parse('$baseUrl/api/bridge/stop')).timeout(const Duration(seconds: 8));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('stopBridge failed: $e');
      return false;
    }
  }

  Future<bool> emergencyHalt() async {
    try {
      final res = await http.post(Uri.parse('$baseUrl/api/bridge/halt')).timeout(const Duration(seconds: 5));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('emergencyHalt failed: $e');
      return false;
    }
  }

  Future<bool> resumeBridge() async {
    try {
      final res = await http.post(Uri.parse('$baseUrl/api/bridge/resume')).timeout(const Duration(seconds: 5));
      return res.statusCode == 200;
    } catch (e) {
      debugPrint('resumeBridge failed: $e');
      return false;
    }
  }
}
