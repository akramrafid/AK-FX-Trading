export interface AccountInfo {
  account_number: number | string;
  company: string;
  account_name?: string;
  currency: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  margin_level: number;
  profit: number;
  leverage: number;
  symbol: string;
  bid: number;
  ask: number;
  spread_pips: number;
  digits: number;
  open_orders_count?: number;
  orders: Position[];
  pairs?: Record<string, { bid: number; ask: number; spread_pips: number }>;
  timestamp?: string;
  trades_today?: number;
}

export interface UserAccount {
  id: string;
  account_number: string;
  broker: string;
  server: string;
  name?: string;
  currency?: string;
  balance?: number;
  equity?: number;
  leverage?: number;
  is_active?: boolean;
  created_at?: string;
}

export interface Position {
  ticket: number;
  symbol: string;
  type: 'BUY' | 'SELL' | string;
  lots: number;
  open_price: number;
  current_price?: number;
  open_time?: string;
  stop_loss: number;
  take_profit: number;
  profit: number;
  magic?: number;
  comment?: string;
}

export interface WatchdogStatus {
  state: 'HEALTHY' | 'WARNING' | 'CRITICAL' | 'STALE' | string;
  bars_processed: number;
  orders_dispatched: number;
  message: string;
  last_bar_time?: string;
}

export interface BridgeStatus {
  bridge_running: boolean;
  emergency_halt: boolean;
  strategy_mode?: string;
  symbol?: string;
  timeframe?: string;
  watchdog?: WatchdogStatus;
  watchdog_state?: string;
  orders_today?: number;
  daily_drawdown_pct?: number;
  max_daily_drawdown_pct?: number;
  session_filter_active?: boolean;
}

export interface Candle {
  time: number; // Unix timestamp in seconds for lightweight-charts
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface TradingSignal {
  id?: string;
  symbol: string;
  timeframe: string;
  signal_type: 'BUY' | 'SELL' | string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward?: number;
  status?: string;
  timestamp: string;
  notes?: string;
}

export interface Settings {
  [key: string]: string;
}
