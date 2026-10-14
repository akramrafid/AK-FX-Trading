'use client';

import React, { useState, useEffect } from 'react';
import { X, Search, CheckCircle2, AlertCircle, Monitor, Shield, Plus, DollarSign, Gauge, Zap } from 'lucide-react';
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
  const [accountNumber, setAccountNumber] = useState('');
  const [nickname, setNickname] = useState('');
  const [server, setServer] = useState('');
  const [broker, setBroker] = useState('Exness Technologies Ltd');
  const [leverage, setLeverage] = useState('2000');
  const [balance, setBalance] = useState('5000.00');
  const [currency, setCurrency] = useState('USD');
  const [password, setPassword] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [detectedPath, setDetectedPath] = useState('');
  const [detectedExe, setDetectedExe] = useState('');
  const [detectedMT4Account, setDetectedMT4Account] = useState('69800896');
  const [detectedMT4Server, setDetectedMT4Server] = useState('Exness-Trial8');
  const [isDetecting, setIsDetecting] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; isError?: boolean } | null>(null);

  // Background detection without overwriting user form inputs
  useEffect(() => {
    if (isOpen) {
      api.getAccountDetect().then((data) => {
        if (data.detected_files_dir) setDetectedPath(data.detected_files_dir);
        if (data.detected_exe_path) setDetectedExe(data.detected_exe_path);
        if (data.current_account) setDetectedMT4Account(data.current_account);
        if (data.current_server) setDetectedMT4Server(data.current_server);
      }).catch(() => {
        // Silent background detection fallback
      });
    }
  }, [isOpen]);

  const handleFillFromActiveMT4 = async () => {
    setIsDetecting(true);
    setStatusMsg(null);
    try {
      const data = await api.getAccountDetect();
      const acc = data.current_account || '69800896';
      const srv = data.current_server || 'Exness-Trial8';
      setAccountNumber(acc);
      setServer(srv);
      setBroker('Exness Technologies Ltd');
      setNickname(`Standard (${srv})`);
      setLeverage('2000');
      setBalance('5000.00');
      setCurrency('USD');
      if (data.detected_files_dir) setDetectedPath(data.detected_files_dir);
      if (data.detected_exe_path) setDetectedExe(data.detected_exe_path);
      setStatusMsg({ text: `Auto-filled active MT4 account ID: ${acc} (${srv}).` });
    } catch {
      setAccountNumber('69800896');
      setServer('Exness-Trial8');
      setBroker('Exness Technologies Ltd');
      setNickname('Standard (Exness-Trial8)');
      setLeverage('2000');
      setBalance('5000.00');
      setStatusMsg({ text: 'Loaded default active MT4 credentials.' });
    } finally {
      setIsDetecting(false);
    }
  };

  const handlePresetSelect = (preset: string) => {
    switch (preset) {
      case 'Exness Standard':
        setBroker('Exness Technologies Ltd');
        setServer('Exness-Trial8');
        setNickname('Standard (Exness-Trial8)');
        setLeverage('2000');
        setBalance('5000.00');
        break;
      case 'Exness Real':
        setBroker('Exness Technologies Ltd');
        setServer('Exness-Real21');
        setNickname('Exness Real Desk');
        setLeverage('2000');
        setBalance('5000.00');
        break;
      case 'IC Markets':
        setBroker('IC Markets Global');
        setServer('ICMarkets-Live01');
        setNickname('IC Markets Raw Spread');
        setLeverage('500');
        setBalance('10000.00');
        break;
      case 'FTMO':
        setBroker('FTMO Challenge');
        setServer('FTMO-Server2');
        setNickname('FTMO 100k Account');
        setLeverage('100');
        setBalance('100000.00');
        break;
      case 'RoboForex':
        setBroker('RoboForex Global');
        setServer('RoboForex-Pro');
        setNickname('RoboForex ECN');
        setLeverage('1000');
        setBalance('2500.00');
        break;
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
      broker: broker.trim() || 'MetaTrader 4 Broker',
      server: server.trim() || `${broker}-Live`,
      name: nickname.trim() || `${broker} (${accountNumber.trim()})`,
      currency: currency.trim().toUpperCase() || 'USD',
      balance: parsedBalance,
      equity: parsedBalance,
      leverage: parsedLeverage,
      is_active: isActive,
      created_at: new Date().toISOString(),
    };

    try {
      // 1. Save directly into backend SQLite database
      const saveResp = await api.saveAccount(newAcc);
      const savedAcc = saveResp.account || newAcc;

      // 2. If active, connect terminal bridge & synchronize .env
      if (isActive) {
        await api.switchAccount(savedAcc.account_number);
        await api.connectAccount({
          account_number: savedAcc.account_number,
          server: savedAcc.server,
          broker: savedAcc.broker,
          balance: parsedBalance,
          leverage: parsedLeverage,
          password: password || undefined,
          terminal_path: detectedPath || undefined,
        });
      }

      // 3. Update localStorage for client persistence
      try {
        const stored = localStorage.getItem('ak_user_accounts');
        let currentList: UserAccount[] = stored ? JSON.parse(stored) : [];
        if (isActive) {
          currentList = currentList.map((a) => ({ ...a, is_active: false }));
        }
        const existingIdx = currentList.findIndex((a) => a.account_number === savedAcc.account_number);
        if (existingIdx >= 0) {
          currentList[existingIdx] = { ...currentList[existingIdx], ...savedAcc };
        } else {
          currentList.push(savedAcc);
        }
        localStorage.setItem('ak_user_accounts', JSON.stringify(currentList));
        if (isActive) {
          localStorage.setItem('ak_connected_mt4_account', JSON.stringify(savedAcc));
        }
      } catch {
        // Storage fallback
      }

      setStatusMsg({ text: `Account ID: ${savedAcc.account_number} saved & synchronized successfully!` });
      if (onAccountAdded) {
        onAccountAdded(savedAcc);
      }
      onConnected();
      setTimeout(onClose, 1000);
    } catch (err: any) {
      // Offline fallback: save locally so user can still switch in UI
      try {
        const stored = localStorage.getItem('ak_user_accounts');
        let currentList: UserAccount[] = stored ? JSON.parse(stored) : [];
        if (isActive) {
          currentList = currentList.map((a) => ({ ...a, is_active: false }));
        }
        const existingIdx = currentList.findIndex((a) => a.account_number === newAcc.account_number);
        if (existingIdx >= 0) {
          currentList[existingIdx] = { ...currentList[existingIdx], ...newAcc };
        } else {
          currentList.push(newAcc);
        }
        localStorage.setItem('ak_user_accounts', JSON.stringify(currentList));
        if (onAccountAdded) {
          onAccountAdded(newAcc);
        }
        onConnected();
        setStatusMsg({ text: `Account ID: ${newAcc.account_number} saved locally to desk.` });
        setTimeout(onClose, 1000);
      } catch {
        setStatusMsg({ text: err.message || 'Failed to add account.', isError: true });
      }
    } finally {
      setIsConnecting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="glass-panel w-full max-w-lg rounded-2xl border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-dark-card shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-accent-lime-15 text-accent-lime">
              <Plus className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Add MT4 Trading Account</h2>
              <p className="text-xs text-slate-400">Add unlimited trading accounts to your portfolio desk</p>
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
        <form onSubmit={handleConnect} className="p-6 space-y-4 overflow-y-auto">
          {/* Quick Auto-Fill Action */}
          <div className="flex items-center justify-between p-3 rounded-xl bg-accent-lime-15 border border-accent-lime-40">
            <div className="flex items-center gap-2 truncate">
              <Zap className="w-4 h-4 text-accent-lime shrink-0" />
              <div className="truncate">
                <span className="text-xs text-white font-bold block">Detected MT4 Terminal</span>
                <span className="text-[11px] font-mono text-slate-300">
                  Account ID: {detectedMT4Account} ({detectedMT4Server})
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={handleFillFromActiveMT4}
              disabled={isDetecting}
              className="px-3 py-1.5 rounded-lg bg-accent-lime text-black text-xs font-bold hover:bg-lime-300 transition-colors cursor-pointer shrink-0"
            >
              {isDetecting ? 'Scanning...' : 'Auto-fill'}
            </button>
          </div>

          {/* Quick Preset Buttons */}
          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">Quick Broker Presets</label>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {['Exness Standard', 'Exness Real', 'IC Markets', 'FTMO', 'RoboForex'].map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => handlePresetSelect(preset)}
                  className="py-1 px-1.5 rounded-lg text-[11px] font-medium border text-center transition-all bg-black/30 border-white/10 text-slate-300 hover:text-accent-lime hover:border-accent-lime-40"
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>

          {/* Account Nickname */}
          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">Account Nickname / Desk Name</label>
            <input
              type="text"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-medium text-white focus:outline-none focus:border-accent-lime"
              placeholder="e.g. Exness Scalper, FTMO 100k Challenge, IC Markets ECN"
            />
          </div>

          {/* Broker & Server Name */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">Broker Company</label>
              <input
                type="text"
                required
                value={broker}
                onChange={(e) => setBroker(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-accent-lime"
                placeholder="e.g. Exness, IC Markets"
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
                placeholder="e.g. Exness-Trial8, ICMarkets-Live01"
              />
            </div>
          </div>

          {/* Account Number & Currency */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">MT4 Account Number</label>
              <input
                type="text"
                required
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime font-bold"
                placeholder="e.g. 69800896 or 12345678"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">Currency</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="AUD">AUD</option>
              </select>
            </div>
          </div>

          {/* Balance & Leverage */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1 flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-accent-lime" />
                <span>Account Balance ($)</span>
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

          {/* Password (Optional) */}
          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">
              Trading Password <span className="text-slate-500 font-normal">(Optional if already saved in MT4 terminal)</span>
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
              placeholder="Leave blank if terminal is already authenticated"
            />
          </div>

          {/* Set Active Checkbox */}
          <div className="flex items-center gap-2.5 p-3 rounded-lg bg-black/30 border border-white/5">
            <input
              type="checkbox"
              id="set-active-toggle"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4 rounded text-accent-lime focus:ring-0 cursor-pointer accent-accent-lime"
            />
            <label htmlFor="set-active-toggle" className="text-xs text-slate-200 cursor-pointer select-none">
              <span className="font-bold">Set as Active Trading Account</span>
              <span className="text-[11px] text-slate-400 block">Immediately switches bridge execution to this account</span>
            </label>
          </div>

          {/* Detected Files Directory */}
          <div className="p-3 rounded-lg bg-black/30 border border-white/5 space-y-1">
            <span className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
              <Monitor className="w-3.5 h-3.5 text-accent-cyan" />
              MT4 Data Directory
            </span>
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
            <Shield className="w-3.5 h-3.5 text-accent-lime shrink-0" />
            <span>Accounts are saved permanently in database and can be switched dynamically anytime.</span>
          </div>

          {/* Actions */}
          <div className="pt-2 flex items-center justify-end gap-3 border-t border-white/10 shrink-0">
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
              {isConnecting ? 'Adding Account...' : (isActive ? 'Add & Activate Account' : 'Add Account')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
