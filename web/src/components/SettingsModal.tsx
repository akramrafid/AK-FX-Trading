'use client';

import React, { useState, useEffect } from 'react';
import { X, Save, Sliders, Shield, Clock, HardDrive, Bell } from 'lucide-react';
import { Settings } from '../types/trading';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: Settings;
  onSave: (newSettings: Settings) => Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onSave,
}) => {
  const [formData, setFormData] = useState<Settings>({});
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setFormData({ ...settings });
      setSaveSuccess(false);
    }
  }, [isOpen, settings]);

  if (!isOpen) return null;

  const handleChange = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await onSave(formData);
      setSaveSuccess(true);
      setTimeout(() => {
        setIsSaving(false);
        onClose();
      }, 1000);
    } catch (err) {
      console.error('Failed to save settings:', err);
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="glass-panel w-full max-w-2xl rounded-2xl border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-dark-card">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-accent-lime-15 text-accent-lime">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Trading Desk Configuration</h2>
              <p className="text-xs text-slate-400">Environment variables & guardrail parameters (.env)</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Strategy Mode Toggle */}
          <div>
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block mb-2">
              Strategy Execution Preset
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => handleChange('STRATEGY_MODE', 'c1_wickswap')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  (formData['STRATEGY_MODE'] || 'c1_wickswap') === 'c1_wickswap'
                    ? 'border-accent-lime bg-accent-lime-10 text-white shadow-sm'
                    : 'border-white/10 bg-black/30 text-slate-400 hover:border-white/20'
                }`}
              >
                <div className="font-bold text-xs text-accent-lime">C1 Wick-Swap (Active Test)</div>
                <div className="text-[11px] text-slate-400 mt-1">1:5 R:R • BE @ 2.0R • C1 Stop Loss</div>
              </button>

              <button
                type="button"
                onClick={() => handleChange('STRATEGY_MODE', 'institutional')}
                className={`p-3 rounded-xl border text-left transition-all ${
                  formData['STRATEGY_MODE'] === 'institutional'
                    ? 'border-accent-cyan bg-accent-cyan-15 text-white shadow-sm'
                    : 'border-white/10 bg-black/30 text-slate-400 hover:border-white/20'
                }`}
              >
                <div className="font-bold text-xs text-accent-cyan">Institutional 5 Pillars</div>
                <div className="text-[11px] text-slate-400 mt-1">Asian Sweeps • 70% @ 2R • 5R Runner</div>
              </button>
            </div>
          </div>

          {/* Instrument & Sizing */}
          <div className="space-y-3">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300 uppercase tracking-wider">
              <Shield className="w-3.5 h-3.5 text-accent-cyan" />
              Instrument & Risk Sizing
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Broker Symbol</label>
                <input
                  type="text"
                  value={formData['TRADING_SYMBOL'] || 'USDCADm'}
                  onChange={(e) => handleChange('TRADING_SYMBOL', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="e.g. USDCADm (case sensitive)"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Timeframe</label>
                <input
                  type="text"
                  value={formData['TRADING_TIMEFRAME'] || 'M5'}
                  onChange={(e) => handleChange('TRADING_TIMEFRAME', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="M5"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Risk Per Trade (Decimal)</label>
                <input
                  type="text"
                  value={formData['RISK_PER_TRADE_PCT'] || '0.01'}
                  onChange={(e) => handleChange('RISK_PER_TRADE_PCT', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="0.01 = 1.0%"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Max Spread (Pips)</label>
                <input
                  type="text"
                  value={formData['MAX_SPREAD_PIPS'] || '2.5'}
                  onChange={(e) => handleChange('MAX_SPREAD_PIPS', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="2.5"
                />
              </div>
            </div>
          </div>

          {/* Session Hours & Cutoff */}
          <div className="space-y-3">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300 uppercase tracking-wider">
              <Clock className="w-3.5 h-3.5 text-accent-lime" />
              Trading Session Window & 12 AM Cutoff
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Session Start Hour (UTC)</label>
                <input
                  type="text"
                  value={formData['SESSION_START_HOUR'] || '7'}
                  onChange={(e) => handleChange('SESSION_START_HOUR', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="7 = 07:00 UTC (1:00 PM local)"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Session End Hour (UTC)</label>
                <input
                  type="text"
                  value={formData['SESSION_END_HOUR'] || '18'}
                  onChange={(e) => handleChange('SESSION_END_HOUR', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="18 = 18:00 UTC (12:00 AM local)"
                />
              </div>
            </div>
            <p className="text-[11px] text-accent-lime bg-accent-lime-10 p-2.5 rounded-lg border border-accent-lime-40 font-medium">
              💡 18:00 UTC corresponds to 12:00 AM (Midnight) local time (UTC+6, Dhaka). Trading stops and no trades can execute after 12 AM.
            </p>
          </div>

          {/* MT4 Terminal Directory */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300 uppercase tracking-wider">
              <HardDrive className="w-3.5 h-3.5 text-slate-400" />
              MetaTrader 4 Files Directory
            </div>
            <input
              type="text"
              value={formData['MT4_FILES_DIR'] || ''}
              onChange={(e) => handleChange('MT4_FILES_DIR', e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
              placeholder="C:\Users\...\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL4\Files"
            />
          </div>

          {/* Telegram Alerts (Optional) */}
          <div className="space-y-3">
            <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300 uppercase tracking-wider">
              <Bell className="w-3.5 h-3.5 text-slate-400" />
              Telegram Alerts (Optional)
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Bot Token</label>
                <input
                  type="password"
                  value={formData['TELEGRAM_BOT_TOKEN'] || ''}
                  onChange={(e) => handleChange('TELEGRAM_BOT_TOKEN', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="Optional bot token"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Chat ID</label>
                <input
                  type="text"
                  value={formData['TELEGRAM_CHAT_ID'] || ''}
                  onChange={(e) => handleChange('TELEGRAM_CHAT_ID', e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-accent-lime"
                  placeholder="Optional chat ID"
                />
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="pt-4 border-t border-white/10 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-accent-lime hover:bg-accent-lime/90 text-black text-xs font-black transition-all shadow-lg active:scale-95 disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {isSaving ? 'Saving...' : saveSuccess ? 'Saved!' : 'Save Configuration'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
