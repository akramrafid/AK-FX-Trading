'use client';

import React from 'react';
import { Cpu, Zap, Activity, CheckCircle, Radio } from 'lucide-react';
import { BridgeStatus } from '../types/trading';

interface StrategyProps {
  status: BridgeStatus;
  strategyMode?: string;
}

export const StrategyWatchdogCard: React.FC<StrategyProps> = ({ status, strategyMode = 'c1_wickswap' }) => {
  const isC1 = strategyMode === 'c1_wickswap';

  return (
    <div className="glass-panel p-5 rounded-xl border border-white/10 flex flex-col justify-between gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-accent-lime-15 border border-accent-lime-40 text-accent-lime">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Strategy & Watchdog Engine</h3>
            <p className="text-[11px] text-slate-400">Deterministic Sweep Rejection System</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-lime-15 text-accent-lime border border-accent-lime-40 text-xs font-mono font-bold">
          <Radio className="w-3 h-3 animate-pulse" />
          {isC1 ? 'C1 WICK-SWAP' : 'INSTITUTIONAL'}
        </div>
      </div>

      {/* Rules Overview */}
      <div className="space-y-2.5 text-xs">
        <div className="p-3 rounded-lg bg-black/30 border border-white/5 flex items-center justify-between">
          <span className="text-slate-300 font-medium flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-accent-lime" />
            Execution Parameters
          </span>
          <span className="font-mono text-accent-lime font-bold">
            {isC1 ? '1:5 R:R • BE @ 2.0R • C1 Stop' : '5 Pillars • 70% @ 2R • 5R Runner'}
          </span>
        </div>

        <div className="p-3 rounded-lg bg-black/30 border border-white/5 flex items-center justify-between">
          <span className="text-slate-300 font-medium flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-accent-cyan" />
            Intrabar HTF Sweep Detection
          </span>
          <span className="font-mono text-accent-green font-bold flex items-center gap-1">
            <CheckCircle className="w-3 h-3" />
            Active (M5 & M15 formation)
          </span>
        </div>

        <div className="p-3 rounded-lg bg-black/30 border border-white/5 flex items-center justify-between">
          <span className="text-slate-300 font-medium flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            Watchdog Supervisor Status
          </span>
          <span className="font-mono text-white font-bold">
            {status.watchdog?.state || 'HEALTHY'} ({status.watchdog?.bars_processed ?? 0} bars)
          </span>
        </div>
      </div>

      {/* Footer System Message */}
      <div className="text-[11px] text-slate-400 bg-black/20 p-2.5 rounded-lg border border-white/5 font-mono">
        {status.watchdog?.message || 'System operational. Last tick processed < 1.0s.'}
      </div>
    </div>
  );
};
