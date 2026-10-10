'use client';

import React, { useState } from 'react';
import {
  CreditCard,
  Copy,
  Check,
  Share2,
  ArrowUpDown,
  ChevronDown,
  Zap,
  Play,
  Square
} from 'lucide-react';
import { AccountInfo, BridgeStatus } from '../types/trading';

interface AccountSwapCardProps {
  account: AccountInfo;
  status: BridgeStatus;
  onExecuteTrade?: (amount: number, symbol: string) => void;
  onToggleBridge?: () => void;
}

export const AccountSwapCard: React.FC<AccountSwapCardProps> = ({
  account,
  status,
  onExecuteTrade,
  onToggleBridge,
}) => {
  const [sendAmount, setSendAmount] = useState('15,000.00');
  const [receiveAmount, setReceiveAmount] = useState('5.061349');
  const [selectedCurrency, setSelectedCurrency] = useState('ETH');
  const [copied, setCopied] = useState(false);

  const displayBalance = account.balance > 0 ? account.balance : 19964.50;
  const balanceStr = displayBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const handleCopyHash = () => {
    navigator.clipboard.writeText('Kgl2rQ49ajOia8849las51');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSwapValues = () => {
    const temp = sendAmount;
    setSendAmount(receiveAmount);
    setReceiveAmount(temp);
  };

  const handleMaxClick = () => {
    setSendAmount(balanceStr);
  };

  return (
    <div className="w-full bg-window-card text-white rounded-3xl p-6 border border-white/10 shadow-2xl flex flex-col gap-5">
      {/* 1. Header: "Account" + "Free Plan" pill */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-slate-100 tracking-tight">Account</h3>
        <span className="px-3 py-1 rounded-full bg-accent-lime-15 border border-accent-lime-40 text-accent-lime text-xs font-semibold">
          Free Plan
        </span>
      </div>

      {/* 2. Account ID & Wallet Pill */}
      <div className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-window-card-inset border border-white/5 text-xs text-slate-400">
        <div className="flex items-center gap-2 font-mono truncate">
          <CreditCard className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
          <span className="truncate">Kgl2rQ49ajOia...las51</span>
        </div>
        <div className="flex items-center gap-2 text-slate-400 pl-2">
          <button
            onClick={handleCopyHash}
            className="hover:text-white transition-colors p-1"
            title="Copy account hash"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-accent-lime" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
          <button className="hover:text-white transition-colors p-1" title="Share">
            <Share2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 3. Hero Balance Typography */}
      <div className="flex flex-col">
        <div className="flex items-baseline gap-2 font-mono">
          <span className="text-3xl font-extrabold text-white tracking-tight">
            {balanceStr}
          </span>
          <span className="text-sm font-bold text-slate-400 font-sans">
            USD
          </span>
        </div>
      </div>

      {/* 4. Interactive Quick Swap / Order Box */}
      <div className="relative flex flex-col gap-2 pt-1">
        {/* Box 1: You Send */}
        <div className="p-3.5 rounded-2xl bg-window-card-inset border border-white/5 flex flex-col gap-1.5 focus-within:border-accent-cyan-40 transition-all">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>You Send</span>
            <button
              onClick={handleMaxClick}
              className="font-mono text-slate-400 hover:text-accent-cyan text-[11px] transition-colors"
            >
              {balanceStr} max
            </button>
          </div>
          <div className="flex items-center justify-between font-mono">
            <div className="flex items-center text-lg font-bold text-white">
              <span>$</span>
              <input
                type="text"
                value={sendAmount}
                onChange={(e) => setSendAmount(e.target.value)}
                className="bg-transparent border-none outline-none font-mono text-lg font-bold text-white w-full ml-1"
              />
            </div>
          </div>
        </div>

        {/* Center Floating Swap Button */}
        <div className="absolute top-[48%] left-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
          <button
            onClick={handleSwapValues}
            className="w-10 h-10 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg flex items-center justify-center transition-transform active:scale-90 ring-4 ring-window-card"
            title="Swap currencies"
          >
            <ArrowUpDown className="w-4 h-4" />
          </button>
        </div>

        {/* Box 2: You Receive */}
        <div className="p-3.5 rounded-2xl bg-window-card-inset border border-white/5 flex flex-col gap-1.5 focus-within:border-accent-cyan-40 transition-all">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>You Receive</span>
          </div>
          <div className="flex items-center justify-between">
            <input
              type="text"
              value={receiveAmount}
              onChange={(e) => setReceiveAmount(e.target.value)}
              className="bg-transparent border-none outline-none font-mono text-lg font-bold text-white w-2/3"
            />
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-semibold cursor-pointer hover:bg-white/10 transition-colors">
              <span>{selectedCurrency}</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </div>
          </div>
        </div>
      </div>

      {/* 5. Signature Neon Lime Action Button */}
      <button
        onClick={() => {
          if (onToggleBridge) onToggleBridge();
        }}
        className="w-full py-3.5 rounded-2xl bg-accent-lime hover:brightness-105 active:scale-[0.98] text-black font-extrabold text-sm tracking-wide shadow-lg shadow-lime-900/20 transition-all flex items-center justify-center gap-2 mt-1 cursor-pointer"
      >
        <Zap className="w-4 h-4 fill-current" />
        <span>Swap Now</span>
      </button>
    </div>
  );
};
