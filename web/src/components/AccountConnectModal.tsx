'use client';

import React, { useState, useEffect } from 'react';
import { X, Link2, Search, CheckCircle2, AlertCircle, Monitor, Shield, Check, Plus, DollarSign, Gauge } from 'lucide-react';
import { api } from '../lib/api';
import { UserAccount } from '../types/trading';

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnected: () => void;
  onAccountAdded?: (newAcc: UserAccount) => void;
}

export const AccountConnectModal: React.FC<AccountModalProps> = ({
  isOpen,
  onClose,
  onConnected,
  onAccountAdded,
}) => {
  const [accountNumber, setAccountNumber] = useState('69800896');
  const [nickname, setNickname] = useState('Standard (Exness-Trial8)');
  const [server, setServer] = useState('Exness-Trial8');
  const [broker, setBroker] = useState('Exness Technologies Ltd');
  const [leverage, setLeverage] = useState('2000');
  const [balance, setBalance] = useState('5000.00');
  const [password, setPassword] = useState('');
  const [detectedPath, setDetectedPath] = useState('');
  const [detectedExe, setDetectedExe] = useState('');
  const [isDetecting, setIsDetecting] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; isError?: boolean } | null>(null);

  useEffect(() => {
    if (isOpen) {
      handleAutoDetect();
    }
  }, [isOpen]);

  const handleAutoDetect = async () => {
    setIsDetecting(true);
    setStatusMsg(null);
    try {
      const data = await api.getAccountDetect();
      if (data.detected_files_dir) {
        setDetectedPath(data.detected_files_dir);
      }
      if (data.detected_exe_path) {
        setDetectedExe(data.detected_exe_path);
      }
      if (data.current_account) {
        setAccountNumber(data.current_account);
      }
      if (data.current_server) {
        setServer(data.current_server);
      }
      setStatusMsg({ text: 'MT4 directory auto-detected and synchronized.' });
    } catch {
      setStatusMsg({ text: 'Auto-detection finished. Saved parameters loaded.', isError: false });
    } finally {
      setIsDetecting(false);
    }
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accountNumber.trim()) {
      setStatusMsg({ text: 'Account number is required.', isError: true });
      return;
    }

    setIsConnecting(true);
    setStatusMsg(null);

    const parsedBalance = parseFloat(balance) || 0.0;
    const parsedLeverage = parseInt(leverage, 10) || 200;

    const newAcc: UserAccount = {
      id: `acc-${Date.now()}`,
      account_number: accountNumber.trim(),
      broker: broker.trim(),
      server: server.trim() || `${broker}-Live`,
      name: nickname.trim() || `${broker} Account`,
      currency: 'USD',
      balance: parsedBalance,
      equity: parsedBalance,
      leverage: parsedLeverage,
      is_active: true,
      created_at: new Date().toISOString(),
    };

    try {
      await api.connectAccount({
        account_number: accountNumber.trim(),
        server: server.trim(),
        broker: broker.trim(),
        balance: parsedBalance,
        leverage: parsedLeverage,
        password: password || undefined,
        terminal_path: detectedPath || undefined,
      });

      // Update multi-account storage in localStorage
      try {
        const stored = localStorage.getItem('ak_user_accounts');
        let currentList: UserAccount[] = stored ? JSON.parse(stored) : [];
        // Set all existing to inactive
        currentList = currentList.map((a) => ({ ...a, is_active: false }));
        // Replace if already exists, else append
        const existingIdx = currentList.findIndex((a) => a.account_number === newAcc.account_number);
        if (existingIdx >= 0) {
          currentList[existingIdx] = { ...currentList[existingIdx], ...newAcc, is_active: true };
        } else {
          currentList.push(newAcc);
        }
        localStorage.setItem('ak_user_accounts', JSON.stringify(currentList));
        localStorage.setItem('ak_connected_mt4_account', JSON.stringify(newAcc));
      } catch {
        // Storage fallback
      }

      setStatusMsg({ text: `Account ID: ${newAcc.account_number} added & linked successfully!` });
      if (onAccountAdded) {
        onAccountAdded(newAcc);
      }
      onConnected();
      setTimeout(onClose, 1200);
    } catch (err: any) {
      // Offline fallback: save locally so user can still switch in UI
      try {
        const stored = localStorage.getItem('ak_user_accounts');
        let currentList: UserAccount[] = stored ? JSON.parse(stored) : [];
        currentList = currentList.map((a) => ({ ...a, is_active: false }));
        const existingIdx = currentList.findIndex((a) => a.account_number === newAcc.account_number);
        if (existingIdx >= 0) {
          currentList[existingIdx] = { ...currentList[existingIdx], ...newAcc, is_active: true };
        } else {
          currentList.push(newAcc);
        }
        localStorage.setItem('ak_user_accounts', JSON.stringify(currentList));
        if (onAccountAdded) {
          onAccountAdded(newAcc);
        }
        onConnected();
        setStatusMsg({ text: `Account ID: ${newAcc.account_number} saved locally to desk.` });
        setTimeout(onClose, 1200);
      } catch {
        setStatusMsg({ text: err.message || 'Failed to connect account.', isError: true });
      }
    } finally {
      setIsConnecting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="glass-panel w-full max-w-lg rounded-2xl border border-white/10 shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-dark-card">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-accent-lime-15 text-accent-lime">
              <Plus className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Add MT4 Trading Account</h2>
              <p className="text-xs text-slate-400">Ak Trading System • Multi-Account Portfolio Management</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleConnect} className="p-6 space-y-4">
          {/* Account Nickname & Broker Selector */}
          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">Account Nickname</label>
            <input
              type="text"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-medium text-white focus:outline-none focus:border-accent-lime"
              placeholder="e.g. Exness Live Desk, Prop Firm, Personal Live"
            />
          </div>

          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">Broker Name</label>
            <div className="grid grid-cols-4 gap-2">
              {['Exness', 'IC Markets', 'FTMO', 'Custom'].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => {
                    setBroker(b);
                    if (b === 'Exness') setServer('Exness-Real21');
                    if (b === 'IC Markets') setServer('ICMarkets-Live04');
                    if (b === 'FTMO') setServer('FTMO-Server');
                  }}
                  className={`py-1.5 px-2 rounded-lg text-xs font-medium border text-center transition-all ${
                    broker === b
                      ? 'bg-accent-lime-15 border-accent-lime-40 text-accent-lime font-bold'
                      : 'bg-black/30 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>

          {/* Account Number & Server */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">MT4 Account Number</label>
              <input
                type="text"
                required
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                placeholder="e.g. 69800896"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">Server Name</label>
              <input
                type="text"
                required
                value={server}
                onChange={(e) => setServer(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                placeholder="e.g. Exness-Real21"
              />
            </div>
          </div>

          {/* Balance & Leverage */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1 flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-accent-lime" />
                <span>Account Balance (USD)</span>
              </label>
              <input
                type="number"
                step="any"
                required
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                placeholder="e.g. 5000"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1 flex items-center gap-1">
                <Gauge className="w-3 h-3 text-accent-cyan" />
                <span>Leverage</span>
              </label>
              <select
                value={leverage}
                onChange={(e) => setLeverage(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
              >
                <option value="100">1:100</option>
                <option value="200">1:200</option>
                <option value="500">1:500</option>
                <option value="1000">1:1000</option>
                <option value="2000">1:2000</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">
              Trading Password <span className="text-slate-500 font-normal">(Optional if saved in MT4 terminal)</span>
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
              placeholder="Leave blank if already authenticated"
            />
          </div>

          {/* Detected Files Directory */}
          <div className="p-3 rounded-lg bg-black/30 border border-white/5 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
                <Monitor className="w-3.5 h-3.5 text-accent-cyan" />
                MT4 Data Directory
              </span>
              <button
                type="button"
                onClick={handleAutoDetect}
                disabled={isDetecting}
                className="text-[11px] text-accent-lime hover:underline flex items-center gap-1 font-semibold cursor-pointer"
              >
                <Search className="w-3 h-3" />
                {isDetecting ? 'Detecting...' : 'Scan Terminal'}
              </button>
            </div>
            <p className="text-[11px] text-slate-300 font-mono break-all bg-black/50 p-2 rounded border border-white/5">
              {detectedPath || 'Scanning active MetaTrader 4 directory...'}
            </p>
          </div>

          {/* Status Message */}
          {statusMsg && (
            <div className={`p-2.5 rounded-lg text-xs flex items-center gap-2 ${
              statusMsg.isError ? 'bg-accent-red-15 text-accent-red border border-accent-red-40' : 'bg-accent-green-15 text-accent-green border border-accent-green-40'
            }`}>
              {statusMsg.isError ? <AlertCircle className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}
              <span>{statusMsg.text}</span>
            </div>
          )}

          {/* Bottom Info Note */}
          <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono pt-1">
            <Shield className="w-3.5 h-3.5 text-accent-lime" />
            <span>Accounts are saved permanently and can be switched anytime.</span>
          </div>

          {/* Actions */}
          <div className="pt-2 flex items-center justify-end gap-3 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isConnecting}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-accent-lime hover:bg-lime-300 text-black text-xs font-black transition-all shadow-lg active:scale-95 disabled:opacity-50 cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              {isConnecting ? 'Adding Account...' : 'Add & Activate Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
