'use client';

import React, { useState } from 'react';
import { Shield, Clock, TrendingUp, CheckCircle2 } from 'lucide-react';
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
  tradesToday = 1,
  maxDailyTrades = 3,
  spreadPips = 1.4,
  maxSpread = 2.5,
}) => {
  const [period, setPeriod] = useState<'WEEK' | 'MONTH'>('MONTH');

  return (
    <div className="w-full bg-window-card text-white rounded-3xl p-6 border border-white/10 shadow-2xl flex flex-col gap-5">
      {/* 1. Header: Title + Period Switcher */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold text-slate-100 tracking-tight">
          Crypto Leaders of Growth and Fall
        </h4>
        <div className="flex items-center gap-1 text-[11px] font-semibold text-slate-400">
          <button
            onClick={() => setPeriod('WEEK')}
            className={`transition-colors ${period === 'WEEK' ? 'text-white font-bold' : 'text-slate-500 hover:text-slate-300'}`}
          >
            WEEK
          </button>
          <span className="text-slate-600">/</span>
          <button
            onClick={() => setPeriod('MONTH')}
            className={`transition-colors ${period === 'MONTH' ? 'text-white font-bold' : 'text-slate-500 hover:text-slate-300'}`}
          >
            MONTH
          </button>
        </div>
      </div>

      {/* 2. Three Metric Columns */}
      <div className="grid grid-cols-3 gap-2 pt-1">
        {/* Metric 1 */}
        <div className="flex flex-col">
          <div className="text-sm font-bold text-white font-mono">$64,189.90</div>
          <div className="text-[11px] text-slate-400">Bitcoin</div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-accent-lime font-mono mt-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-lime" />
            <span>32.1%</span>
          </div>
        </div>

        {/* Metric 2 */}
        <div className="flex flex-col">
          <div className="text-sm font-bold text-white font-mono">$3,144.02</div>
          <div className="text-[11px] text-slate-400">Doge</div>
          <div className="flex items-center gap-1 text-[11px] font-bold text-accent-purple font-mono mt-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-purple" />
            <span>16.7%</span>
          </div>
        </div>

        {/* Metric 3 */}
        <div className="flex flex-col">
          <div className="text-sm font-bold text-white font-mono">$12.500</div>
          <div className="text-[11px] text-slate-400">Full-time</div>
          <div className="flex items-center gap-1 text-[11px] font-semibold text-slate-400 font-mono mt-2">
            <span>Stable</span>
          </div>
        </div>
      </div>

      {/* 3. Tri-color Segmented Progress Meter Bar */}
      <div className="flex flex-col gap-1.5 pt-1">
        <div className="w-full h-3 rounded-full bg-slate-800/80 p-0.5 flex items-center gap-1 overflow-hidden shadow-inner">
          {/* Segment 1: Neon Lime */}
          <div className="h-full rounded-full bg-accent-lime flex-[4] shadow-sm" />
          {/* Segment 2: Electric Purple */}
          <div className="h-full rounded-full bg-accent-purple flex-[4] shadow-sm" />
          {/* Segment 3: Slate Gray */}
          <div className="h-full rounded-full bg-slate-700 flex-[3]" />
        </div>

        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-0.5">
          <span>Feb</span>
          <span>1:28</span>
        </div>
      </div>

      {/* 4. Telemetry Footer: 12:00 AM Local Cutoff Active Banner */}
      <div className="p-3 rounded-2xl bg-window-card-inset border border-white/5 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-accent-lime" />
          <span className="text-[11px] text-slate-300 font-mono">12:00 AM LOCAL CUTOFF ACTIVE</span>
        </div>
        <span className="text-[10px] font-mono text-accent-lime font-bold">07:00–18:00 UTC</span>
      </div>
    </div>
  );
};
