'use client';

import React, { useState } from 'react';
import { Shield, Clock, CheckCircle2, AlertTriangle, Activity } from 'lucide-react';
import { BridgeStatus } from '../types/trading';

interface LeadersRiskCardProps {
  status: BridgeStatus;
  tradesToday?: number;
  maxDailyTrades?: number;
  spreadPips?: number;
  maxSpread?: number;
}

export const LeadersRiskCard: React.FC<LeadersRiskCardProps> = ({
  status,
  tradesToday = 0,
  maxDailyTrades = 3,
  spreadPips = 1.4,
  maxSpread = 2.5,
}) => {
  const [period, setPeriod] = useState<'TODAY' | 'WEEK'>('TODAY');

  const drawdownPct = status.daily_drawdown_pct || 0;
  const maxDrawdownPct = status.max_daily_drawdown_pct || 3.0;
  const isDrawdownSafe = drawdownPct < maxDrawdownPct;
  const isSpreadSafe = spreadPips <= maxSpread;
  const isUnlimitedTrades = !maxDailyTrades || maxDailyTrades === 0;
  const tradesRemaining = isUnlimitedTrades ? 'Unlimited' : `${Math.max(0, maxDailyTrades - tradesToday)} Allowed`;
  const quotaDisplay = isUnlimitedTrades ? `${tradesToday} / ∞` : `${tradesToday} / ${maxDailyTrades}`;

  return (
    <div className="w-full bg-window-card text-white rounded-3xl p-6 border border-white/10 shadow-2xl flex flex-col gap-5">
      {/* 1. Header: Title + Period Switcher */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-accent-lime" />
          <h4 className="text-sm font-bold text-slate-100 tracking-tight">
            Risk Guardrails & Watchdog
          </h4>
        </div>
        <div className="flex items-center gap-1 text-[11px] font-semibold text-slate-400">
          <button
            onClick={() => setPeriod('TODAY')}
            className={`transition-colors cursor-pointer ${period === 'TODAY' ? 'text-white font-bold' : 'text-slate-500 hover:text-slate-300'}`}
          >
            TODAY
          </button>
          <span className="text-slate-600">/</span>
          <button
            onClick={() => setPeriod('WEEK')}
            className={`transition-colors cursor-pointer ${period === 'WEEK' ? 'text-white font-bold' : 'text-slate-500 hover:text-slate-300'}`}
          >
            WEEK
          </button>
        </div>
      </div>

      {/* 2. Three Metric Columns */}
      <div className="grid grid-cols-3 gap-2 pt-1">
        {/* Metric 1: Daily Drawdown */}
        <div className="flex flex-col">
          <div className="text-sm font-bold text-white font-mono">
            {drawdownPct.toFixed(2)}%
          </div>
          <div className="text-[11px] text-slate-400">Daily Drawdown</div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-accent-lime font-mono mt-2">
            <span className={`w-1.5 h-1.5 rounded-full ${isDrawdownSafe ? 'bg-accent-lime' : 'bg-rose-500'}`} />
            <span>{isDrawdownSafe ? `Safe (< ${maxDrawdownPct.toFixed(1)}%)` : 'BREACH'}</span>
          </div>
        </div>

        {/* Metric 2: Live Spread */}
        <div className="flex flex-col">
          <div className="text-sm font-bold text-white font-mono">
            {spreadPips.toFixed(1)} pips
          </div>
          <div className="text-[11px] text-slate-400">USDCADm Spread</div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-accent-purple font-mono mt-2">
            <span className={`w-1.5 h-1.5 rounded-full ${isSpreadSafe ? 'bg-accent-purple' : 'bg-rose-500'}`} />
            <span>{isSpreadSafe ? `Optimal (< ${maxSpread.toFixed(1)}p)` : 'High'}</span>
          </div>
        </div>

        {/* Metric 3: Trade Quota */}
        <div className="flex flex-col">
          <div className="text-sm font-bold text-white font-mono">
            {quotaDisplay}
          </div>
          <div className="text-[11px] text-slate-400">Trades Executed</div>
          <div className="flex items-center gap-1 text-[11px] font-semibold text-slate-400 font-mono mt-2">
            <span>{tradesRemaining}</span>
          </div>
        </div>
      </div>

      {/* 3. Tri-color Segmented Progress Meter Bar */}
      <div className="flex flex-col gap-1.5 pt-1">
        <div className="w-full h-3 rounded-full bg-slate-800/80 p-0.5 flex items-center gap-1 overflow-hidden shadow-inner">
          {/* Segment 1: Drawdown / Risk Safety (Neon Lime) */}
          <div className="h-full rounded-full bg-accent-lime flex-[4] shadow-sm" title="Risk & Drawdown Safe" />
          {/* Segment 2: Trade Quota / Execution (Electric Purple) */}
          <div className="h-full rounded-full bg-accent-purple flex-[4] shadow-sm" title="Quota Allocation" />
          {/* Segment 3: Session Window Buffer (Slate) */}
          <div className="h-full rounded-full bg-slate-700 flex-[3]" title="Session Margin" />
        </div>

        <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 pt-0.5">
          <span className="flex items-center gap-1">
            <Activity className="w-3 h-3 text-accent-lime" />
            London/NY Window: 07:00–18:00 UTC
          </span>
          <span className="text-accent-lime font-semibold">Sync &lt; 1.0s • Healthy</span>
        </div>
      </div>

      {/* 4. Telemetry Footer: 12:00 AM Local Cutoff Active Banner */}
      <div className="p-3 rounded-2xl bg-window-card-inset border border-white/5 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-accent-lime" />
          <span className="text-[11px] text-slate-300 font-mono">12:00 AM LOCAL CUTOFF ACTIVE</span>
        </div>
        <span className="text-[10px] font-mono text-accent-lime font-bold">1:00 PM–12:00 AM Dhaka</span>
      </div>
    </div>
  );
};
