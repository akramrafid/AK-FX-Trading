'use client';

import React, { useState } from 'react';
import {
  ChevronDown,
  LayoutGrid,
  Wallet,
  BarChart3,
  Clock,
  HelpCircle,
  Settings as SettingsIcon,
  Copy,
  Check,
  Play,
  Square,
  AlertOctagon,
  Monitor,
  Link2,
  Lock,
  RotateCcw,
  Share2,
  Home
} from 'lucide-react';
import { BridgeStatus } from '../types/trading';

interface HeaderProps {
  status: BridgeStatus;
  isConnected: boolean;
  activeTab?: string;
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
  onTabChange,
  onStartBridge,
  onStopBridge,
  onHaltBridge,
  onLaunchMT4,
  onOpenSettings,
  onOpenConnectAccount,
}) => {
  const [currentTab, setCurrentTab] = useState(activeTab);
  const [copied, setCopied] = useState(false);

  const navItems = [
    { label: 'Overview', icon: Home },
    { label: 'Positions', icon: LayoutGrid },
    { label: 'Wallet', icon: Wallet },
    { label: 'Analytics', icon: BarChart3 },
    { label: 'History', icon: Clock },
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
          <Lock className="w-3 h-3 text-slate-400" />
          <span className="truncate">talentsync.com/dashboard</span>
          <RotateCcw className="w-2.5 h-2.5 text-slate-500 ml-1 cursor-pointer hover:text-slate-300" />
        </div>

        {/* Right: Quick Window Action Buttons */}
        <div className="flex items-center gap-2 text-slate-400">
          <button
            onClick={onLaunchMT4}
            className="flex items-center gap-1 text-[11px] font-medium hover:text-white px-2 py-0.5 rounded bg-white/5 border border-white/5 transition-colors"
            title="Launch MT4 Terminal"
          >
            <Monitor className="w-3 h-3 text-accent-cyan" />
            <span className="hidden md:inline">Launch MT4</span>
          </button>
          <button
            onClick={onOpenConnectAccount}
            className="flex items-center gap-1 text-[11px] font-medium hover:text-white px-2 py-0.5 rounded bg-white/5 border border-white/5 transition-colors"
            title="Connect Account"
          >
            <Link2 className="w-3 h-3 text-accent-lime" />
            <span className="hidden md:inline">Connect</span>
          </button>
          <button className="hover:text-white p-1" title="Share">
            <Share2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Main Navigation Header Bar */}
      <div className="px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
        {/* Brand Identity */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent-lime flex items-center justify-center shadow-md shadow-lime-900/30">
            {/* Custom TrendWise Curved Umbrella / Growth Icon */}
            <svg className="w-5 h-5 text-black" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3c-4.97 0-9 4.03-9 9 0 .8.1 1.58.29 2.33A2 2 0 0 0 5.25 16h13.5a2 2 0 0 0 1.96-1.67c.19-.75.29-1.53.29-2.33 0-4.97-4.03-9-9-9z" />
              <path d="M12 16v5" />
            </svg>
          </div>
          <span className="text-white font-bold text-lg tracking-tight">
            TrendWise
          </span>
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
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium transition-all ${
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

        {/* Right Corner Telemetry: Network Pill + User Badge */}
        <div className="flex items-center gap-3">
          {/* Ethereum / Broker Selector Pill */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/40 border border-white/10 text-xs font-medium text-slate-200 shadow-sm">
            <span className="w-2.5 h-2.5 rounded-full bg-token-eth flex items-center justify-center">
              <span className="w-1 h-1 rounded-full bg-white" />
            </span>
            <span className="font-semibold text-xs">Ethereum</span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </div>

          {/* Avatar & Balance Badge */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-black/40 border border-white/10">
            <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-purple-500 to-indigo-600 flex items-center justify-center text-[10px] font-bold text-white shadow-sm ring-1 ring-white/20">
              AK
            </div>
            <span className="text-xs font-mono font-bold text-white tracking-tight">
              178 ETH
            </span>
          </div>

          {/* Bridge Control Indicator Pill */}
          {status.bridge_running ? (
            <button
              onClick={onStopBridge}
              className="px-2.5 py-1 rounded-full bg-accent-red-15 border border-accent-red-40 text-accent-red text-xs font-bold hover:bg-rose-950/40 transition-all flex items-center gap-1.5"
              title="Stop Bridge Execution"
            >
              <Square className="w-2.5 h-2.5 fill-current" />
              <span>STOP</span>
            </button>
          ) : (
            <button
              onClick={onStartBridge}
              className="px-2.5 py-1 rounded-full bg-accent-lime-15 border border-accent-lime-40 text-accent-lime text-xs font-bold hover:bg-lime-950/40 transition-all flex items-center gap-1.5"
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
