'use client';

import React, { useState } from 'react';
import {
  CreditCard,
  Copy,
  Check,
  Plus,
  Trash2,
  Cpu,
  ShieldCheck,
  Layers,
  ChevronRight,
  Activity,
  Server
} from 'lucide-react';
import { AccountInfo, BridgeStatus, UserAccount } from '../types/trading';

interface AccountSwapCardProps {
  account: AccountInfo;
  status: BridgeStatus;
  accountsList?: UserAccount[];
  activeAccountId?: string;
  onSelectAccount?: (acc: UserAccount) => void;
  onOpenAddAccount?: () => void;
  onDeleteAccount?: (accId: string) => void;
  onToggleBridge?: () => void;
}

export const AccountSwapCard: React.FC<AccountSwapCardProps> = ({
  account,
  status,
  accountsList = [],
  activeAccountId,
  onSelectAccount,
  onOpenAddAccount,
  onDeleteAccount,
  onToggleBridge,
}) => {
  const [copied, setCopied] = useState(false);

  const activeAcc = accountsList.find((a) => (activeAccountId ? a.id === activeAccountId : a.is_active)) || accountsList[0];
  const activeAccNum = activeAcc ? String(activeAcc.account_number) : String(account.account_number || '69800896');
  const activeBroker = activeAcc?.broker || account.company || 'Exness';
  const displayBalance = (activeAcc?.balance !== undefined && activeAcc.balance > 0)
    ? activeAcc.balance
    : (account.balance > 0 ? account.balance : 0.00);
  const balanceStr = displayBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const displayEquity = (activeAcc?.equity !== undefined && activeAcc.equity > 0)
    ? activeAcc.equity
    : (account.equity > 0 ? account.equity : displayBalance);
  const displayFreeMargin = account.free_margin > 0 ? account.free_margin : displayBalance;
  const activeLeverage = activeAcc?.leverage || account.leverage || 200;

  const handleCopyAccount = () => {
    navigator.clipboard.writeText(activeAccNum);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="w-full bg-window-card text-white rounded-3xl p-6 border border-white/10 shadow-2xl flex flex-col gap-5">
      {/* 1. Header: Account Portfolio + Active Broker Badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-accent-lime" />
          <h3 className="text-base font-bold text-slate-100 tracking-tight">Account Portfolio</h3>
          <span className="px-2 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono text-[11px]">
            {accountsList.length > 0 ? `${accountsList.length} Accounts` : 'Active Desk'}
          </span>
        </div>
        <span className="px-3 py-1 rounded-full bg-accent-lime-15 border border-accent-lime-40 text-accent-lime text-xs font-semibold">
          {activeBroker} Real
        </span>
      </div>

      {/* 2. Active Account Details & Copy Button */}
      <div className="flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-window-card-inset border border-white/5 text-xs text-slate-400">
        <div className="flex items-center gap-2 font-mono truncate">
          <CreditCard className="w-3.5 h-3.5 text-accent-lime flex-shrink-0" />
          <span className="truncate text-white font-bold">
            Account ID: {activeAccNum}
          </span>
          <span className="text-slate-500">•</span>
          <span className="text-slate-400">1:{activeLeverage} Lev</span>
        </div>
        <div className="flex items-center gap-2 text-slate-400 pl-2">
          <button
            onClick={handleCopyAccount}
            className="hover:text-white transition-colors p-1 cursor-pointer"
            title="Copy Account ID"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-accent-lime" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 3. Hero Balance Typography */}
      <div className="flex flex-col">
        <div className="text-[11px] text-slate-400 font-semibold tracking-wider uppercase mb-1">
          Active Account Balance
        </div>
        <div className="flex items-baseline gap-2 font-mono">
          <span className="text-3xl font-extrabold text-white tracking-tight">
            ${balanceStr}
          </span>
          <span className="text-sm font-bold text-slate-400 font-sans">
            USD
          </span>
        </div>
        <div className="text-[11px] text-slate-400 font-mono mt-1.5 flex items-center gap-2.5">
          <span>Eq: ${displayEquity.toFixed(2)}</span>
          <span className="text-slate-600">•</span>
          <span>Free: ${displayFreeMargin.toFixed(2)}</span>
          <span className="text-slate-600">•</span>
          <span>Margin: ${(account.margin || 0).toFixed(2)}</span>
        </div>
      </div>

      {/* 4. Multi-Account Switcher & Management List */}
      <div className="flex flex-col gap-2.5 pt-2 border-t border-white/10">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-300">Connected Accounts</span>
          {onOpenAddAccount && (
            <button
              onClick={onOpenAddAccount}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-accent-lime-15 border border-accent-lime-40 text-accent-lime text-xs font-bold hover:bg-accent-lime hover:text-black transition-all cursor-pointer active:scale-95"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Account</span>
            </button>
          )}
        </div>

        {/* Account Cards Container */}
        <div className="flex flex-col gap-2 max-h-[190px] overflow-y-auto pr-1">
          {accountsList.length > 0 ? (
            accountsList.map((acc) => {
              const isActive = activeAcc ? acc.id === activeAcc.id : String(acc.account_number) === activeAccNum;
              return (
                <div
                  key={acc.id}
                  onClick={() => onSelectAccount && onSelectAccount(acc)}
                  className={`p-3 rounded-2xl border transition-all cursor-pointer flex items-center justify-between ${
                    isActive
                      ? 'bg-window-card-inset border-accent-lime-40 shadow-sm'
                      : 'bg-black/20 border-white/5 hover:bg-white/5 hover:border-white/10'
                  }`}
                >
                  <div className="flex items-center gap-3 truncate">
                    <div className={`w-8 h-8 rounded-xl flex items-center justify-center font-bold text-xs shrink-0 ${
                      isActive ? 'bg-accent-lime text-black font-black' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {acc.broker?.slice(0, 2).toUpperCase() || 'FX'}
                    </div>
                    <div className="truncate">
                      <div className="flex items-center gap-2 truncate">
                        <span className={`text-xs font-bold truncate ${isActive ? 'text-white' : 'text-slate-300'}`}>
                          {acc.name || `Account ${acc.account_number}`}
                        </span>
                        {isActive && (
                          <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-bold bg-accent-lime-15 text-accent-lime border border-accent-lime-40">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] font-mono text-slate-400 flex items-center gap-1.5">
                        <span>ID: {acc.account_number}</span>
                        <span>•</span>
                        <span>{acc.server || 'Exness'}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 pl-2">
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-white">
                        ${(acc.balance ?? 0.00).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </div>
                      <div className="text-[10px] font-mono text-slate-400">
                        1:{acc.leverage || 200}
                      </div>
                    </div>
                    {onDeleteAccount && accountsList.length > 1 && !isActive && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteAccount(acc.id);
                        }}
                        className="text-slate-500 hover:text-rose-400 p-1 transition-colors"
                        title="Remove Account"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="p-3 rounded-2xl bg-black/20 border border-white/5 flex items-center justify-between text-xs text-slate-400">
              <div className="flex items-center gap-2">
                <Server className="w-4 h-4 text-accent-lime" />
                <span>Primary Desk (Account ID: {activeAccNum})</span>
              </div>
              <span className="font-mono text-white font-bold">${balanceStr}</span>
            </div>
          )}
        </div>
      </div>

      {/* 5. Algorithmic Trading Safeguard Banner (Manual execution disabled) */}
      <div className="p-3.5 rounded-2xl bg-window-card-inset border border-white/5 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-accent-lime" />
            <span className="text-xs font-bold text-white">C1 Algorithmic Automation</span>
          </div>
          <span className="px-2 py-0.5 rounded-md bg-accent-lime-15 border border-accent-lime-40 text-[10px] font-mono font-bold text-accent-lime">
            ARMED
          </span>
        </div>

        <div className="text-[11px] text-slate-400 leading-relaxed font-mono">
          <div className="flex items-center justify-between text-slate-300">
            <span>Trading Pair:</span>
            <span className="text-accent-lime font-bold">USDCADm (Dedicated)</span>
          </div>
          <div className="flex items-center justify-between text-slate-300 mt-0.5">
            <span>Strategy Setup:</span>
            <span className="text-white">M5/M15 Wick-Swap</span>
          </div>
          <div className="flex items-center justify-between text-slate-300 mt-0.5">
            <span>Execution Mode:</span>
            <span className="text-accent-cyan font-bold">100% Automated by MT4 Bridge</span>
          </div>
        </div>

        <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-accent-lime" />
            <span>Manual Trading Disabled</span>
          </span>
          <span className="text-slate-500">Zero Intervention Required</span>
        </div>
      </div>

      {/* 6. Bridge Watchdog Status Line */}
      <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono px-1">
        <span className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${status.bridge_running ? 'bg-accent-lime animate-pulse' : 'bg-slate-500'}`} />
          <span>Bridge: {status.bridge_running ? 'C1 Watchdog Active' : 'Standby'}</span>
        </span>
        {onToggleBridge && (
          <button
            onClick={onToggleBridge}
            className="text-slate-400 hover:text-white underline transition-colors cursor-pointer"
          >
            {status.bridge_running ? 'Pause Scanning' : 'Resume'}
          </button>
        )}
      </div>
    </div>
  );
};
