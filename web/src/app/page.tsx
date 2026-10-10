'use client';

import React, { useState } from 'react';
import { Header } from '../components/Header';
import { TradingViewChart } from '../components/TradingViewChart';
import { AccountSwapCard } from '../components/AccountSwapCard';
import { LeadersRiskCard } from '../components/LeadersRiskCard';
import { SettingsModal } from '../components/SettingsModal';
import { AccountConnectModal } from '../components/AccountConnectModal';
import { useTradingStream } from '../hooks/useTradingStream';
import { Bell } from 'lucide-react';

export default function TradingDeskPage() {
  const {
    account,
    status,
    candles,
    settings,
    isConnected,
    systemNotice,
    refreshData,
    loadCandles,
    startBridge,
    stopBridge,
    haltBridge,
    launchMT4,
    updateSettings,
  } = useTradingStream();

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isConnectOpen, setIsConnectOpen] = useState(false);
  const [selectedTf, setSelectedTf] = useState('4h');
  const [activeNavTab, setActiveNavTab] = useState('Overview');

  const handleTimeframeChange = (tf: string) => {
    setSelectedTf(tf);
    const sym = settings['TRADING_SYMBOL'] || 'USDCADm';
    loadCandles(sym, tf);
  };

  const handleSymbolChange = (sym: string) => {
    loadCandles(sym, selectedTf);
  };

  const maxTrades = parseInt(settings['MAX_DAILY_TRADES'] || '3', 10);
  const maxSpread = parseFloat(settings['MAX_SPREAD_PIPS'] || '2.5');

  return (
    <div className="min-h-screen bg-desktop-aura text-slate-100 flex items-center justify-center p-2 sm:p-4 md:p-8 font-sans selection:bg-accent-lime selection:text-black">
      {/* Floating macOS Desktop Window Shell */}
      <div className="w-full max-w-[1580px] bg-window-shell rounded-[28px] border border-white/10 shadow-2xl overflow-hidden flex flex-col backdrop-blur-xl">
        {/* Top Window Navigation & Traffic Lights Bar */}
        <Header
          status={status}
          isConnected={isConnected}
          activeTab={activeNavTab}
          onTabChange={(tab) => {
            setActiveNavTab(tab);
            if (tab === 'Settings') setIsSettingsOpen(true);
            if (tab === 'Positions') setIsConnectOpen(true);
          }}
          onStartBridge={async () => {
            await startBridge();
            await refreshData();
          }}
          onStopBridge={async () => {
            await stopBridge();
            await refreshData();
          }}
          onHaltBridge={async () => {
            await haltBridge();
            await refreshData();
          }}
          onLaunchMT4={async () => {
            await launchMT4();
          }}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onOpenConnectAccount={() => setIsConnectOpen(true)}
        />

        {/* Main Window Canvas Body */}
        <div className="p-4 sm:p-5 md:p-6 flex flex-col gap-5">
          {/* System Notice Toast */}
          {systemNotice && (
            <div className="bg-accent-lime-15 border border-accent-lime-40 text-accent-lime px-4 py-2.5 rounded-2xl text-xs font-mono flex items-center gap-2 shadow-lg animate-in slide-in-from-top-2">
              <Bell className="w-4 h-4 animate-bounce" />
              <span>{systemNotice}</span>
            </div>
          )}

          {/* Bi-Tonal Split Grid: Left White Card + Right Dark Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Left Column: White Canvas Card (Tickers + TV Chart + Transactions) */}
            <div className="lg:col-span-8 flex flex-col">
              <TradingViewChart
                candles={candles}
                symbol={settings['TRADING_SYMBOL'] || 'BTC/USDT'}
                timeframe={selectedTf}
                onTimeframeChange={handleTimeframeChange}
                onSymbolChange={handleSymbolChange}
                bidPrice={account.bid}
                askPrice={account.ask}
                spreadPips={account.spread_pips}
                orders={account.orders || []}
              />
            </div>

            {/* Right Column: Dark Cards (Account & Swap + Growth & Risk Status) */}
            <div className="lg:col-span-4 flex flex-col gap-5">
              {/* Account & Swap Card */}
              <AccountSwapCard
                account={account}
                status={status}
                onToggleBridge={async () => {
                  if (status.bridge_running) {
                    await stopBridge();
                  } else {
                    await startBridge();
                  }
                  await refreshData();
                }}
              />

              {/* Growth Leaders & Risk Telemetry Card */}
              <LeadersRiskCard
                status={status}
                tradesToday={account.trades_today || status.orders_today || 1}
                maxDailyTrades={maxTrades}
                spreadPips={account.spread_pips || 1.4}
                maxSpread={maxSpread}
              />
            </div>
          </div>
        </div>

        {/* Subtle Window Footer */}
        <footer className="px-6 py-3.5 bg-window-bar border-t border-white/5 text-xs text-slate-500 font-mono flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent-lime" />
            <span>TrendWise • Institutional Forex & Crypto Quant Terminal</span>
          </div>
          <div className="text-[11px] text-slate-400">
            Session Window: 07:00 – 18:00 UTC (12:00 AM Local Cutoff Active)
          </div>
        </footer>
      </div>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onSave={updateSettings}
      />

      {/* MT4 Account Connect Modal */}
      <AccountConnectModal
        isOpen={isConnectOpen}
        onClose={() => setIsConnectOpen(false)}
        onConnected={refreshData}
      />
    </div>
  );
}
