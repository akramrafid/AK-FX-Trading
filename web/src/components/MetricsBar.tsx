'use client';

import React from 'react';
import { Wallet, TrendingUp, ShieldCheck, PieChart, Layers } from 'lucide-react';
import { AccountInfo } from '../types/trading';

interface MetricsBarProps {
  account: AccountInfo;
  riskPct?: number; // e.g. 0.01 for 1%
}

export const MetricsBar: React.FC<MetricsBarProps> = ({ account, riskPct = 0.01 }) => {
  // Calculate dynamic lot sizing based on account balance & risk
  // In C1 Wick-Swap on USDCAD (SL ~ 4-5 pips avg = 45 points), 1% on $492 is ~$4.92 risk -> ~0.11 lots
  const riskAmount = (account.balance || 0) * riskPct;
  const estimatedLotSize = Math.max(0.01, Math.round(((riskAmount / 45) * 100)) / 100);

  const isProfitPositive = account.profit >= 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3.5 w-full">
      {/* Balance */}
      <div className="glass-panel p-3.5 rounded-xl border border-white/10 flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
          <span className="flex items-center gap-1.5">
            <Wallet className="w-3.5 h-3.5 text-accent-lime" />
            Balance
          </span>
          <span className="text-[10px] text-slate-500 font-mono">USD</span>
        </div>
        <div className="text-xl font-black text-white font-mono tracking-tight">
          ${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>

      {/* Equity */}
      <div className="glass-panel p-3.5 rounded-xl border border-white/10 flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
          <span className="flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-accent-cyan" />
            Equity
          </span>
          <span className="text-[10px] text-slate-500 font-mono">100%</span>
        </div>
        <div className="text-xl font-black text-white font-mono tracking-tight">
          ${account.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>

      {/* Floating P&L */}
      <div className="glass-panel p-3.5 rounded-xl border border-white/10 flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
          <span className="flex items-center gap-1.5">
            <PieChart className="w-3.5 h-3.5 text-accent-green" />
            Floating P&L
          </span>
          <span className="text-[10px] font-mono px-1 rounded bg-white/5 text-slate-400">
            {account.open_orders_count || account.orders?.length || 0} Open
          </span>
        </div>
        <div className={`text-xl font-black font-mono tracking-tight ${isProfitPositive ? 'text-accent-green' : 'text-accent-red'}`}>
          {isProfitPositive ? '+' : ''}${account.profit.toFixed(2)}
        </div>
      </div>

      {/* Free Margin */}
      <div className="glass-panel p-3.5 rounded-xl border border-white/10 flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
            Free Margin
          </span>
          <span className="text-[10px] text-slate-500 font-mono">Available</span>
        </div>
        <div className="text-xl font-black text-white font-mono tracking-tight">
          ${account.free_margin.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>

      {/* Dynamic Sizing (ATR Lots) */}
      <div className="glass-panel p-3.5 rounded-xl border border-white/10 flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
          <span className="flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-accent-lime" />
            Dynamic Size
          </span>
          <span className="text-[10px] text-accent-lime font-mono">{(riskPct * 100).toFixed(1)}% Risk</span>
        </div>
        <div className="text-xl font-black text-accent-lime font-mono tracking-tight">
          {estimatedLotSize.toFixed(2)} Lots
        </div>
      </div>

      {/* Account Info */}
      <div className="glass-panel p-3.5 rounded-xl border border-white/10 flex flex-col justify-between">
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
          <span className="text-slate-400">Terminal</span>
          <span className="text-[10px] font-mono text-slate-400">1:{account.leverage || 200}</span>
        </div>
        <div className="text-sm font-bold text-slate-200 truncate font-mono">
          ID: {account.account_number}
        </div>
        <div className="text-[11px] text-slate-500 truncate">
          {account.company || 'Exness-Real21'}
        </div>
      </div>
    </div>
  );
};
