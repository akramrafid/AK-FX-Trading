'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  LayoutGrid,
  Wallet,
  BarChart3,
  Clock,
  HelpCircle,
  Settings as SettingsIcon,
  Play,
  Square,
  Monitor,
  Link2,
  Lock,
  RotateCcw,
  Share2,
  Home,
  LogOut,
  User,
  Check,
  Plus,
} from 'lucide-react';
import { BridgeStatus, UserAccount } from '../types/trading';

interface HeaderProps {
  status: BridgeStatus;
  isConnected: boolean;
  activeTab?: string;
  user?: { email: string; name: string } | null;
  accountsList?: UserAccount[];
  activeAccount?: UserAccount;
  onSelectAccount?: (acc: UserAccount) => void;
  onLogout?: () => void;
  onTabChange?: (tab: string) => void;
  onStartBridge: () => void;
  onStopBridge: () => void;
  onHaltBridge: () => void;
  onLaunchMT4: () => void;
  onOpenSettings: () => void;
  onOpenConnectAccount: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  isConnected,
  activeTab = 'Overview',
  user,
  accountsList = [],
  activeAccount,
  onSelectAccount,
  onLogout,
  onTabChange,
  onStartBridge,
  onStopBridge,
  onHaltBridge,
  onLaunchMT4,
  onOpenSettings,
  onOpenConnectAccount,
}) => {
  const [currentTab, setCurrentTab] = useState(activeTab);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement>(null);

  const activeAccNum = activeAccount?.account_number || '69800896';
  const activeBrokerName = activeAccount?.broker || 'Exness';

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(event.target as Node)) {
        setIsAccountMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const navItems = [
    { label: 'Overview', icon: Home },
    { label: 'Positions', icon: LayoutGrid },
    { label: 'History', icon: Clock },
    { label: 'Strategy (C1)', icon: BarChart3 },
    { label: 'Risk Guardrails', icon: Wallet },
    { label: 'Support', icon: HelpCircle },
    { label: 'Settings', icon: SettingsIcon },
  ];

  const handleTabClick = (label: string) => {
    setCurrentTab(label);
    if (label === 'Settings') {
      onOpenSettings();
    }
    if (onTabChange) {
      onTabChange(label);
    }
  };

  return (
    <div className="w-full flex flex-col bg-window-bar text-slate-200 border-b border-white/5 select-none">
      {/* 1. macOS Style Top Window Bar */}
      <div className="px-5 py-2.5 flex items-center justify-between border-b border-white/5 text-xs text-slate-400">
        {/* Left: macOS Traffic Lights */}
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full bg-traffic-red hover:opacity-80 cursor-pointer shadow-sm" />
          <span className="w-3 h-3 rounded-full bg-traffic-yellow hover:opacity-80 cursor-pointer shadow-sm" />
          <span className="w-3 h-3 rounded-full bg-traffic-green hover:opacity-80 cursor-pointer shadow-sm" />

          {/* Forward / Back Navigation Controls */}
          <div className="hidden sm:flex items-center gap-1.5 ml-4 text-slate-500">
            <button className="hover:text-slate-300 transition-colors px-1" title="Back">&lsaquo;</button>
            <button className="hover:text-slate-300 transition-colors px-1" title="Forward">&rsaquo;</button>
          </div>
        </div>

        {/* Center: Window URL / Status Pill */}
        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-black/40 border border-white/10 text-[11px] font-mono text-slate-400 max-w-md w-full justify-center shadow-inner">
          <Lock className="w-3 h-3 text-accent-green" />
          <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-accent-green' : 'bg-accent-amber animate-pulse'}`} />
          <span className="truncate">ak-trading.internal/terminal • ID: {activeAccNum}</span>
          <RotateCcw className="w-2.5 h-2.5 text-slate-500 ml-1 cursor-pointer hover:text-slate-300" />
        </div>

        {/* Right: Quick Window Action Buttons */}
        <div className="flex items-center gap-2 text-slate-400">
          <button
            onClick={onLaunchMT4}
            className="flex items-center gap-1 text-[11px] font-medium hover:text-white px-2 py-0.5 rounded bg-white/5 border border-white/5 transition-colors cursor-pointer"
            title="Launch MT4 Terminal"
          >
            <Monitor className="w-3 h-3 text-accent-cyan" />
            <span className="hidden md:inline">Launch MT4</span>
          </button>
          <button
            onClick={onOpenConnectAccount}
            className="flex items-center gap-1 text-[11px] font-medium hover:text-white px-2 py-0.5 rounded bg-white/5 border border-white/5 transition-colors cursor-pointer"
            title="Add MT4 Account"
          >
            <Link2 className="w-3 h-3 text-accent-lime" />
            <span className="hidden md:inline">Add MT4</span>
          </button>
          <button className="hover:text-white p-1 cursor-pointer" title="Share Desk">
            <Share2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Main Navigation Header Bar */}
      <div className="px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
        {/* Brand Identity: Ak Trading System */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-lime flex items-center justify-center shadow-md shadow-lime-900/30">
            {/* Custom Geometric AK Monogram Badge */}
            <svg
              className="w-5 h-5 text-black"
              viewBox="0 0 100 100"
              fill="none"
              stroke="currentColor"
              strokeWidth="9"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M 22 78 L 38 22 L 54 78" />
              <path d="M 28 58 L 48 58" />
              <path d="M 58 22 L 58 78" />
              <path d="M 82 24 L 59 50 L 84 78" />
            </svg>
          </div>
          <div className="flex flex-col">
            <span className="text-white font-extrabold text-lg tracking-tight leading-tight">
              Ak Trading System
            </span>
            <span className="text-[10px] text-accent-lime font-mono tracking-wider font-semibold">
              QUANTITATIVE DESK
            </span>
          </div>
        </div>

        {/* Pill Navigation Tabs */}
        <nav className="flex items-center gap-1.5 overflow-x-auto py-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.label;
            return (
              <button
                key={item.label}
                onClick={() => handleTabClick(item.label)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer ${
                  isActive
                    ? 'bg-white/10 text-white border border-white/15 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-accent-lime' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Corner Telemetry: Broker Pill / Account Selector + User Badge + Bridge Button */}
        <div className="flex items-center gap-3">
          {/* Account Selector Dropdown Menu */}
          <div className="relative" ref={accountMenuRef}>
            <button
              onClick={() => setIsAccountMenuOpen(!isAccountMenuOpen)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/40 border border-white/10 text-xs font-medium text-slate-200 shadow-sm cursor-pointer hover:border-white/20 transition-all"
              title="Switch or Add Trading Accounts"
            >
              <span className="w-2.5 h-2.5 rounded-full bg-accent-green flex items-center justify-center">
                <span className="w-1 h-1 rounded-full bg-white" />
              </span>
              <span className="font-semibold text-xs">{activeBrokerName} Real</span>
              <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isAccountMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Floating Multi-Account Dropdown */}
            {isAccountMenuOpen && (
              <div className="absolute right-0 top-full mt-2 w-72 rounded-2xl bg-slate-900/95 border border-white/10 shadow-2xl p-2 z-50 backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150">
                <div className="px-3 py-2 border-b border-white/10 flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-300">Switch Account</span>
                  <span className="text-[10px] font-mono text-slate-500">
                    {accountsList.length} Connected
                  </span>
                </div>

                <div className="flex flex-col gap-1 py-1.5 max-h-56 overflow-y-auto">
                  {accountsList.length > 0 ? (
                    accountsList.map((acc) => {
                      const isActive = String(acc.account_number) === String(activeAccNum);
                      return (
                        <button
                          key={acc.id}
                          onClick={() => {
                            if (onSelectAccount) onSelectAccount(acc);
                            setIsAccountMenuOpen(false);
                          }}
                          className={`w-full p-2.5 rounded-xl text-left flex items-center justify-between transition-all cursor-pointer ${
                            isActive
                              ? 'bg-white/10 border border-accent-lime-40 text-white'
                              : 'hover:bg-white/5 border border-transparent text-slate-300'
                          }`}
                        >
                          <div className="flex items-center gap-2.5 truncate">
                            <div className={`w-7 h-7 rounded-lg flex items-center justify-center font-bold text-[10px] shrink-0 ${
                              isActive ? 'bg-accent-lime text-black font-black' : 'bg-slate-800 text-slate-400'
                            }`}>
                              {acc.broker?.slice(0, 2).toUpperCase() || 'FX'}
                            </div>
                            <div className="truncate">
                              <div className="text-xs font-bold truncate">
                                {acc.name || `${acc.broker} Account`}
                              </div>
                              <div className="text-[10px] font-mono text-slate-400">
                                ID: {acc.account_number} • {acc.server || 'Real'}
                              </div>
                            </div>
                          </div>

                          {isActive && (
                            <Check className="w-4 h-4 text-accent-lime shrink-0 ml-2" />
                          )}
                        </button>
                      );
                    })
                  ) : (
                    <div className="px-3 py-2 text-xs text-slate-400">
                      ID: {activeAccNum} (Default Desk)
                    </div>
                  )}
                </div>

                <div className="pt-1.5 border-t border-white/10">
                  <button
                    onClick={() => {
                      setIsAccountMenuOpen(false);
                      onOpenConnectAccount();
                    }}
                    className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-accent-lime-15 border border-accent-lime-40 text-accent-lime text-xs font-bold hover:bg-accent-lime hover:text-black transition-all cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add New MT4 Account</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* User Account & Profile with Logout */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-black/40 border border-white/10">
            <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-emerald-500 to-accent-lime flex items-center justify-center text-[10px] font-black text-black shadow-sm ring-1 ring-white/20">
              AK
            </div>
            <div className="flex flex-col">
              <span className="text-[11px] font-mono font-bold text-white tracking-tight leading-none">
                {user ? user.email.split('@')[0] : `ID: ${activeAccNum}`}
              </span>
              {user && (
                <span className="text-[9px] text-slate-400 font-mono leading-none truncate max-w-[90px]">
                  {user.email}
                </span>
              )}
            </div>

            {/* Logout Action Button */}
            {onLogout && (
              <button
                onClick={onLogout}
                className="ml-1 p-1 rounded-full text-slate-400 hover:text-accent-red hover:bg-white/10 transition-colors cursor-pointer"
                title="Log out from Ak Trading System"
              >
                <LogOut className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Bridge Control Indicator Pill */}
          {status.bridge_running ? (
            <button
              onClick={onStopBridge}
              className="px-2.5 py-1 rounded-full bg-accent-red-15 border border-accent-red-40 text-accent-red text-xs font-bold hover:bg-rose-950/40 transition-all flex items-center gap-1.5 cursor-pointer"
              title="Stop Bridge Execution"
            >
              <Square className="w-2.5 h-2.5 fill-current" />
              <span>STOP</span>
            </button>
          ) : (
            <button
              onClick={onStartBridge}
              className="px-2.5 py-1 rounded-full bg-accent-lime-15 border border-accent-lime-40 text-accent-lime text-xs font-bold hover:bg-lime-950/40 transition-all flex items-center gap-1.5 cursor-pointer"
              title="Start Bridge Execution"
            >
              <Play className="w-2.5 h-2.5 fill-current" />
              <span>LIVE</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
