'use client';

import React from 'react';
import { Shield, Clock, AlertTriangle, CheckCircle2, Gauge, Zap } from 'lucide-react';
import { BridgeStatus, WatchdogStatus } from '../types/trading';

interface RiskProps {
  status: BridgeStatus;
  tradesToday: number;
  maxDailyTrades?: number;
  spreadPips?: number;
  maxSpread?: number;
  sessionStartHour?: number;
  sessionEndHour?: number;
}

export const RiskGuardrailsCard: React.FC<RiskProps> = ({
  status,
  tradesToday,
  maxDailyTrades = 3,
  spreadPips = 1.4,
  maxSpread = 2.5,
  sessionStartHour = 7,
  sessionEndHour = 18,
}) => {
  const isDrawdownHealthy = (status.daily_drawdown_pct || 0) < (status.max_daily_drawdown_pct || 3.0);
  const isSpreadHealthy = spreadPips <= maxSpread;

  // Format session hours
  const startStr = String(sessionStartHour).padStart(2, '0') + ':00';
  const endStr = String(sessionEndHour).padStart(2, '0') + ':00';

  const tradesRatio = Math.min(1, tradesToday / (maxDailyTrades || 3));

  return (
    <div className="glass-panel p-5 rounded-xl border border-white/10 flex flex-col justify-between gap-4">
      {/* Title & Overall Status */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-accent-cyan-15 border border-accent-cyan-40 text-accent-cyan">
            <Shield className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Risk Guardrails & Session</h3>
            <p className="text-[11px] text-slate-400">Enforced by Rule Engine & Watchdog</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-black/40 border border-white/10 text-xs font-mono">
          <CheckCircle2 className="w-3.5 h-3.5 text-accent-green" />
          <span className="text-accent-green font-semibold">GUARDRAILS ENGAGED</span>
        </div>
      </div>

      {/* Grid of Risk Meters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Trades Today */}
        <div className="p-3 rounded-lg bg-black/30 border border-white/5 flex flex-col justify-between">
          <div className="flex justify-between items-center text-xs text-slate-400 mb-1">
            <span>Daily Executions</span>
            <span className="font-mono text-white font-bold">{tradesToday} / {maxDailyTrades || '∞'}</span>
          </div>
          <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-accent-lime h-full rounded-full transition-all"
              style={{ width: `${tradesRatio * 100}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-500 mt-1.5">Max {maxDailyTrades} per 24h cycle</span>
        </div>

        {/* Daily Drawdown Ceiling */}
        <div className="p-3 rounded-lg bg-black/30 border border-white/5 flex flex-col justify-between">
          <div className="flex justify-between items-center text-xs text-slate-400 mb-1">
            <span>Daily Drawdown</span>
            <span className="font-mono font-bold text-accent-green">
              {status.daily_drawdown_pct || '0.0'}% / {status.max_daily_drawdown_pct || '3.0'}%
            </span>
          </div>
          <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${isDrawdownHealthy ? 'bg-accent-green' : 'bg-accent-red'}`}
              style={{ width: `${((status.daily_drawdown_pct || 0) / (status.max_daily_drawdown_pct || 3.0)) * 100}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-500 mt-1.5">Circuit breaker at 3.0%</span>
        </div>

        {/* Live Spread Meter */}
        <div className="p-3 rounded-lg bg-black/30 border border-white/5 flex flex-col justify-between">
          <div className="flex justify-between items-center text-xs text-slate-400 mb-1">
            <span>Live Spread</span>
            <span className={`font-mono font-bold ${isSpreadHealthy ? 'text-accent-lime' : 'text-accent-red'}`}>
              {spreadPips.toFixed(1)}p / Cap {maxSpread.toFixed(1)}p
            </span>
          </div>
          <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${isSpreadHealthy ? 'bg-accent-lime' : 'bg-accent-red'}`}
              style={{ width: `${Math.min(100, (spreadPips / maxSpread) * 100)}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-500 mt-1.5">High volatility protection</span>
        </div>
      </div>

      {/* Session Window & Strict 12 AM Cutoff Banner */}
      <div className="p-3 rounded-lg bg-accent-lime-10 border border-accent-lime-40 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-accent-lime" />
          <div>
            <div className="text-xs font-bold text-white flex items-center gap-2">
              Trading Window: <span className="font-mono text-accent-lime">{startStr} - {endStr} UTC</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-black/60 text-accent-lime font-mono border border-accent-lime-40 font-bold">
                12:00 AM LOCAL CUTOFF ACTIVE
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Corresponds to 1:00 PM – 12:00 AM Dhaka (UTC+6). No setups arm or execute after 12 AM.
            </p>
          </div>
        </div>

        {/* Watchdog Status Pill */}
        <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
          <span className="w-2 h-2 rounded-full bg-accent-green animate-ping" />
          <span>Sync &lt; 1.0s</span>
          <span className="text-slate-500">•</span>
          <span className="text-slate-400">{status.watchdog?.bars_processed ?? 0} bars verified</span>
        </div>
      </div>
    </div>
  );
};
