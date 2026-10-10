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

  // Initialize Light Theme Lightweight Charts
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'rgb(255, 255, 255)' },
        textColor: 'rgb(100, 116, 139)',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(0, 0, 0, 0.04)' },
        horzLines: { color: 'rgba(0, 0, 0, 0.04)' },
      },
      crosshair: {
        vertLine: {
          color: 'rgb(99, 102, 241)',
          width: 1,
          style: 2,
          labelBackgroundColor: 'rgb(15, 23, 42)',
        },
        horzLine: {
          color: 'rgb(99, 102, 241)',
          width: 1,
          style: 2,
          labelBackgroundColor: 'rgb(15, 23, 42)',
        },
      },
      timeScale: {
        borderColor: 'rgba(0, 0, 0, 0.08)',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: 'rgba(0, 0, 0, 0.08)',
        scaleMargins: {
          top: 0.12,
          bottom: 0.15,
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

    // Purple (bullish) and Red (bearish) candlesticks as shown in reference design
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: 'rgb(99, 102, 241)',
      downColor: 'rgb(239, 68, 68)',
      wickUpColor: 'rgb(99, 102, 241)',
      wickDownColor: 'rgb(239, 68, 68)',
      borderVisible: false,
    });

    const smaSeries = chart.addSeries(LineSeries, {
      color: 'rgba(99, 102, 241, 0.5)',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const emaSeries = chart.addSeries(LineSeries, {
      color: 'rgba(239, 68, 68, 0.5)',
      lineWidth: 1,
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
          height: 380,
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
    <div className="w-full bg-white text-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-100 flex flex-col gap-6">
      {/* 1. Top Four Market Ticker Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        {marketTickers.map((ticker) => {
          const isSelected = selectedTicker === ticker.id;
          return (
            <div
              key={ticker.id}
              onClick={() => handleTickerSelect(ticker.id)}
              className={`p-3.5 rounded-2xl border transition-all cursor-pointer flex items-center justify-between ${
                isSelected
                  ? 'bg-slate-100/80 border-slate-300 shadow-sm'
                  : 'bg-slate-50/70 border-slate-200/80 hover:bg-slate-100/50'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div className={`w-8 h-8 rounded-full ${ticker.tokenBg} text-white flex items-center justify-center font-bold text-xs shadow-sm`}>
                  {ticker.tokenLetter}
                </div>
                <div>
                  <div className="text-xs font-bold text-slate-800">{ticker.name}</div>
                  <div className="text-[11px] font-mono font-medium text-slate-500">
                    {ticker.price}{' '}
                    <span className={ticker.isUp ? 'text-emerald-600' : 'text-rose-600'}>
                      {ticker.change}
                    </span>
                  </div>
                </div>
              </div>

              <div className="text-slate-400">
                {ticker.isUp ? (
                  <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5 text-rose-500" />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 2. Chart Toolbar (Timeframes, Modes, Tools) */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-100 text-xs">
        {/* Left: Timeframe pills + Chart Mode Selector */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-semibold text-slate-400 mr-1">Time</span>
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => handleTfClick(tf)}
                className={`px-3 py-1 rounded-full text-xs font-semibold transition-all ${
                  activeTf === tf
                    ? 'bg-slate-900 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100'
                }`}
              >
                {tf}
              </button>
            ))}
            <button className="text-slate-400 hover:text-slate-700 px-1">
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-4 w-px bg-slate-200 hidden sm:block" />

          {/* Chart Modes */}
          <div className="flex items-center gap-3 text-xs font-medium">
            <button
              onClick={() => setChartMode('Original')}
              className={`transition-colors ${chartMode === 'Original' ? 'text-slate-900 font-bold' : 'text-slate-400 hover:text-slate-700'}`}
            >
              Original
            </button>
            <button
              onClick={() => setChartMode('TradingView')}
              className={`transition-colors ${chartMode === 'TradingView' ? 'text-slate-900 font-bold underline decoration-2 underline-offset-4' : 'text-slate-400 hover:text-slate-700'}`}
            >
              TradingView
            </button>
            <button
              onClick={() => setChartMode('Depth')}
              className={`transition-colors ${chartMode === 'Depth' ? 'text-slate-900 font-bold' : 'text-slate-400 hover:text-slate-700'}`}
            >
              Depth
            </button>
          </div>
        </div>

        {/* Right: Technical Indicators & Fullscreen */}
        <div className="flex items-center gap-2 text-slate-400">
          <button
            onClick={() => setShowIndicators(!showIndicators)}
            className={`p-1.5 rounded-lg border transition-colors ${
              showIndicators ? 'bg-slate-100 text-slate-800 border-slate-300' : 'hover:bg-slate-50 border-slate-200'
            }`}
            title="Toggle Indicators (SMA/EMA)"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => chartRef.current?.timeScale().fitContent()}
            className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-500 transition-colors"
            title="Reset Zoom / Fit"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 3. The Interactive Candlestick Chart Area */}
      <div className="relative w-full h-[380px] rounded-xl overflow-hidden bg-white">
        <div ref={containerRef} className="w-full h-full" />

        {/* Current Price Right-Axis Pill Badge */}
        {bidPrice ? (
          <div className="absolute top-[48%] right-2 z-10 px-2 py-0.5 rounded bg-slate-900 text-white font-mono text-[10px] font-bold shadow-md">
            {bidPrice.toFixed(5)}
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
