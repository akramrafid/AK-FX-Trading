// Trade & System Data Models

enum Direction { buy, sell }

enum TradeStatus { pending, filled, rejected, unconfirmed, closed }

class TradeRecord {
  final int magic;
  final int ticket;
  final String symbol;
  final Direction direction;
  final double lots;
  final double entryPrice;
  final double currentPrice;
  final double slPrice;
  final double tpPrice;
  final double? exitPrice;
  final double pnl;
  final double rMultiple;
  final TradeStatus status;
  final String rejectionReason;
  final String comment;
  final DateTime createdAt;

  TradeRecord({
    required this.magic,
    required this.ticket,
    required this.symbol,
    required this.direction,
    required this.lots,
    required this.entryPrice,
    double? currentPrice,
    required this.slPrice,
    required this.tpPrice,
    this.exitPrice,
    this.pnl = 0.0,
    this.rMultiple = 0.0,
    required this.status,
    this.rejectionReason = '',
    this.comment = '',
    required this.createdAt,
  }) : currentPrice = currentPrice ?? entryPrice;

  factory TradeRecord.fromJson(Map<String, dynamic> json) {
    Direction dir = (json['direction'] ?? json['type'] ?? 'BUY').toString().toUpperCase().contains('SELL')
        ? Direction.sell
        : Direction.buy;

    TradeStatus st;
    final s = (json['status'] ?? 'PENDING').toString().toUpperCase();
    if (s == 'FILLED') {
      st = TradeStatus.filled;
    } else if (s == 'REJECTED') {
      st = TradeStatus.rejected;
    } else if (s == 'CLOSED') {
      st = TradeStatus.closed;
    } else if (s == 'UNCONFIRMED') {
      st = TradeStatus.unconfirmed;
    } else {
      st = TradeStatus.pending;
    }

    DateTime dt;
    try {
      dt = DateTime.parse(json['created_at'] ?? json['open_time'] ?? json['timestamp'] ?? DateTime.now().toIso8601String());
    } catch (_) {
      dt = DateTime.now();
    }

    final entry = (json['entry_price'] ?? json['open_price'] ?? json['target_entry'] as num?)?.toDouble() ?? 0.0;
    final cur = (json['current_price'] as num?)?.toDouble() ?? entry;

    return TradeRecord(
      magic: json['magic'] is int ? json['magic'] : int.tryParse(json['magic']?.toString() ?? '0') ?? 0,
      ticket: json['ticket'] is int ? json['ticket'] : int.tryParse(json['ticket']?.toString() ?? '0') ?? 0,
      symbol: json['symbol'] ?? 'EURUSDm',
      direction: dir,
      lots: (json['lots'] as num?)?.toDouble() ?? 0.0,
      entryPrice: entry,
      currentPrice: cur,
      slPrice: (json['sl'] ?? json['sl_price'] ?? json['stop_loss'] as num?)?.toDouble() ?? 0.0,
      tpPrice: (json['tp'] ?? json['tp_price'] ?? json['take_profit'] as num?)?.toDouble() ?? 0.0,
      exitPrice: (json['exit_price'] as num?)?.toDouble(),
      pnl: (json['profit'] ?? json['pnl'] as num?)?.toDouble() ?? 0.0,
      rMultiple: (json['r_multiple'] as num?)?.toDouble() ?? 0.0,
      status: st,
      rejectionReason: json['rejection_reason'] ?? json['message'] ?? '',
      comment: json['comment'] ?? '',
      createdAt: dt,
    );
  }
}

class CandleData {
  final DateTime time;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;

  CandleData({
    required this.time,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    this.volume = 0,
  });

  bool get isBullish => close >= open;

