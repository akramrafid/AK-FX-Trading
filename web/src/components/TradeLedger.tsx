'use client';

import React, { useState, useMemo } from 'react';
import {
  Activity,
  History,
  ArrowUpRight,
  ArrowDownRight,
  Database,
  Filter,
  Search,
  CheckCircle2,
  TrendingUp,
  Award,
  Wallet,
  Clock,
  Layers,
  ChevronLeft,
  ChevronRight,
  MoreVertical,
} from 'lucide-react';
import { Position } from '../types/trading';

export interface TradeRecord {
  ticket: number;
  account_number?: number | string;
  symbol: string;
  direction: 'BUY' | 'SELL' | string;
  lots: number;
  entry_price: number;
  current_price?: number;
  close_price?: number;
  sl_price?: number;
  tp_price?: number;
  pnl: number;
  pips?: number;
  status: 'RUNNING' | 'FILLED' | 'CLOSED' | string;
  exit_reason?: string;
  created_at: string;
  closed_at?: string;
  comment?: string;
}

interface TradeLedgerProps {
  runningTrades: Position[];
  tradeHistory: TradeRecord[];
  activeAccount: string | number;
  currentBid?: number;
  currentAsk?: number;
  activeTab?: 'running' | 'history';
  onTabChange?: (tab: 'running' | 'history') => void;
}

