'use client';

import React from 'react';
import { Layers, ArrowUpRight, ArrowDownRight, XCircle } from 'lucide-react';
import { Position } from '../types/trading';

interface PositionsProps {
  orders: Position[];
}

export const ActivePositionsCard: React.FC<PositionsProps> = ({ orders }) => {
  return (
    <div className="glass-panel p-5 rounded-xl border border-white/10 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-accent-green-15 border border-accent-green-40 text-accent-green">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Live Market Positions</h3>
            <p className="text-[11px] text-slate-400">Open orders managed via MT4 DWX Bridge</p>
          </div>
        </div>
        <div className="px-2.5 py-1 rounded bg-black/40 border border-white/10 text-xs font-mono text-slate-300 font-semibold">
          {orders.length} ACTIVE {orders.length === 1 ? 'POSITION' : 'POSITIONS'}
        </div>
      </div>

      {/* Orders Table */}
      {orders.length === 0 ? (
        <div className="py-8 flex flex-col items-center justify-center text-center rounded-lg bg-black/20 border border-white/5">
          <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center mb-2 text-slate-500">
            <Layers className="w-5 h-5" />
          </div>
          <p className="text-xs font-semibold text-slate-300">No Open Positions</p>
          <p className="text-[11px] text-slate-500 max-w-sm mt-0.5">
            Rule engine is scanning for M5/M15 wick-swap sweep setups during active session hours.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-white/10 text-slate-400">
                <th className="py-2 px-3">Ticket</th>
                <th className="py-2 px-3">Type</th>
                <th className="py-2 px-3">Lots</th>
                <th className="py-2 px-3">Open Price</th>
                <th className="py-2 px-3">Stop Loss</th>
                <th className="py-2 px-3">Take Profit</th>
                <th className="py-2 px-3 text-right">Profit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {orders.map((pos) => {
                const isBuy = pos.type?.toUpperCase().includes('BUY');
                const isProfitable = pos.profit >= 0;
                return (
                  <tr key={pos.ticket} className="hover:bg-white/5 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-white">Ticket: {pos.ticket}</td>
                    <td className="py-2.5 px-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                        isBuy ? 'bg-accent-green-15 text-accent-green' : 'bg-accent-red-15 text-accent-red'
                      }`}>
                        {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {pos.type}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-300">{pos.lots?.toFixed(2)}</td>
                    <td className="py-2.5 px-3 text-white">{pos.open_price?.toFixed(5)}</td>
                    <td className="py-2.5 px-3 text-accent-red">{pos.stop_loss ? pos.stop_loss.toFixed(5) : '-'}</td>
                    <td className="py-2.5 px-3 text-accent-green">{pos.take_profit ? pos.take_profit.toFixed(5) : '-'}</td>
                    <td className={`py-2.5 px-3 text-right font-bold text-sm ${
                      isProfitable ? 'text-accent-green' : 'text-accent-red'
                    }`}>
                      {isProfitable ? '+' : ''}${pos.profit.toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
