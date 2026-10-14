'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  LineSeries,
  IChartApi,
  ISeriesApi
} from 'lightweight-charts';
import { Candle, Position } from '../types/trading';
import {
  TrendingUp,
  TrendingDown,
  SlidersHorizontal,
  Maximize2,
  ChevronDown,
} from 'lucide-react';
import { TradeLedger, TradeRecord } from './TradeLedger';

interface ChartProps {
  candles: Candle[];
  symbol: string;
  timeframe: string;
  onTimeframeChange?: (tf: string) => void;
  onSymbolChange?: (sym: string) => void;
  bidPrice?: number;
  askPrice?: number;
  spreadPips?: number;
  orders?: Position[];
  tradeHistory?: TradeRecord[];
  activeAccount?: string | number;
  activeLedgerTab?: 'running' | 'history';
  onLedgerTabChange?: (tab: 'running' | 'history') => void;
}

export const TradingViewChart: React.FC<ChartProps> = ({
  candles,
  symbol,
  timeframe,
  onTimeframeChange,
  onSymbolChange,
  bidPrice,
  askPrice,
  spreadPips,
  orders = [],
  tradeHistory = [],
  activeAccount = '69800896',
  activeLedgerTab = 'running',
  onLedgerTabChange,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const smaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const [activeTf, setActiveTf] = useState(timeframe || 'M5');
  const [chartMode, setChartMode] = useState<'Original' | 'TradingView' | 'Depth'>('TradingView');
  const [showIndicators, setShowIndicators] = useState(true);
  const [selectedTicker, setSelectedTicker] = useState(symbol || 'USDCADm');

  // Dynamically compute 24h high/low and range from candles
  const { high24, low24, rangePips } = React.useMemo(() => {
    if (!candles || candles.length === 0) {
      const p = bidPrice || 1.42500;
      return { high24: p, low24: p, rangePips: 0.0 };
    }
    const highs = candles.map((c) => c.high || 0).filter((h) => h > 0);
    const lows = candles.map((c) => c.low || 999999).filter((l) => l < 999999);
    const maxH = highs.length > 0 ? Math.max(...highs) : (bidPrice || 1.42500);
    const minL = lows.length > 0 ? Math.min(...lows) : (bidPrice || 1.42500);
    const rPips = Math.round((maxH - minL) * 10000 * 10) / 10;
    return { high24: maxH, low24: minL, rangePips: rPips };
  }, [candles, bidPrice]);

  // Dedicated USDCAD (USD/CAD) market telemetry cards
  const marketTickers = [
    {
      id: 'USDCADm',
      name: 'USD/CAD (USDCADm)',
      price: bidPrice ? bidPrice.toFixed(5) : '1.42175',
      change: `Spread ${spreadPips ? spreadPips.toFixed(1) : '1.4'}p`,
      isUp: true,
      tokenBg: 'bg-emerald-600',
      tokenLetter: '$',
    },
    {
      id: 'USDCADm_SPREAD',
      name: 'USDCADm Spread',
      price: `${spreadPips ? spreadPips.toFixed(1) : '1.4'} pips`,
      change: 'Limit 2.5p',
      isUp: true,
      tokenBg: 'bg-indigo-600',
      tokenLetter: '⇄',
    },
    {
      id: 'USDCADm_RANGE',
      name: '24h High / Low',
      price: `${high24.toFixed(5)} / ${low24.toFixed(5)}`,
      change: `${rangePips.toFixed(1)}p Range`,
      isUp: false,
      tokenBg: 'bg-slate-800',
      tokenLetter: '↕',
    },
    {
      id: 'USDCADm_STRATEGY',
      name: 'C1 Wick-Swap',
      price: 'M5 & M15 Armed',
      change: '1:5 R:R Enforced',
      isUp: true,
      tokenBg: 'bg-purple-600',
      tokenLetter: '⚡',
    },
  ];

  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1d'];

  // Initialize Institutional Dark Theme Lightweight Charts
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'rgb(11, 15, 23)' },
        textColor: 'rgb(148, 163, 184)',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      crosshair: {
        vertLine: {
          color: 'rgba(0, 240, 255, 0.45)',
          width: 1,
          style: 2,
          labelBackgroundColor: 'rgb(19, 23, 34)',
        },
        horzLine: {
          color: 'rgba(0, 240, 255, 0.45)',
          width: 1,
          style: 2,
          labelBackgroundColor: 'rgb(19, 23, 34)',
        },
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        scaleMargins: {
          top: 0.10,
          bottom: 0.12,
        },
      },
      handleScale: {
        axisPressedMouseMove: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
    });

    // Emerald (bullish) and Crimson (bearish) candlesticks
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: 'rgb(0, 230, 118)',
      downColor: 'rgb(255, 51, 102)',
      wickUpColor: 'rgb(0, 230, 118)',
      wickDownColor: 'rgb(255, 51, 102)',
      borderVisible: false,
    });

    const smaSeries = chart.addSeries(LineSeries, {
      color: 'rgba(206, 255, 0, 0.75)',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const emaSeries = chart.addSeries(LineSeries, {
      color: 'rgba(0, 240, 255, 0.75)',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    smaSeriesRef.current = smaSeries;
    emaSeriesRef.current = emaSeries;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 500,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // Update candle data & SMA/EMA
  useEffect(() => {
    if (!candleSeriesRef.current || !candles || candles.length === 0) return;

    const formatted = candles
      .filter((c) => c && c.time && c.open && c.high && c.low && c.close)
      .map((c) => ({
        time: c.time as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      .sort((a, b) => a.time - b.time);

    candleSeriesRef.current.setData(formatted);

    // Calculate SMA 20
    if (smaSeriesRef.current && showIndicators) {
      const smaData: Array<{ time: any; value: number }> = [];
      const period = 20;
      for (let i = period - 1; i < formatted.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
          sum += formatted[i - j].close;
        }
        smaData.push({ time: formatted[i].time, value: sum / period });
      }
      smaSeriesRef.current.setData(smaData);
    }

    // Calculate EMA 50
    if (emaSeriesRef.current && showIndicators) {
      const emaData: Array<{ time: any; value: number }> = [];
      const period = 50;
      const k = 2 / (period + 1);
      let ema = formatted[0].close;
      for (let i = 0; i < formatted.length; i++) {
        ema = formatted[i].close * k + ema * (1 - k);
        if (i >= period - 1) {
          emaData.push({ time: formatted[i].time, value: ema });
        }
      }
      emaSeriesRef.current.setData(emaData);
    }

    chartRef.current?.timeScale().fitContent();
  }, [candles, showIndicators]);

  const handleTfClick = (tf: string) => {
    setActiveTf(tf);
    if (onTimeframeChange) {
      onTimeframeChange(tf);
    }
  };

  const handleTickerSelect = (id: string) => {
    setSelectedTicker(id);
    if (onSymbolChange) {
      onSymbolChange(id);
    }
  };

  return (
    <div className="w-full bg-window-card text-white rounded-3xl p-4 sm:p-5 md:p-6 shadow-2xl border border-white/10 flex flex-col gap-5 backdrop-blur-xl">
      {/* 1. Top Four Market Ticker Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {marketTickers.map((ticker) => {
          const isSelected = selectedTicker === ticker.id;
          return (
            <div
              key={ticker.id}
              onClick={() => handleTickerSelect(ticker.id)}
              className={`p-3.5 rounded-2xl border transition-all cursor-pointer flex items-center justify-between ${
                isSelected
                  ? 'bg-window-card-inset border-accent-lime-40 shadow-sm'
                  : 'bg-black/20 border-white/5 hover:bg-white/5 hover:border-white/10'
              }`}
            >
              <div className="flex items-center gap-2.5 truncate">
                <div className={`w-8 h-8 rounded-xl ${ticker.tokenBg} text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-sm`}>
                  {ticker.tokenLetter}
                </div>
                <div className="truncate">
                  <div className="text-xs font-bold text-slate-200 truncate">{ticker.name}</div>
                  <div className="text-[11px] font-mono font-medium text-slate-400">
                    {ticker.price}{' '}
                    <span className={ticker.isUp ? 'text-accent-green font-semibold' : 'text-accent-red font-semibold'}>
                      {ticker.change}
                    </span>
                  </div>
                </div>
              </div>

              <div className="shrink-0 pl-1">
                {ticker.isUp ? (
                  <TrendingUp className="w-3.5 h-3.5 text-accent-green" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5 text-accent-red" />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 2. Chart Toolbar (Timeframes, Modes, Tools) */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-white/10 text-xs">
        {/* Left: Timeframe pills + Chart Mode Selector */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1">
            <span className="text-[11px] font-semibold text-slate-400 mr-1 uppercase tracking-wider font-mono">Period</span>
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => handleTfClick(tf)}
                className={`px-3 py-1 rounded-xl text-xs font-bold font-mono transition-all cursor-pointer ${
                  activeTf === tf
                    ? 'bg-accent-lime text-black shadow-sm font-black'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          <div className="h-4 w-px bg-white/10 hidden sm:block" />

          {/* Chart Modes */}
          <div className="flex items-center gap-2 text-xs font-medium">
            <button
              onClick={() => setChartMode('TradingView')}
              className={`px-2.5 py-1 rounded-lg transition-colors cursor-pointer ${
                chartMode === 'TradingView'
                  ? 'bg-white/10 text-white font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              TradingView
            </button>
            <button
              onClick={() => setChartMode('Depth')}
              className={`px-2.5 py-1 rounded-lg transition-colors cursor-pointer ${
                chartMode === 'Depth'
                  ? 'bg-white/10 text-white font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Depth & Flow
            </button>
          </div>
        </div>

        {/* Right: Technical Indicators & Fullscreen */}
        <div className="flex items-center gap-2 text-slate-400">
          <button
            onClick={() => setShowIndicators(!showIndicators)}
            className={`px-2.5 py-1 rounded-lg border text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer ${
              showIndicators ? 'bg-accent-lime-15 text-accent-lime border-accent-lime-40' : 'bg-white/5 border-white/10 hover:text-white'
            }`}
            title="Toggle Indicators (SMA 20 & EMA 50)"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>SMA / EMA</span>
          </button>
          <button
            onClick={() => chartRef.current?.timeScale().fitContent()}
            className="p-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white transition-colors cursor-pointer"
            title="Reset Zoom / Fit Content"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 3. The Interactive Candlestick Chart Area (Expansive Full Canvas) */}
      <div className="relative w-full h-[460px] md:h-[520px] 2xl:h-[600px] rounded-2xl overflow-hidden bg-black/40 border border-white/10 shadow-inner">
        <div ref={containerRef} className="w-full h-full" />

        {/* Current Price Right-Axis Pill Badge */}
        {bidPrice ? (
          <div className="absolute top-[48%] right-2 z-10 px-2.5 py-1 rounded-lg bg-accent-lime text-black font-mono text-[11px] font-black shadow-lg flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-black animate-ping" />
            <span>{bidPrice.toFixed(5)}</span>
          </div>
        ) : null}
      </div>

      {/* 4. Connected Account Trade History & Running Positions Ledger */}
      <TradeLedger
        runningTrades={orders}
        tradeHistory={tradeHistory}
        activeAccount={activeAccount}
        currentBid={bidPrice}
        currentAsk={askPrice}
        activeTab={activeLedgerTab}
        onTabChange={onLedgerTabChange}
      />
    </div>
  );
};