export const TradeLedger: React.FC<TradeLedgerProps> = ({
  runningTrades,
  tradeHistory,
  activeAccount,
  currentBid = 1.42548,
  currentAsk = 1.42571,
  activeTab = 'running',
  onTabChange,
}) => {
  const [tab, setTab] = useState<'running' | 'history'>(activeTab);
  const [searchTerm, setSearchTerm] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState<'ALL' | 'WINS' | 'LOSSES'>('ALL');
  const [directionFilter, setDirectionFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 8;

  const currentTabState = onTabChange ? activeTab : tab;

  const handleTabSwitch = (t: 'running' | 'history') => {
    setTab(t);
    setCurrentPage(1);
    if (onTabChange) {
      onTabChange(t);
    }
  };

  // Filter history based on search, outcome, and direction
  const filteredHistory = useMemo(() => {
    return tradeHistory.filter((item) => {
      // Search filter
      const matchesSearch =
        !searchTerm ||
        item.ticket.toString().includes(searchTerm) ||
        item.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (item.exit_reason && item.exit_reason.toLowerCase().includes(searchTerm.toLowerCase()));

      // Outcome filter
      const matchesOutcome =
        outcomeFilter === 'ALL' ||
        (outcomeFilter === 'WINS' && item.pnl > 0) ||
        (outcomeFilter === 'LOSSES' && item.pnl <= 0);

      // Direction filter
      const matchesDirection =
        directionFilter === 'ALL' ||
        item.direction.toUpperCase().includes(directionFilter);

      return matchesSearch && matchesOutcome && matchesDirection;
    });
  }, [tradeHistory, searchTerm, outcomeFilter, directionFilter]);

  // Aggregate telemetry for the active account
  const accountMetrics = useMemo(() => {
    const total = tradeHistory.length;
    if (total === 0) {
      return { total: 0, wins: 0, losses: 0, winRate: 0, netPnl: 0, totalPips: 0 };
    }
    const wins = tradeHistory.filter((t) => t.pnl > 0).length;
    const losses = tradeHistory.filter((t) => t.pnl <= 0).length;
    const netPnl = tradeHistory.reduce((acc, t) => acc + (t.pnl || 0), 0);
    const totalPips = tradeHistory.reduce((acc, t) => acc + (t.pips || 0), 0);
    const winRate = total > 0 ? (wins / total) * 100 : 0;

    return { total, wins, losses, winRate, netPnl, totalPips };
  }, [tradeHistory]);

  const totalPages = Math.ceil(filteredHistory.length / pageSize) || 1;
  const paginatedHistory = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredHistory.slice(start, start + pageSize);
  }, [filteredHistory, currentPage, pageSize]);

  return (
    <div className="flex flex-col gap-3 pt-4 border-t border-slate-100">
      {/* 1. Header Toolbar: Mode Toggle + Database Status + Account Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Toggle between Running Trades and Trade History */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100 border border-slate-200">
          <button
            onClick={() => handleTabSwitch('running')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              currentTabState === 'running'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-accent-green" />
            <span>Running Trades</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
              runningTrades.length > 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
            }`}>
              {runningTrades.length}
            </span>
          </button>

          <button
            onClick={() => handleTabSwitch('history')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              currentTabState === 'history'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            <History className="w-3.5 h-3.5 text-accent-purple" />
            <span>Trade History</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-slate-200 text-slate-700">
              {tradeHistory.length}
            </span>
          </button>
        </div>

        {/* Database Connection Pill & Account Info */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-[11px] font-mono font-medium">
            <Database className="w-3 h-3 text-emerald-600" />
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>SQLite Connected: {tradeHistory.length} Records</span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 border border-slate-200 text-slate-700 text-[11px] font-mono font-bold">
            <Wallet className="w-3 h-3 text-slate-500" />
            <span>Account: {activeAccount}</span>
          </div>
        </div>
      </div>

      {/* 2. RUNNING TRADES VIEW */}
      {currentTabState === 'running' && (
        <div className="space-y-3">
          {runningTrades.length > 0 ? (
            <div className="w-full overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-slate-400 font-semibold border-b border-slate-100 pb-2">
                    <th className="pb-2.5 font-medium">Symbol & Ticket</th>
                    <th className="pb-2.5 font-medium">Order Type & Lots</th>
                    <th className="pb-2.5 font-medium">Execution Levels</th>
                    <th className="pb-2.5 font-medium text-right pr-6">Floating P&L</th>
                    <th className="pb-2.5 w-6"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {runningTrades.map((pos) => {
                    const isBuy = pos.type?.toUpperCase().includes('BUY');
                    const isProfitable = pos.profit >= 0;
                    return (
                      <tr key={pos.ticket} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3">
                          <div className="flex items-center gap-2.5">
                            <div className="w-7 h-7 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-xs shadow-sm font-mono">
                              CA
                            </div>
                            <div>
                              <div className="font-bold text-slate-800">{pos.symbol}</div>
                              <div className="text-[11px] text-slate-400 font-mono">
                                Ticket: {pos.ticket} • Acc: {activeAccount}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3">
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                              isBuy ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}>
                              {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                              {pos.type}
                            </span>
                            <span className="font-mono text-slate-700 font-medium">{pos.lots?.toFixed(2)} Lots</span>
                          </div>
                        </td>
                        <td className="py-3">
                          <div>
                            <div className="font-bold text-slate-800 font-mono">
                              Open: {pos.open_price?.toFixed(5)}
                            </div>
                            <div className="text-[11px] text-slate-400 font-mono">
                              SL: {pos.stop_loss ? pos.stop_loss.toFixed(5) : '-'} • TP: {pos.take_profit ? pos.take_profit.toFixed(5) : '-'}
                            </div>
                          </div>
                        </td>
                        <td className="py-3 text-right pr-6">
                          <div className={`inline-flex items-center gap-1 font-mono font-bold ${isProfitable ? 'text-emerald-600' : 'text-rose-600'}`}>
                            <span>{isProfitable ? '+' : ''}${pos.profit.toFixed(2)} USD</span>
                            {isProfitable ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                          </div>
                        </td>
                        <td className="py-3 text-right">
                          <button className="text-slate-400 hover:text-slate-700 p-1" title="Order details">
                            <MoreVertical className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            /* Real-time Standby State for Running Trades */
            <div className="py-8 px-4 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col items-center text-center justify-center space-y-2">
              <div className="w-10 h-10 rounded-full bg-emerald-100 border border-emerald-200 flex items-center justify-center text-emerald-600 shadow-sm animate-pulse">
                <Activity className="w-5 h-5" />
              </div>
              <div className="text-sm font-bold text-slate-800">
                No Active Trades Currently Running
              </div>
              <p className="text-xs text-slate-500 max-w-md">
                Ak Trading System is actively scanning USDCADm M5/M15 liquidity sweeps. When sweep criteria are validated by the C1 algorithm, orders will dispatch and display here automatically.
              </p>
              <div className="flex items-center gap-3 pt-2 text-[11px] font-mono text-slate-400">
                <span>Pair: USDCADm</span>
                <span>•</span>
                <span>Bid: {currentBid.toFixed(5)}</span>
                <span>•</span>
                <span>Ask: {currentAsk.toFixed(5)}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3. TRADE HISTORY VIEW */}
      {currentTabState === 'history' && (
        <div className="space-y-4">
          {/* Account Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col">
              <span className="text-[11px] text-slate-500 font-medium flex items-center gap-1">
                <Layers className="w-3 h-3 text-slate-400" />
                Total Closed Trades
              </span>
              <span className="text-lg font-extrabold text-slate-900 font-mono mt-0.5">
                {accountMetrics.total}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col">
              <span className="text-[11px] text-slate-500 font-medium flex items-center gap-1">
                <Award className="w-3 h-3 text-amber-500" />
                Win Rate
              </span>
              <div className="flex items-baseline gap-1.5 mt-0.5">
                <span className="text-lg font-extrabold text-emerald-600 font-mono">
                  {accountMetrics.winRate.toFixed(1)}%
                </span>
                <span className="text-[10px] text-slate-400 font-mono">
                  ({accountMetrics.wins}W / {accountMetrics.losses}L)
                </span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col">
              <span className="text-[11px] text-slate-500 font-medium flex items-center gap-1">
                <TrendingUp className="w-3 h-3 text-emerald-500" />
                Realized P&L
              </span>
              <span className={`text-lg font-extrabold font-mono mt-0.5 ${
                accountMetrics.netPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'
              }`}>
                {accountMetrics.netPnl >= 0 ? '+' : ''}${accountMetrics.netPnl.toFixed(2)} USD
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col">
              <span className="text-[11px] text-slate-500 font-medium flex items-center gap-1">
                <Clock className="w-3 h-3 text-indigo-500" />
                Net Gain Pips
              </span>
              <span className={`text-lg font-extrabold font-mono mt-0.5 ${
                accountMetrics.totalPips >= 0 ? 'text-indigo-600' : 'text-rose-600'
              }`}>
                {accountMetrics.totalPips >= 0 ? '+' : ''}{accountMetrics.totalPips.toFixed(1)} pips
              </span>
            </div>
          </div>

          {/* Search & Filter Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 bg-slate-50/80 p-2 rounded-xl border border-slate-200">
            {/* Search Input */}
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder="Search ticket or reason..."
                className="w-full bg-white border border-slate-200 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 font-mono outline-none focus:border-slate-400"
              />
            </div>

            {/* Filter Pills */}
            <div className="flex items-center gap-1.5 text-xs">
              <div className="flex items-center rounded-lg bg-white border border-slate-200 p-0.5 font-medium">
                {(['ALL', 'WINS', 'LOSSES'] as const).map((o) => (
                  <button
                    key={o}
                    onClick={() => {
                      setOutcomeFilter(o);
                      setCurrentPage(1);
                    }}
                    className={`px-2 py-1 rounded text-[11px] font-bold transition-all cursor-pointer ${
                      outcomeFilter === o
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    {o}
                  </button>
                ))}
              </div>

              <div className="flex items-center rounded-lg bg-white border border-slate-200 p-0.5 font-medium">
                {(['ALL', 'BUY', 'SELL'] as const).map((d) => (
                  <button
                    key={d}
                    onClick={() => {
                      setDirectionFilter(d);
                      setCurrentPage(1);
                    }}
                    className={`px-2 py-1 rounded text-[11px] font-bold transition-all cursor-pointer ${
                      directionFilter === d
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Trade History Table */}
          <div className="w-full overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-slate-400 font-semibold border-b border-slate-100 pb-2">
                  <th className="pb-2.5 font-medium">Ticket & Symbol</th>
                  <th className="pb-2.5 font-medium">Direction & Lots</th>
                  <th className="pb-2.5 font-medium">Open & Close Levels</th>
                  <th className="pb-2.5 font-medium">Reason</th>
                  <th className="pb-2.5 font-medium text-right pr-4">Realized P&L</th>
                  <th className="pb-2.5 font-medium text-right pr-2">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {paginatedHistory.length > 0 ? (
                  paginatedHistory.map((item) => {
                    const isBuy = item.direction?.toUpperCase().includes('BUY');
                    const isWin = item.pnl > 0;
                    return (
                      <tr key={item.ticket} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-2.5">
                          <div>
                            <div className="font-bold text-slate-800">{item.symbol}</div>
                            <div className="text-[11px] text-slate-400 font-mono">
                              Ticket: {item.ticket} • Acc: {item.account_number || activeAccount}
                            </div>
                          </div>
                        </td>
                        <td className="py-2.5">
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
                              isBuy ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                            }`}>
                              {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                              {item.direction}
                            </span>
                            <span className="font-mono text-slate-700 font-medium">
                              {item.lots?.toFixed(2)} Lots
                            </span>
                          </div>
                        </td>
                        <td className="py-2.5">
                          <div>
                            <div className="font-mono text-slate-800 font-medium">
                              {item.entry_price?.toFixed(5)} &rarr; {item.close_price ? item.close_price.toFixed(5) : '-'}
                            </div>
                            <div className="text-[11px] text-slate-400 font-mono">
                              SL: {item.sl_price?.toFixed(5)} • TP: {item.tp_price?.toFixed(5)}
                            </div>
                          </div>
                        </td>
                        <td className="py-2.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                            item.exit_reason === 'TP'
                              ? 'bg-emerald-100 text-emerald-800'
                              : item.exit_reason === 'SL'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}>
                            {item.exit_reason || 'CLOSED'}
                          </span>
                        </td>
                        <td className="py-2.5 text-right pr-4">
                          <div>
                            <div className={`font-mono font-bold ${isWin ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {isWin ? '+' : ''}${item.pnl.toFixed(2)} USD
                            </div>
                            {item.pips !== undefined && (
                              <div className="text-[11px] font-mono text-slate-400">
                                {item.pips >= 0 ? '+' : ''}{item.pips.toFixed(1)} pips
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="py-2.5 text-right pr-2 text-slate-400 font-mono text-[11px]">
                          {item.created_at ? item.created_at.replace('T', ' ').slice(0, 16) : '-'}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-400 text-xs">
                      No matching trade records found for Account {activeAccount}.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
              <span className="text-slate-400 font-mono">
                Showing {((currentPage - 1) * pageSize) + 1} – {Math.min(currentPage * pageSize, filteredHistory.length)} of {filteredHistory.length} trades
              </span>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
                  title="Previous Page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="px-2 font-mono text-slate-700 font-bold">
                  {currentPage} / {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
                  title="Next Page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
