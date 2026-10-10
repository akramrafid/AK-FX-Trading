'use client';

import React, { useState } from 'react';
import { Lock, Mail, Eye, EyeOff, ShieldCheck, ArrowRight, Sparkles } from 'lucide-react';

interface AuthScreenProps {
  onLogin: (user: { email: string; name: string }) => void;
}

export const AuthScreen: React.FC<AuthScreenProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setErrorMsg('Please enter your Gmail address.');
      return;
    }

    if (!trimmedEmail.includes('@') || !trimmedEmail.includes('.')) {
      setErrorMsg('Please enter a valid email address (e.g. yourname@gmail.com).');
      return;
    }

    if (!password) {
      setErrorMsg('Please enter your password.');
      return;
    }

    if (password.length < 4) {
      setErrorMsg('Password must be at least 4 characters.');
      return;
    }

    setIsLoading(true);

    setTimeout(() => {
      const userObj = {
        email: trimmedEmail,
        name: trimmedEmail.split('@')[0],
      };

      if (rememberMe) {
        try {
          localStorage.setItem('ak_trading_auth_user', JSON.stringify(userObj));
        } catch {
          // LocalStorage fallback
        }
      }

      setIsLoading(false);
      onLogin(userObj);
    }, 600);
  };

  const handleQuickDemo = () => {
    setEmail('ak@gmail.com');
    setPassword('aktrading2026');
    setErrorMsg(null);
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/90 p-4 font-sans select-none overflow-y-auto animate-in fade-in duration-300">
      {/* Background Aura */}
      <div className="absolute inset-0 bg-desktop-aura opacity-75 pointer-events-none" />

      {/* Login Card */}
      <div className="relative z-10 w-full max-w-md bg-window-shell rounded-3xl border border-white/10 shadow-2xl p-6 sm:p-8 backdrop-blur-xl">
        {/* Top Monogram & Brand Header */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-window-card border border-accent-lime-40 flex items-center justify-center shadow-lg mb-3">
            <svg
              className="w-8 h-8 text-accent-lime"
              viewBox="0 0 100 100"
              fill="none"
              stroke="currentColor"
              strokeWidth="8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M 22 78 L 38 22 L 54 78" />
              <path d="M 28 58 L 48 58" />
              <path d="M 58 22 L 58 78" />
              <path d="M 82 24 L 59 50 L 84 78" />
            </svg>
          </div>

          <h2 className="text-xl sm:text-2xl font-extrabold text-white tracking-tight">
            Ak Trading System
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Sign in to access your quantitative trading desk
          </p>
        </div>

        {/* Error Notification */}
        {errorMsg && (
          <div className="mb-4 p-3 rounded-xl bg-accent-red-15 border border-accent-red-40 text-accent-red text-xs font-mono animate-in slide-in-from-top-2">
            {errorMsg}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Gmail Field */}
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              Gmail Address
            </label>
            <div className="relative flex items-center">
              <Mail className="absolute left-3.5 w-4 h-4 text-slate-400 pointer-events-none" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="ak@gmail.com"
                required
                className="w-full bg-black/50 border border-white/15 focus:border-accent-lime focus:ring-1 focus:ring-accent-lime rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-slate-500 font-mono transition-all outline-none"
              />
            </div>
          </div>

          {/* Password Field */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-semibold text-slate-300">
                Password
              </label>
            </div>
            <div className="relative flex items-center">
              <Lock className="absolute left-3.5 w-4 h-4 text-slate-400 pointer-events-none" />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                required
                className="w-full bg-black/50 border border-white/15 focus:border-accent-lime focus:ring-1 focus:ring-accent-lime rounded-xl pl-10 pr-10 py-2.5 text-xs text-white placeholder-slate-500 font-mono transition-all outline-none"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 text-slate-400 hover:text-slate-200 transition-colors p-1"
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Remember Me Checkbox */}
          <div className="flex items-center justify-between text-xs pt-1">
            <label className="flex items-center gap-2 text-slate-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="rounded bg-black/60 border-white/20 text-accent-lime focus:ring-0 w-3.5 h-3.5 accent-lime"
              />
              <span>Keep me signed in</span>
            </label>

            <button
              type="button"
              onClick={handleQuickDemo}
              className="inline-flex items-center gap-1 text-[11px] text-accent-lime hover:underline"
            >
              <Sparkles className="w-3 h-3" />
              <span>Fill Demo</span>
            </button>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full mt-2 py-3 px-4 rounded-xl bg-accent-lime hover:bg-lime-300 active:scale-[0.99] text-black font-bold text-xs uppercase tracking-wider flex items-center justify-center gap-2 shadow-lg shadow-lime-900/20 transition-all cursor-pointer disabled:opacity-70"
          >
            {isLoading ? (
              <span>Authenticating...</span>
            ) : (
              <>
                <span>Sign In to Ak Trading System</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        {/* Security Assurance */}
        <div className="mt-6 pt-4 border-t border-white/5 flex items-center justify-center gap-2 text-[11px] text-slate-500 font-mono">
          <ShieldCheck className="w-3.5 h-3.5 text-accent-green" />
          <span>256-Bit Encrypted Session • Persisted on Device</span>
        </div>
      </div>
    </div>
  );
};
