'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../lib/api';
import { AccountInfo, BridgeStatus, Candle, Position, Settings, TradingSignal } from '../types/trading';

const defaultAccount: AccountInfo = {
  account_number: '69800896',
  company: 'Exness Technologies Ltd',
  currency: 'USD',
  balance: 5000.00,
  equity: 5000.00,
  margin: 0,
  free_margin: 5000.00,
  margin_level: 0,
  profit: 0,
  leverage: 2000,
  symbol: 'USDCADm',
  bid: 1.42546,
  ask: 1.42560,
  spread_pips: 1.4,
  digits: 5,
  orders: [],
  trades_today: 0,
};

const defaultStatus: BridgeStatus = {
  bridge_running: true,
  emergency_halt: false,
  strategy_mode: 'c1_wickswap',
  symbol: 'USDCADm',
  timeframe: 'M5',
  orders_today: 0,
  daily_drawdown_pct: 0.0,
  max_daily_drawdown_pct: 3.0,
  session_filter_active: true,
  watchdog: {
    state: 'HEALTHY',
    bars_processed: 0,
    orders_dispatched: 0,
    message: 'System operational.',
  },
};

export function useTradingStream() {
  const [account, setAccount] = useState<AccountInfo>(defaultAccount);
  const [status, setStatus] = useState<BridgeStatus>(defaultStatus);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [settings, setSettings] = useState<Settings>({
    SESSION_START_HOUR: '7',
    SESSION_END_HOUR: '18',
    STRATEGY_MODE: 'c1_wickswap',
    TRADING_SYMBOL: 'USDCADm',
    TRADING_TIMEFRAME: 'M5',
    RISK_PER_TRADE_PCT: '0.01',
    MAX_DAILY_LOSS_PCT: '0.03',
    MAX_DAILY_TRADES: '3',
    MAX_SPREAD_PIPS: '2.5',
    ENABLE_INTRABAR_SWEEP: 'true',
  });
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [closedTrades, setClosedTrades] = useState<Position[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [systemNotice, setSystemNotice] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const activeAccountRef = useRef<string | number>('69800896');

  const refreshData = useCallback(async (accountNum?: string | number) => {
    if (accountNum !== undefined) {
      activeAccountRef.current = accountNum;
    }
    const currAcc = activeAccountRef.current;
    try {
      const [accData, statusData, settingsData, tradesData, sigData] = await Promise.allSettled([
        api.getAccount(),
        api.getStatus(),
        api.getSettings(),
        api.getTrades(currAcc),
        api.getSignals(),
      ]);

      if (accData.status === 'fulfilled' && accData.value) {
        setAccount(accData.value);
      }
      if (statusData.status === 'fulfilled' && statusData.value) {
        setStatus(statusData.value);
      }
      if (settingsData.status === 'fulfilled' && settingsData.value) {
        setSettings(settingsData.value);
      }
      if (tradesData.status === 'fulfilled' && tradesData.value) {
        setClosedTrades(tradesData.value);
      }
      if (sigData.status === 'fulfilled' && sigData.value) {
        setSignals(sigData.value);
      }
    } catch (err) {
      console.warn('REST refresh error:', err);
    }
  }, []);

  const loadCandles = useCallback(async (sym?: string, tf?: string) => {
    const symbol = sym || settings['TRADING_SYMBOL'] || 'USDCADm';
    const timeframe = tf || settings['TRADING_TIMEFRAME'] || 'M5';
    try {
      const rawCandles = await api.getCandles(symbol, timeframe);
      if (rawCandles && rawCandles.length > 0) {
        setCandles(rawCandles);
      }
    } catch (e) {
      console.warn('Failed to load candles:', e);
    }
  }, [settings]);

  useEffect(() => {
    refreshData();
    loadCandles();
    const interval = setInterval(refreshData, 3000);
    return () => clearInterval(interval);
  }, [refreshData, loadCandles]);

  // WebSocket Setup
  useEffect(() => {
    function connectWs() {
      if (typeof window === 'undefined') return;

      const wsUrl = window.location.port === '8642'
        ? `ws://${window.location.host}/ws`
        : 'ws://127.0.0.1:8642/ws';

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          console.log('Trading WebSocket Connected');
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'account_update' || data.account_number) {
              setAccount((prev) => ({ ...prev, ...data }));
            } else if (data.type === 'status' || data.bridge_running !== undefined) {
              setStatus((prev) => ({ ...prev, ...data }));
            } else if (data.type === 'candle') {
              setCandles((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.time === data.candle.time) {
                  updated[updated.length - 1] = data.candle;
                } else {
                  updated.push(data.candle);
                }
                return updated.slice(-300);
              });
            } else if (data.type === 'system_notice') {
              setSystemNotice(data.message);
              setTimeout(() => setSystemNotice(null), 5000);
            }
          } catch (e) {
            console.error('WS parse error:', e);
          }
        };

        ws.onclose = () => {
          setIsConnected(false);
          reconnectTimeoutRef.current = setTimeout(connectWs, 3000);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch (e) {
        console.warn('WS connection failed:', e);
        reconnectTimeoutRef.current = setTimeout(connectWs, 3000);
      }
    }

    connectWs();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  return {
    account,
    status,
    candles,
    settings,
    signals,
    closedTrades,
    isConnected,
    systemNotice,
    refreshData,
    loadCandles,
    startBridge: api.startBridge,
    stopBridge: api.stopBridge,
    haltBridge: api.haltBridge,
    resumeBridge: api.resumeBridge,
    launchMT4: api.launchMT4,
    updateSettings: async (newSettings: Settings) => {
      await api.updateSettings(newSettings);
      await refreshData();
    },
    connectAccount: async (data: {
      account_number: string;
      password?: string;
      server?: string;
      broker?: string;
      balance?: number;
      leverage?: number;
      terminal_path?: string;
    }) => {
      const res = await api.connectAccount(data);
      await refreshData(data.account_number);
      return res;
    },
  };
}
