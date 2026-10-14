'use client';

import React, { useState, useEffect } from 'react';
import { Header } from '../components/Header';
import { TradingViewChart } from '../components/TradingViewChart';
import { AccountSwapCard } from '../components/AccountSwapCard';
import { LeadersRiskCard } from '../components/LeadersRiskCard';
import { SettingsModal } from '../components/SettingsModal';
import { AccountConnectModal } from '../components/AccountConnectModal';
import { IntroSplash } from '../components/IntroSplash';
import { AuthScreen } from '../components/AuthScreen';
import { useTradingStream } from '../hooks/useTradingStream';
import { UserAccount } from '../types/trading';
import { api } from '../lib/api';
import { Bell } from 'lucide-react';

const defaultSeedAccounts: UserAccount[] = [
  {
    id: 'acc-1',
    account_number: '70704655',
    broker: 'Exness Technologies Ltd',
    server: 'Exness-Trial9',
    name: 'RawSpread (Exness-Trial9)',
    currency: 'USD',
    balance: 5000.00,
    equity: 5000.00,
    leverage: 2000,
    is_active: true,
  },
];

export default function TradingDeskPage() {
  const {
    account,
    status,
    candles,
    settings,
    closedTrades,
    isConnected,
    systemNotice,
    refreshData,
    loadCandles,
    startBridge,
    stopBridge,
    haltBridge,
    launchMT4,
    updateSettings,
    connectAccount,
  } = useTradingStream();

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isConnectOpen, setIsConnectOpen] = useState(false);
  const [selectedTf, setSelectedTf] = useState('4h');
  const [activeNavTab, setActiveNavTab] = useState('Overview');
  const [activeLedgerTab, setActiveLedgerTab] = useState<'running' | 'history'>('running');

  // Multi-account portfolio state
  const [accountsList, setAccountsList] = useState<UserAccount[]>(defaultSeedAccounts);

  // Authentication & Intro logo splash state
  const [user, setUser] = useState<{ email: string; name: string } | null>(null);
  const [showSplash, setShowSplash] = useState(true);
  const [isAuthLoaded, setIsAuthLoaded] = useState(false);

  useEffect(() => {
    try {
      const storedAuth = localStorage.getItem('ak_trading_auth_user');
      if (storedAuth) {
        const parsed = JSON.parse(storedAuth);
        if (parsed && parsed.email) {
          setUser(parsed);
          setShowSplash(false);
        }
      }
      const storedAccounts = localStorage.getItem('ak_user_accounts');
      if (storedAccounts) {
        const parsedAccs = JSON.parse(storedAccounts);
        if (Array.isArray(parsedAccs) && parsedAccs.length > 0) {
          const cleaned = parsedAccs.filter((a: UserAccount) => a.id !== 'acc-2');
          setAccountsList(cleaned.length > 0 ? cleaned : defaultSeedAccounts);
        }
      }
    } catch (e) {
      console.warn('Failed reading state from localStorage:', e);
    } finally {
      setIsAuthLoaded(true);
    }

    // Dynamically load unlimited accounts from backend SQLite database
    api.getAccounts()
      .then((dbAccs) => {
        if (Array.isArray(dbAccs) && dbAccs.length > 0) {
          setAccountsList(dbAccs);
          try {
            localStorage.setItem('ak_user_accounts', JSON.stringify(dbAccs));
            const active = dbAccs.find((a) => a.is_active);
            if (active) {
              localStorage.setItem('ak_connected_mt4_account', JSON.stringify(active));
            }
          } catch {}
        }
      })
      .catch((err) => {
        console.warn('Could not load accounts from SQLite API (using cached/fallback):', err);
      });
  }, []);

  // Synchronize live account metrics when bridge connects
  useEffect(() => {
    if (account && account.account_number) {
      const accNumStr = String(account.account_number);
      setAccountsList((prev) => {
        const exists = prev.some((a) => String(a.account_number) === accNumStr);
        if (exists) {
          return prev.map((a) => {
            if (String(a.account_number) === accNumStr) {
              return {
                ...a,
                broker: account.company || a.broker,
                balance: account.balance > 0 ? account.balance : a.balance,
                equity: account.equity > 0 ? account.equity : a.equity,
                leverage: account.leverage || a.leverage,
                is_active: true,
              };
            }
            return { ...a, is_active: false };
          });
        } else {
          const liveAcc: UserAccount = {
            id: 'acc-live',
            account_number: accNumStr,
            broker: account.company || 'Exness Technologies Ltd',
            server: account.company || 'Exness-Trial9',
            name: `${account.account_name || 'Standard'} (${account.company || 'Exness'})`,
            currency: account.currency || 'USD',
            balance: account.balance || 5000.0,
            equity: account.equity || 5000.0,
            leverage: account.leverage || 2000,
            is_active: true,
          };
          return [liveAcc, ...prev.map((a) => ({ ...a, is_active: false }))];
        }
      });
    }
  }, [account]);

  const activeAccount = accountsList.find((a) => a.is_active) || accountsList[0] || defaultSeedAccounts[0];

  const handleSelectAccount = async (selected: UserAccount) => {
    const updatedList = accountsList.map((a) => ({
      ...a,
      is_active: a.account_number === selected.account_number,
    }));
    setAccountsList(updatedList);
    try {
      localStorage.setItem('ak_user_accounts', JSON.stringify(updatedList));
      localStorage.setItem('ak_connected_mt4_account', JSON.stringify(selected));
    } catch {
      // LocalStorage fallback
    }

    try {
      await api.switchAccount(selected.account_number);
    } catch (e) {
      console.warn('Failed to switch active account in database:', e);
    }

    try {
      await connectAccount({
        account_number: selected.account_number,
        server: selected.server,
        broker: selected.broker,
        balance: selected.balance,
        leverage: selected.leverage,
      });
    } catch (e) {
      console.warn('Failed to switch MT4 account on backend:', e);
    }
    await refreshData(selected.account_number);
  };

  const handleAccountAdded = (newAcc: UserAccount) => {
    const updatedList = [
      ...accountsList.map((a) => ({ ...a, is_active: false })),
      { ...newAcc, is_active: true },
    ];
    setAccountsList(updatedList);
    try {
      localStorage.setItem('ak_user_accounts', JSON.stringify(updatedList));
      localStorage.setItem('ak_connected_mt4_account', JSON.stringify(newAcc));
    } catch {
      // Storage fallback
    }
    refreshData(newAcc.account_number);
  };

  const handleDeleteAccount = async (accId: string) => {
    try {
      await api.deleteAccount(accId);
    } catch (e) {
      console.warn('Failed to delete account on backend:', e);
    }
    const updatedList = accountsList.filter((a) => a.id !== accId);
    if (updatedList.length > 0 && !updatedList.some((a) => a.is_active)) {
      updatedList[0].is_active = true;
      try {
        await api.switchAccount(updatedList[0].account_number);
      } catch (e) {
        console.warn('Failed to switch to fallback account in database:', e);
      }
    }
    setAccountsList(updatedList);
    try {
      localStorage.setItem('ak_user_accounts', JSON.stringify(updatedList));
    } catch {
      // Storage fallback
    }
  };

  const handleLogout = () => {
    try {
      localStorage.removeItem('ak_trading_auth_user');
    } catch {
      // Storage fallback
    }
    setUser(null);
    setShowSplash(false);
  };

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

  // Render gate: wait for localStorage read
  if (!isAuthLoaded) {
    return (
      <div className="min-h-screen bg-desktop-aura flex items-center justify-center">
        <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-white/10 animate-pulse" />
      </div>
    );
  }

  // 1. Initial Logo Animation Splash Screen
  if (showSplash) {
    return <IntroSplash onComplete={() => setShowSplash(false)} />;
  }

  // 2. Authentication Screen (Gmail & Password)
  if (!user) {
    return <AuthScreen onLogin={(loggedInUser) => setUser(loggedInUser)} />;
  }

  // 3. Ak Trading System Main Trading Desk
  return (
    <div className="min-h-screen bg-desktop-aura text-slate-100 flex flex-col items-center justify-start p-2 sm:p-3 md:p-4 2xl:p-6 font-sans selection:bg-accent-lime selection:text-black">
      {/* Institutional Quant Trading Desktop Shell */}
      <div className="w-full max-w-[2560px] mx-auto bg-window-shell rounded-[24px] border border-white/10 shadow-2xl overflow-hidden flex flex-col backdrop-blur-2xl flex-1">
        {/* Top Window Navigation & Traffic Lights Bar */}
        <Header
          status={status}
          isConnected={isConnected}
          activeTab={activeNavTab}
          user={user}
          accountsList={accountsList}
          activeAccount={activeAccount}
          onSelectAccount={handleSelectAccount}
          onLogout={handleLogout}
          onTabChange={(tab) => {
            setActiveNavTab(tab);
            if (tab === 'Settings') setIsSettingsOpen(true);
            if (tab === 'Positions') {
              setActiveLedgerTab('running');
            }
            if (tab === 'History') {
              setActiveLedgerTab('history');
            }
          }}
          onStartBridge={async () => {
            await startBridge();
            await refreshData(activeAccount?.account_number);
          }}
          onStopBridge={async () => {
            await stopBridge();
            await refreshData(activeAccount?.account_number);
          }}
          onHaltBridge={async () => {
            await haltBridge();
            await refreshData(activeAccount?.account_number);
          }}
          onLaunchMT4={async () => {
            await launchMT4();
          }}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onOpenConnectAccount={() => setIsConnectOpen(true)}
        />

        {/* Main Window Canvas Body */}
        <div className="p-3 sm:p-4 md:p-5 2xl:p-6 flex flex-col gap-4 2xl:gap-5 flex-1">
          {/* System Notice Toast */}
          {systemNotice && (
            <div className="bg-accent-lime-15 border border-accent-lime-40 text-accent-lime px-4 py-2.5 rounded-2xl text-xs font-mono flex items-center gap-2 shadow-lg animate-in slide-in-from-top-2">
              <Bell className="w-4 h-4 animate-bounce" />
              <span>{systemNotice}</span>
            </div>
          )}

          {/* Institutional Full-Canvas Quant Grid */}
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 2xl:gap-5 items-start w-full">
            {/* Left Primary Cockpit: Tickers + Candlestick Chart + Unified Trade Ledger */}
            <div className="xl:col-span-8 2xl:col-span-9 flex flex-col">
              <TradingViewChart
                candles={candles}
                symbol={settings['TRADING_SYMBOL'] || 'USDCADm'}
                timeframe={selectedTf}
                onTimeframeChange={handleTimeframeChange}
                onSymbolChange={handleSymbolChange}
                bidPrice={account.bid}
                askPrice={account.ask}
                spreadPips={account.spread_pips}
                orders={account.orders || []}
                tradeHistory={closedTrades as any}
                activeAccount={activeAccount?.account_number || account.account_number || '70704655'}
                activeLedgerTab={activeLedgerTab}
                onLedgerTabChange={(tab) => setActiveLedgerTab(tab)}
              />
            </div>

            {/* Right Telemetry Column: Portfolio Accounts + Swap Control + Risk Guardrails */}
            <div className="xl:col-span-4 2xl:col-span-3 flex flex-col gap-4 2xl:gap-5">
              {/* Account Portfolio & Automation Card */}
              <AccountSwapCard
                account={account}
                status={status}
                accountsList={accountsList}
                activeAccountId={activeAccount?.id}
                onSelectAccount={handleSelectAccount}
                onOpenAddAccount={() => setIsConnectOpen(true)}
                onDeleteAccount={handleDeleteAccount}
                onToggleBridge={async () => {
                  if (status.bridge_running) {
                    await stopBridge();
                  } else {
                    await startBridge();
                  }
                  await refreshData(activeAccount?.account_number);
                }}
              />

              {/* Growth Leaders & Risk Telemetry Card */}
              <LeadersRiskCard
                status={status}
                tradesToday={account.trades_today ?? status.orders_today ?? 0}
                maxDailyTrades={maxTrades}
                spreadPips={account.spread_pips ?? 0.0}
                maxSpread={maxSpread}
              />
            </div>
          </div>
        </div>

        {/* Subtle Window Footer */}
        <footer className="px-6 py-3.5 bg-window-bar border-t border-white/5 text-xs text-slate-500 font-mono flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent-lime" />
            <span>Ak Trading System • Institutional MT4 C1 Wick-Swap Terminal</span>
          </div>
          <div className="text-[11px] text-slate-400">
            Connected Account: ID: {activeAccount?.account_number || account.account_number || '70704655'} • Session: 07:00 – 18:00 UTC (USDCAD Dedicated)
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

      {/* MT4 Multi-Account Connect Modal */}
      <AccountConnectModal
        isOpen={isConnectOpen}
        onClose={() => setIsConnectOpen(false)}
        onConnected={() => refreshData(activeAccount?.account_number)}
        onAccountAdded={handleAccountAdded}
      />
    </div>
  );
}
