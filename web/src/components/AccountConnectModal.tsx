'use client';

import React, { useState, useEffect } from 'react';
import { X, Link2, Search, CheckCircle2, AlertCircle, Monitor } from 'lucide-react';
import { api } from '../lib/api';

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConnected: () => void;
}

export const AccountConnectModal: React.FC<AccountModalProps> = ({ isOpen, onClose, onConnected }) => {
  const [accountNumber, setAccountNumber] = useState('70702138');
  const [server, setServer] = useState('Exness-Real21');
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
      setStatusMsg({ text: 'MT4 directory auto-detected successfully.' });
    } catch {
      setStatusMsg({ text: 'Auto-detection failed. You can enter paths manually.', isError: true });
    } finally {
      setIsDetecting(false);
    }
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsConnecting(true);
    setStatusMsg(null);
    try {
      const res = await api.connectAccount({
        account_number: accountNumber,
        server,
        password: password || undefined,
        terminal_path: detectedPath || undefined,
      });
      if (res.status === 'connected') {
        setStatusMsg({ text: res.message || 'Connected successfully!' });
        onConnected();
        setTimeout(onClose, 1200);
      } else {
        setStatusMsg({ text: res.message || 'Connection failed.', isError: true });
      }
    } catch (err: any) {
      setStatusMsg({ text: err.message || 'Failed to connect account.', isError: true });
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
              <Link2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Connect MetaTrader 4 Account</h2>
              <p className="text-xs text-slate-400">Bridge auto-detection & terminal authentication</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleConnect} className="p-6 space-y-4">
          {/* Account Number & Server */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">Account Number</label>
              <input
                type="text"
                required
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                placeholder="e.g. 70702138"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-300 font-semibold block mb-1">Account Server</label>
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

          <div>
            <label className="text-[11px] text-slate-300 font-semibold block mb-1">
              Trading Password <span className="text-slate-500 font-normal">(Optional for auto-launch)</span>
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
              placeholder="Leave blank if already saved in MT4"
            />
          </div>

          {/* Detected Files Directory */}
          <div className="p-3 rounded-lg bg-black/30 border border-white/5 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
                <Monitor className="w-3.5 h-3.5 text-accent-cyan" />
                MT4 MQL4 Files Directory
              </span>
              <button
                type="button"
                onClick={handleAutoDetect}
                disabled={isDetecting}
                className="text-[11px] text-accent-lime hover:underline flex items-center gap-1 font-semibold"
              >
                <Search className="w-3 h-3" />
                {isDetecting ? 'Detecting...' : 'Scan Terminal'}
              </button>
            </div>
            <p className="text-[11px] text-slate-300 font-mono break-all bg-black/50 p-2 rounded border border-white/5">
              {detectedPath || 'Scanning for active MT4 terminal installation...'}
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

          {/* Actions */}
          <div className="pt-2 flex items-center justify-end gap-3 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isConnecting}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-accent-lime hover:bg-accent-lime/90 text-black text-xs font-black transition-all shadow-lg active:scale-95 disabled:opacity-50"
            >
              <Link2 className="w-4 h-4" />
              {isConnecting ? 'Connecting...' : 'Connect & Launch'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
