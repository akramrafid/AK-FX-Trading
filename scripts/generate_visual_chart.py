"""scripts/generate_visual_chart.py
Generates an interactive HTML visual chart backtester using TradingView Lightweight Charts.
Plots real USDCAD market candles from data/trading.db alongside every executed trade,
entry, SL, TP, and exit.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.run_current_strategy_backtest import load_candles_from_db, run_strategy_backtest
from engine.rule_engine import resample_m1_to_htf

def main():
    print("[1/3] Loading recorded USDCAD candles from data/trading.db...")
    m1_candles = load_candles_from_db("USDCAD")
    m5_candles = resample_m1_to_htf(m1_candles, 5)

    print(f"Loaded {len(m1_candles):,} M1 candles, {len(m5_candles):,} M5 candles.")

    print("[2/3] Running active strategy backtest on USDCAD...")
    result = run_strategy_backtest(
        m1_candles,
        symbol="USDCAD",
        initial_balance=5000.0,
        risk_pct=1.0,
        pip_size=0.0001,
        pip_value_per_lot=7.14,
        spread_pips=0.0,
        slippage_pips=0.0,
        breakeven_r=2.0,
        reward_risk_ratio=10.0,
        max_open_trades=5,
        session_filter=True,
    )

    print(f"Backtest completed with {len(result.trades)} trades.")

    # Prepare candle JSON data for Lightweight Charts
    # Time must be UTC unix timestamp in seconds
    m1_data = []
    for c in m1_candles:
        m1_data.append({
            "time": int(c.timestamp.timestamp()),
            "open": round(c.open, 5),
            "high": round(c.high, 5),
            "low": round(c.low, 5),
            "close": round(c.close, 5),
        })

    m5_data = []
    for c in m5_candles:
        m5_data.append({
            "time": int(c.timestamp.timestamp()),
            "open": round(c.open, 5),
            "high": round(c.high, 5),
            "low": round(c.low, 5),
            "close": round(c.close, 5),
        })

    # Prepare trade markers and trade table items
    markers = []
    trades_data = []

    for t in result.trades:
        entry_time = int(t.entry_time.timestamp())
        exit_time = int(t.exit_time.timestamp())
        is_buy = t.direction == "BUY"
        is_win = t.pnl_currency > 0

        # Entry Marker
        markers.append({
            "time": entry_time,
            "position": "belowBar" if is_buy else "aboveBar",
            "color": "#10b981" if is_buy else "#ef4444",
            "shape": "arrowUp" if is_buy else "arrowDown",
            "text": f"{t.direction} #{t.trade_id} @ {t.entry_price:.5f}",
        })

        # Exit Marker
        exit_color = "#10b981" if is_win else ("#f59e0b" if t.exit_reason == "BE" else "#ef4444")
        markers.append({
            "time": exit_time,
            "position": "aboveBar" if is_buy else "belowBar",
            "color": exit_color,
            "shape": "circle",
            "text": f"{t.exit_reason} (+${t.pnl_currency:.2f})" if is_win else f"{t.exit_reason} (${t.pnl_currency:.2f})",
        })

        trades_data.append({
            "id": t.trade_id,
            "direction": t.direction,
            "entry_time": t.entry_time.strftime("%Y-%m-%d %H:%M"),
            "entry_timestamp": entry_time,
            "entry_price": round(t.entry_price, 5),
            "stop_loss": round(t.stop_loss, 5),
            "take_profit": round(t.take_profit, 5),
            "exit_time": t.exit_time.strftime("%Y-%m-%d %H:%M"),
            "exit_timestamp": exit_time,
            "exit_price": round(t.exit_price, 5),
            "exit_reason": t.exit_reason,
            "realized_r": round(t.realized_r, 1),
            "pnl_cash": round(t.pnl_currency, 2),
            "pnl_pips": round(t.pnl_pips, 1),
            "lots": round(t.lots, 2),
        })

    # Sort markers by time
    markers.sort(key=lambda x: x["time"])

    # Output HTML template
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AK Strategy: Visual Market Chart Backtest (USDCAD)</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: #0b0f19;
            color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
        }}
        header {{
            background: #111827;
            border-bottom: 1px solid #1f2937;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .badge {{
            background: #1e293b;
            color: #38bdf8;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid #334155;
            text-transform: uppercase;
        }}
        .title {{ font-size: 16px; font-weight: 700; color: #f8fafc; }}
        .stats-strip {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        .stat-item {{ display: flex; flex-direction: column; align-items: flex-end; }}
        .stat-label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-val {{ font-size: 14px; font-weight: 700; }}
        .val-profit {{ color: #10b981; }}
        .val-neutral {{ color: #e2e8f0; }}
        .tf-switcher {{
            display: flex;
            background: #0f172a;
            border-radius: 6px;
            padding: 2px;
            border: 1px solid #334155;
            gap: 2px;
        }}
        .tf-btn {{
            background: transparent;
            color: #94a3b8;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .tf-btn.active {{ background: #2563eb; color: #ffffff; }}
        .tf-btn:hover:not(.active) {{ color: #ffffff; background: #1e293b; }}

        main {{
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }}
        #chart-container {{
            flex: 1;
            width: 100%;
            height: 100%;
            position: relative;
        }}
        .chart-hud {{
            position: absolute;
            top: 12px;
            left: 16px;
            z-index: 10;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(51, 65, 85, 0.7);
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 12px;
            font-family: monospace;
            display: flex;
            gap: 12px;
            pointer-events: none;
        }}
        .hud-up {{ color: #10b981; }}
        .hud-down {{ color: #ef4444; }}

        #ledger-drawer {{
            height: 220px;
            background: #0f172a;
            border-top: 1px solid #1e293b;
            display: flex;
            flex-direction: column;
        }}
        .drawer-header {{
            padding: 8px 16px;
            background: #111827;
            border-bottom: 1px solid #1f2937;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            font-weight: 600;
            color: #cbd5e1;
        }}
        .table-wrap {{
            flex: 1;
            overflow-y: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            text-align: left;
        }}
        th {{
            position: sticky;
            top: 0;
            background: #1e293b;
            color: #94a3b8;
            font-weight: 600;
            padding: 6px 12px;
            border-bottom: 1px solid #334155;
            font-size: 11px;
            text-transform: uppercase;
        }}
        td {{
            padding: 6px 12px;
            border-bottom: 1px solid #1e293b;
            color: #e2e8f0;
            font-family: monospace;
        }}
        tr:hover {{ background: #1e293b; cursor: pointer; }}
        .badge-buy {{ background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 2px 6px; border-radius: 4px; font-weight: 700; }}
        .badge-sell {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; padding: 2px 6px; border-radius: 4px; font-weight: 700; }}
        .badge-win {{ color: #10b981; font-weight: 700; }}
        .badge-loss {{ color: #ef4444; font-weight: 700; }}
        .badge-be {{ color: #f59e0b; font-weight: 700; }}
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <span class="badge">Backtest Visualizer</span>
            <div class="title">AK Strategy: USDCAD Market Chart</div>
            <div class="tf-switcher">
                <button class="tf-btn active" id="btn-m1" onclick="switchTimeframe('M1')">M1 (Execution)</button>
                <button class="tf-btn" id="btn-m5" onclick="switchTimeframe('M5')">M5 (Structure)</button>
            </div>
        </div>
        <div class="stats-strip">
            <div class="stat-item">
                <span class="stat-label">Initial Balance</span>
                <span class="stat-val val-neutral">$5,000.00</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Final Balance</span>
                <span class="stat-val val-profit">$5,520.30</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Net Return</span>
                <span class="stat-val val-profit">+10.41% (+18.0R)</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Win Rate</span>
                <span class="stat-val val-neutral">7.89% (9W / 105L)</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Profit Factor</span>
                <span class="stat-val val-profit">1.15</span>
            </div>
        </div>
    </header>

    <main>
        <div class="chart-hud" id="hud">
            <span>O: <span id="hud-o">-</span></span>
            <span>H: <span id="hud-h">-</span></span>
            <span>L: <span id="hud-l">-</span></span>
            <span>C: <span id="hud-c">-</span></span>
        </div>
        <div id="chart-container"></div>
    </main>

    <div id="ledger-drawer">
        <div class="drawer-header">
            <span>Executed Backtest Trades (Click any row to jump chart to that trade)</span>
            <span>Total Trades: {len(trades_data)}</span>
        </div>
        <div class="table-wrap">
            <table id="trades-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Type</th>
                        <th>Entry Time</th>
                        <th>Entry</th>
                        <th>Stop Loss</th>
                        <th>Take Profit</th>
                        <th>Exit Time</th>
                        <th>Exit</th>
                        <th>Reason</th>
                        <th>Realized R</th>
                        <th>Net P&L ($)</th>
                    </tr>
                </thead>
                <tbody>
"""

    for t in trades_data:
        type_badge = f'<span class="badge-buy">BUY</span>' if t["direction"] == "BUY" else f'<span class="badge-sell">SELL</span>'
        pnl_class = "badge-win" if t["pnl_cash"] > 0 else ("badge-be" if t["exit_reason"] == "BE" else "badge-loss")
        pnl_prefix = "+" if t["pnl_cash"] > 0 else ""
        
        html_content += f"""                    <tr onclick="jumpToTrade({t['entry_timestamp']}, {t['entry_price']}, {t['stop_loss']}, {t['take_profit']})">
                        <td>{t['id']}</td>
                        <td>{type_badge}</td>
                        <td>{t['entry_time']}</td>
                        <td>{t['entry_price']:.5f}</td>
                        <td>{t['stop_loss']:.5f}</td>
                        <td>{t['take_profit']:.5f}</td>
                        <td>{t['exit_time']}</td>
                        <td>{t['exit_price']:.5f}</td>
                        <td>{t['exit_reason']}</td>
                        <td class="{pnl_class}">{t['realized_r']:+.1f}R</td>
                        <td class="{pnl_class}">{pnl_prefix}${t['pnl_cash']:.2f}</td>
                    </tr>
"""

    html_content += f"""                </tbody>
            </table>
        </div>
    </div>

    <script>
        const m1Data = {json.dumps(m1_data)};
        const m5Data = {json.dumps(m5_data)};
        const markersData = {json.dumps(markers)};

        let currentTf = 'M1';
        let chart;
        let candleSeries;
        let slLine = null;
        let tpLine = null;
        let entryLine = null;

        function initChart() {{
            const container = document.getElementById('chart-container');
            chart = LightweightCharts.createChart(container, {{
                layout: {{
                    background: {{ type: 'solid', color: '#0b0f19' }},
                    textColor: '#94a3b8',
                }},
                grid: {{
                    vertLines: {{ color: '#1e293b' }},
                    horzLines: {{ color: '#1e293b' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                }},
                rightPriceScale: {{
                    borderColor: '#334155',
                }},
                timeScale: {{
                    borderColor: '#334155',
                    timeVisible: true,
                    secondsVisible: false,
                }},
            }});

            candleSeries = chart.addCandlestickSeries({{
                upColor: '#10b981',
                downColor: '#ef4444',
                borderVisible: false,
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            }});

            candleSeries.setData(m1Data);
            candleSeries.setMarkers(markersData);

            // Auto resize
            window.addEventListener('resize', () => {{
                chart.resize(container.clientWidth, container.clientHeight);
            }});

            // Crosshair move HUD
            chart.subscribeCrosshairMove(param => {{
                if (!param.time || !param.seriesData.get(candleSeries)) {{
                    return;
                }}
                const d = param.seriesData.get(candleSeries);
                document.getElementById('hud-o').innerText = d.open.toFixed(5);
                document.getElementById('hud-h').innerText = d.high.toFixed(5);
                document.getElementById('hud-l').innerText = d.low.toFixed(5);
                document.getElementById('hud-c').innerText = d.close.toFixed(5);
                
                const cEl = document.getElementById('hud-c');
                cEl.className = d.close >= d.open ? 'hud-up' : 'hud-down';
            }});

            chart.timeScale().fitContent();
        }}

        function switchTimeframe(tf) {{
            currentTf = tf;
            document.getElementById('btn-m1').className = tf === 'M1' ? 'tf-btn active' : 'tf-btn';
            document.getElementById('btn-m5').className = tf === 'M5' ? 'tf-btn active' : 'tf-btn';
            
            if (tf === 'M1') {{
                candleSeries.setData(m1Data);
            }} else {{
                candleSeries.setData(m5Data);
            }}
            candleSeries.setMarkers(markersData);
        }}

        function jumpToTrade(timestamp, entry, sl, tp) {{
            // Remove previous lines
            if (entryLine) candleSeries.removePriceLine(entryLine);
            if (slLine) candleSeries.removePriceLine(slLine);
            if (tpLine) candleSeries.removePriceLine(tpLine);

            entryLine = candleSeries.createPriceLine({{
                price: entry,
                color: '#38bdf8',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: 'ENTRY',
            }});

            slLine = candleSeries.createPriceLine({{
                price: sl,
                color: '#ef4444',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'STOP LOSS',
            }});

            tpLine = candleSeries.createPriceLine({{
                price: tp,
                color: '#10b981',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: 'TAKE PROFIT (1:10)',
            }});

            // Center chart on this bar
            chart.timeScale().scrollToPosition(-10, true);
            chart.timeScale().setVisibleRange({{
                from: timestamp - 3600 * 2,
                to: timestamp + 3600 * 4,
            }});
        }}

        window.onload = initChart;
    </script>
</body>
</html>
"""

    out_path = WORKSPACE_ROOT / "docs" / "qa" / "usdcad_visual_chart_backtest.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[3/3] Interactive visual chart created at: {out_path}")


if __name__ == "__main__":
    main()
