'use client';

import React, { useEffect, useState } from 'react';
import { ShieldCheck, ChevronRight } from 'lucide-react';

interface IntroSplashProps {
  onComplete: () => void;
}

export const IntroSplash: React.FC<IntroSplashProps> = ({ onComplete }) => {
  const [step, setStep] = useState(0);
  const [progress, setProgress] = useState(15);

  const statusMessages = [
    'Initializing Ak Trading System Engine...',
    'Connecting SQLite Database telemetry...',
    'Calibrating USDCAD C1 Wick-Swap scanner...',
    'Welcome, AK. Launching Security Gateway...',
  ];

  useEffect(() => {
    const timer1 = setTimeout(() => {
      setStep(1);
      setProgress(45);
    }, 600);

    const timer2 = setTimeout(() => {
      setStep(2);
      setProgress(78);
    }, 1300);

    const timer3 = setTimeout(() => {
      setStep(3);
      setProgress(100);
    }, 2000);

    const timer4 = setTimeout(() => {
      onComplete();
    }, 2600);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
    };
  }, [onComplete]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/95 text-slate-100 overflow-hidden font-sans select-none animate-in fade-in duration-300">
      {/* Radial atmospheric glowing backdrop */}
      <div className="absolute inset-0 bg-desktop-aura opacity-70 pointer-events-none" />

      {/* Background Grid Pattern */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:32px_32px] pointer-events-none opacity-40" />

      {/* Main Centered Brand Card */}
      <div className="relative z-10 flex flex-col items-center text-center max-w-md px-6 py-8">
        {/* Animated AK Monogram Logo */}
        <div className="relative w-28 h-28 mb-8 flex items-center justify-center">
          {/* Outer Breathing Glow Ring */}
          <div className="absolute inset-0 rounded-3xl bg-accent-lime-15 blur-xl animate-pulse-glow" />
          <div className="absolute -inset-1 rounded-3xl bg-gradient-to-tr from-accent-lime/30 via-transparent to-accent-cyan/20 blur-sm" />

          {/* Central Logo Box */}
          <div className="relative w-full h-full rounded-3xl bg-window-shell border border-accent-lime/40 shadow-2xl flex items-center justify-center overflow-hidden animate-ak-logo">
            {/* Shimmer Light Beam Sweep */}
            <div className="absolute inset-0 w-1/2 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-ak-beam" />

            {/* Custom SVG Geometric AK Monogram */}
            <svg
              className="w-16 h-16 text-accent-lime drop-shadow-md"
              viewBox="0 0 100 100"
              fill="none"
              stroke="currentColor"
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {/* Letter 'A' Form */}
              <path d="M 22 78 L 38 22 L 54 78" />
              <path d="M 28 58 L 48 58" />

              {/* Letter 'K' Form */}
              <path d="M 58 22 L 58 78" />
              <path d="M 82 24 L 59 50 L 84 78" />
            </svg>
          </div>
        </div>

        {/* Brand System Title */}
        <div className="space-y-2 mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent-lime-10 border border-accent-lime-40 text-accent-lime text-[11px] font-mono uppercase tracking-widest font-bold">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-lime animate-ping" />
            <span>AK TRADING SYSTEM</span>
          </div>

          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
            Ak Trading System
          </h1>

          <p className="text-xs sm:text-sm text-slate-400 font-medium max-w-xs mx-auto">
            Institutional Algorithmic Execution Terminal • USDCAD Specialist
          </p>
        </div>

        {/* Progress Bar & Telemetry Status */}
        <div className="w-full max-w-xs space-y-3">
          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden p-0.5 border border-white/5">
            <div
              className="h-full bg-gradient-to-r from-accent-lime via-emerald-400 to-accent-cyan rounded-full transition-all duration-500 ease-out shadow-sm"
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span className="truncate">{statusMessages[step]}</span>
            <span className="font-bold text-accent-lime ml-2">{progress}%</span>
          </div>
        </div>

        {/* Bottom Security Badge */}
        <div className="mt-8 flex items-center gap-1.5 text-[11px] text-slate-500 font-mono">
          <ShieldCheck className="w-3.5 h-3.5 text-accent-green" />
          <span>Hardware-Bound • SQLite DB Connected • Session Guard</span>
        </div>

        {/* Fast Bypass Button */}
        <button
          onClick={onComplete}
          className="mt-6 flex items-center gap-1 text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
        >
          <span>Continue to Login</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
