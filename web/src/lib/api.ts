import { AccountInfo, BridgeStatus, Candle, Position, Settings, TradingSignal } from '../types/trading';

const BASE_URL = typeof window !== 'undefined'
  ? (window.location.port === '8642' ? window.location.origin : 'http://127.0.0.1:8642')
  : 'http://127.0.0.1:8642';

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText} on ${endpoint}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async getStatus(): Promise<BridgeStatus> {
    return fetchJson<BridgeStatus>('/api/status');
  },

  async getAccount(): Promise<AccountInfo> {
    return fetchJson<AccountInfo>('/api/account');
  },

  async getAccountDetect(): Promise<{
    status: string;
    detected_files_dir: string;
    detected_exe_path: string;
    mt4_process_running: boolean;
    current_account: string;
    current_server: string;
    symbol: string;
  }> {
    return fetchJson('/api/account/detect');
  },

  async getTrades(): Promise<Position[]> {
    return fetchJson<Position[]>('/api/trades');
  },

  async getSignals(): Promise<TradingSignal[]> {
    return fetchJson<TradingSignal[]>('/api/signals');
  },

  async getCandles(symbol = 'USDCADm', timeframe = 'M5'): Promise<Candle[]> {
    try {
      const data = await fetchJson<any[]>(`/api/candles?symbol=${symbol}&timeframe=${timeframe}`);
      if (!Array.isArray(data)) return [];
      return data.map((c: any) => {
        let t = 0;
        if (typeof c.time === 'number') {
          t = c.time;
        } else if (typeof c.timestamp === 'string') {
          t = Math.floor(new Date(c.timestamp).getTime() / 1000);
        } else if (typeof c.time === 'string') {
          t = Math.floor(new Date(c.time).getTime() / 1000);
        } else {
          t = Math.floor(Date.now() / 1000);
        }
        return {
          time: t,
          open: Number(c.open || c.o || 0),
          high: Number(c.high || c.h || 0),
          low: Number(c.low || c.l || 0),
          close: Number(c.close || c.c || 0),
          volume: Number(c.volume || c.v || 0),
        };
      }).sort((a, b) => a.time - b.time);
    } catch {
      return [];
    }
  },

  async getSettings(): Promise<Settings> {
    return fetchJson<Settings>('/api/settings');
  },

  async updateSettings(settings: Settings): Promise<{ status: string; keys: string[] }> {
    return fetchJson('/api/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    });
  },

  async connectAccount(data: {
    account_number: string;
    password?: string;
    server?: string;
    terminal_path?: string;
  }): Promise<{ status: string; message: string }> {
    return fetchJson('/api/account/connect', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async startBridge(): Promise<{ status: string }> {
    return fetchJson('/api/bridge/start', { method: 'POST' });
  },

  async stopBridge(): Promise<{ status: string }> {
    return fetchJson('/api/bridge/stop', { method: 'POST' });
  },

  async haltBridge(): Promise<{ status: string }> {
    return fetchJson('/api/bridge/halt', { method: 'POST' });
  },

  async resumeBridge(): Promise<{ status: string }> {
    return fetchJson('/api/bridge/resume', { method: 'POST' });
  },

  async launchMT4(): Promise<{ status: string }> {
    return fetchJson('/api/mt4/launch', { method: 'POST' });
  },
};