  factory CandleData.fromJson(Map<String, dynamic> json) {
    DateTime dt;
    try {
      dt = DateTime.parse(json['timestamp'] ?? json['time'] ?? DateTime.now().toIso8601String());
    } catch (_) {
      dt = DateTime.now();
    }
    return CandleData(
      time: dt,
      open: (json['open'] as num?)?.toDouble() ?? 0.0,
      high: (json['high'] as num?)?.toDouble() ?? 0.0,
      low: (json['low'] as num?)?.toDouble() ?? 0.0,
      close: (json['close'] as num?)?.toDouble() ?? 0.0,
      volume: (json['volume'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class AccountSummary {
  final int accountNumber;
  final String company;
  final String accountName;
  final String currency;
  final double balance;
  final double equity;
  final double margin;
  final double freeMargin;
  final double marginLevel;
  final double profit;
  final int leverage;
  final String symbol;
  final double bid;
  final double ask;
  final double spreadPips;
  final int digits;
  final int tradesToday;
  final int openTrades;
  final int openOrdersCount;
  final List<TradeRecord> orders;
  final Map<String, dynamic> pairs;

  AccountSummary({
    this.accountNumber = 70702138,
    this.company = 'Exness',
    this.accountName = 'Standard MT4',
    this.currency = 'USD',
    this.balance = 500.0,
    this.equity = 503.74,
    this.margin = 62.54,
    this.freeMargin = 441.20,
    this.marginLevel = 805.5,
    this.profit = 3.74,
    this.leverage = 200,
    this.symbol = 'EURUSDm',
    this.bid = 1.13737,
    this.ask = 1.13745,
    this.spreadPips = 0.8,
    this.digits = 5,
    this.tradesToday = 1,
    this.openTrades = 1,
    this.openOrdersCount = 1,
    this.orders = const [],
    this.pairs = const {},
  });

  double get dailyPnl => profit;

  factory AccountSummary.fromJson(Map<String, dynamic> json) {
    List<TradeRecord> parsedOrders = [];
    if (json['orders'] is List) {
      for (final o in (json['orders'] as List)) {
        if (o is Map<String, dynamic>) {
          parsedOrders.add(TradeRecord.fromJson(o));
        }
      }
    }

    final bal = (json['balance'] as num?)?.toDouble() ?? 500.0;
    final eq = (json['equity'] as num?)?.toDouble() ?? bal;
    final mg = (json['margin'] as num?)?.toDouble() ?? 0.0;
    final fmg = (json['free_margin'] as num?)?.toDouble() ?? (eq - mg);
    final prof = (json['profit'] ?? json['daily_pnl'] as num?)?.toDouble() ?? 0.0;
    final pairsMap = json['pairs'] is Map<String, dynamic>
        ? (json['pairs'] as Map<String, dynamic>)
        : <String, dynamic>{};

    return AccountSummary(
      accountNumber: json['account_number'] is int
          ? json['account_number']
          : int.tryParse(json['account_number']?.toString() ?? '70702138') ?? 70702138,
      company: json['company'] ?? 'Exness',
      accountName: json['account_name'] ?? 'Standard MT4',
      currency: json['currency'] ?? 'USD',
      balance: bal,
      equity: eq,
      margin: mg,
      freeMargin: fmg,
      marginLevel: (json['margin_level'] as num?)?.toDouble() ?? (mg > 0 ? (eq / mg * 100) : 0.0),
      profit: prof,
      leverage: json['leverage'] is int ? json['leverage'] : int.tryParse(json['leverage']?.toString() ?? '200') ?? 200,
      symbol: json['symbol'] ?? 'EURUSDm',
      bid: (json['bid'] as num?)?.toDouble() ?? 1.13737,
      ask: (json['ask'] as num?)?.toDouble() ?? 1.13745,
      spreadPips: (json['spread_pips'] as num?)?.toDouble() ?? 0.8,
      digits: json['digits'] is int ? json['digits'] : 5,
      tradesToday: json['trades_today'] is int ? json['trades_today'] : parsedOrders.length,
      openTrades: json['open_trades'] is int ? json['open_trades'] : parsedOrders.length,
      openOrdersCount: json['open_orders_count'] is int ? json['open_orders_count'] : parsedOrders.length,
      orders: parsedOrders,
      pairs: pairsMap,
    );
  }
}

class BridgeState {
  final bool isRunning;
  final bool emergencyHalt;
  final String symbol;
  final String timeframe;
  final double balance;
  final int ordersToday;
  final int openTrades;
  final String watchdogState;
  final String watchdogMessage;
  final String strategyMode;

  BridgeState({
    this.isRunning = false,
    this.emergencyHalt = false,
    this.symbol = 'EURUSDm',
    this.timeframe = 'M5',
    this.balance = 500.0,
    this.ordersToday = 0,
    this.openTrades = 0,
    this.watchdogState = 'HEALTHY',
    this.watchdogMessage = 'System operational',
    this.strategyMode = 'c1_wickswap',
  });

  factory BridgeState.fromJson(Map<String, dynamic> json) {
    final wd = json['watchdog'] as Map<String, dynamic>?;
    return BridgeState(
      isRunning: json['bridge_running'] == true,
      emergencyHalt: json['emergency_halt'] == true,
      symbol: json['symbol'] ?? 'EURUSDm',
      timeframe: json['timeframe'] ?? 'M5',
      balance: (json['balance'] as num?)?.toDouble() ?? 500.0,
      ordersToday: json['orders_today'] is int ? json['orders_today'] : 0,
      openTrades: json['open_trades'] is int ? json['open_trades'] : 0,
      watchdogState: wd?['state'] ?? 'HEALTHY',
      watchdogMessage: wd?['message'] ?? 'System operational',
      strategyMode: json['strategy_mode'] ?? 'c1_wickswap',
    );
  }
}
