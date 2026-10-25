"""config.py
Production configuration management for AK Forex Trading system.

Loads settings from environment variables and optional .env files.
Enforces validation bounds on all trading, risk, and path parameters.
Zero third-party dependencies (pure standard library).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional


def parse_simple_env_file(filepath: Path) -> Dict[str, str]:
    """Parse a basic key=value .env file without external dependencies."""
    env_vars: Dict[str, str] = {}
    if not filepath.is_file():
        return env_vars

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                k = k.strip()
                # Strip inline comment if value is unquoted or after quotes
                if "#" in v:
                    # If value starts with quote, only strip after closing quote
                    if v.startswith(('"', "'")):
                        q = v[0]
                        end_q = v.find(q, 1)
                        if end_q != -1:
                            v = v[1:end_q]
                        else:
                            v = v.split("#")[0].strip().strip("'\"")
                    else:
                        v = v.split("#")[0].strip().strip("'\"")
                else:
                    v = v.strip().strip("'\"")
                env_vars[k] = v
    return env_vars


# Strategy & Compliance Constants (Section 9)
RR_MULTIPLE: int = 10
CONFIRM_CANDLES: int = 3
HTF: list[str] = ["M5", "M15"]
ENTRY_ORDER_TYPE: str = "market"
EQUAL_TOLERANCE_POINTS: float = 0.0
SL_REFERENCE: str = "c1_wick_extreme"
M1_METHODS: list[str] = ["equal", "wick_swap"]

# Strategy Assumptions (Section 10 [A1 - A6])
A1_SWEEP_ON_FORMING_HTF: bool = True                  # [A1] HTF sweep is read on the still-forming candle H
A2_EQUAL_TOLERANCE_POINTS: float = 0.0                 # [A2] Equal tolerance (0 = exact equality at broker precision)
A3_SL_IS_C1_WICK_EXTREME: bool = True                 # [A3] Stop is c1's wick extreme (c1.high for sell, c1.low for buy)
A4_RESET_ON_INTERRUPTION: bool = True                 # [A4] Interrupted run resets and searches again
A5_EXPIRE_ON_HTF_CLOSE: bool = True                   # [A5] Setup expires when sweeping HTF candle closes
A6_L_MUST_BE_IMMEDIATE_PREVIOUS_OPPOSITE: bool = True # [A6] L must be candle right before c1 and opposite colour

# 1-Minute Sell Scenarios 1-4 (SELL_STRATEGY_PROMPT.md §7; trader decisions 2026-10-25)
SELL_ENABLED_SCENARIOS: tuple[int, ...] = (1, 2, 3, 4)
SELL_HTF_EQ_TOL_PIPS: float = 0.0                       # [ASSUMPTION] 0 = HTF highs exactly equal
SELL_LTF_EQ_TOL_PIPS: float = 0.0                       # [ASSUMPTION] 0 = 1m highs exactly equal
SELL_DOJI_BODY_TOL_PIPS: float = 0.0                    # [ASSUMPTION] 0 = open == close ("no body")
SELL_MAX_DOJI_IN_SEQUENCE: int = 1                      # [ASSUMPTION] "an" indecisive candle
SELL_SL_BUFFER_POINTS: int = 1                          # [ASSUMPTION] SL 1 point above B1's high
SELL_B1_MUST_BE_HIGHEST: bool = True                    # [ASSUMPTION] B2/B3 may not exceed B1's high
SELL_HTF_SETUP_EXPIRY_BARS: int = 3                     # [ASSUMPTION] setup armed for 3 HTF candles
SELL_INVALIDATE_ON_CLOSE_ABOVE_HTF_HIGH: bool = False   # [ASSUMPTION] optional cancel rule, off
SELL_LTF_NEAR_HTF_HIGH_PIPS: Optional[float] = None     # [ASSUMPTION] optional proximity filter, off
SELL_MAX_TRADES_PER_SETUP: int = 1                      # [ASSUMPTION] one trade per HTF setup
SELL_MAX_OPEN_POSITIONS: Optional[int] = None           # Trader: no limit (the spec default was 1)
SELL_ENTRY_FILL: str = "next_bar_open"                  # [ASSUMPTION] backtest fill; "b3_close" = Pine
SELL_SAME_BAR_SL_TP: str = "SL_FIRST"                   # [ASSUMPTION] bar data cannot order SL and TP
SELL_MAX_1M_GAP_MINUTES: int = 5                        # Feed outage: no 1m sequence spans a longer gap
SELL_SESSION_START_HOUR: int = 7                        # Trader: London, London-NY and NY sessions (UTC)
SELL_SESSION_END_HOUR: int = 21
SELL_SESSION_WEEKDAYS: tuple[int, ...] = (0, 1, 2, 3, 4)  # Monday-Friday

# Exact 1% Risk Sizing Config Constants (Section 6)
RISK_PERCENT: float = 1.0
RISK_BASIS: str = "balance"
COMMISSION_PER_LOT_ROUND_TURN: float = 7.00
LOT_ROUNDING: str = "floor"
MIN_LOT_POLICY: str = "skip"
BALANCE_MAX_AGE_SECONDS: float = 5.0
RISK_DEVIATION_TOLERANCE_PCT: float = 5.0

# Sizing Assumptions (Section 7 [A1 - A4])
A1_ACCOUNT_CURRENCY: str = "USD"               # [A1] The account currency is USD
A2_COMMISSION_PER_LOT_ROUND_TURN: float = 7.00 # [A2] Commission is $7.00 per lot round-turn, derived from history
A3_RISK_BASIS_IS_BALANCE: bool = True          # [A3] "Balance" means MT4 account balance, not equity
A4_NO_POST_ENTRY_MODIFICATIONS: bool = True    # [A4] No break-even, trailing, partial close or early close


@dataclass
class AppConfig:
    """Consolidated production configuration."""
    # MT4 DWX Directory
    mt4_files_dir: Path

    # Market Strategy
    symbol: str = "EURUSD"
    timeframe: str = "M5"
    strategy_mode: str = "strict_compliance"  # "strict_compliance", "c1_wickswap", "institutional", or "sell_scenarios"
    enable_intrabar_sweep: bool = True  # Enable intrabar sweep detection during HTF formation
    rr_multiple: int = RR_MULTIPLE
    confirm_candles: int = CONFIRM_CANDLES
    htf_timeframes: list[str] = field(default_factory=lambda: list(HTF))
    entry_order_type: str = ENTRY_ORDER_TYPE
    sl_reference: str = SL_REFERENCE
    equal_tolerance_points: float = EQUAL_TOLERANCE_POINTS
    m1_methods: list[str] = field(default_factory=lambda: list(M1_METHODS))
    initial_balance: Decimal = Decimal("10000.00")
    risk_pct: Decimal = Decimal("0.01")  # 1.0%

    # Risk Guardrails
    max_daily_loss_pct: Optional[Decimal] = Decimal("0.03")  # None = unlimited / disabled
    max_open_trades: Optional[int] = 1  # None = unlimited open trades (no position limit)
    max_daily_trades: Optional[int] = None  # None = unlimited daily trades (no trade limits)
    max_spread_pips: Decimal = Decimal("2.5")
    session_filter_enabled: bool = True
    session_start_hour: int = 7   # 07:00 UTC (1:00 PM Local Time UTC+6)
    session_end_hour: int = 18    # 18:00 UTC (12:00 AM / Midnight Local Time UTC+6)
    emergency_halt: bool = False

    # Bridge Tuning
    confirmation_timeout_sec: float = 10.0
    max_heartbeat_age_sec: float = 900.0  # 15 min (3 M5 bars)

    # Database Configuration (SQLite)
    db_enabled: bool = True
    db_path: Path = field(default_factory=lambda: Path("data/trading.db"))

    # Alert Integrations
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    webhook_url: Optional[str] = None

    # MT4 Terminal Executable Path
    mt4_exe_path: Optional[Path] = None

    # Exact 1% Risk Sizing Config (Section 6)
    risk_percent: float = RISK_PERCENT
    risk_basis: str = RISK_BASIS
    commission_per_lot_round_turn: float = COMMISSION_PER_LOT_ROUND_TURN
    lot_rounding: str = LOT_ROUNDING
    min_lot_policy: str = MIN_LOT_POLICY
    balance_max_age_seconds: float = BALANCE_MAX_AGE_SECONDS
    risk_deviation_tolerance_pct: float = RISK_DEVIATION_TOLERANCE_PCT
    allow_post_entry_modifications: bool = not A4_NO_POST_ENTRY_MODIFICATIONS

    def __post_init__(self) -> None:
        self.mt4_files_dir = Path(self.mt4_files_dir).resolve()
        if self.mt4_exe_path:
            self.mt4_exe_path = Path(self.mt4_exe_path).resolve()
        if self.risk_pct <= 0 or self.risk_pct > Decimal("0.05"):
            raise ValueError(f"Risk % must be between 0.001 and 0.05 (got: {self.risk_pct})")
        if self.max_daily_loss_pct is not None:
            if self.max_daily_loss_pct <= 0 or self.max_daily_loss_pct > Decimal("0.10"):
                raise ValueError(f"Daily loss limit must be between 0.01 and 0.10 (got: {self.max_daily_loss_pct})")
        if self.max_open_trades is not None and self.max_open_trades < 1:
            raise ValueError("Max open trades must be >= 1")
        if self.max_daily_trades is not None and self.max_daily_trades < 1:
            raise ValueError("Max daily trades must be >= 1")
        if self.max_spread_pips <= 0:
            raise ValueError("Max spread must be strictly positive")

    @property
    def symbols(self) -> list[str]:
        """Returns list of configured trading symbols."""
        return [s.strip() for s in self.symbol.split(",") if s.strip()]


def load_config(env_file: Optional[str | Path] = None) -> AppConfig:
    """Load and validate configuration from .env and os.environ."""
    env_path = Path(env_file) if env_file else Path(".env")
    file_vars = parse_simple_env_file(env_path)

    def get_var(key: str, default: str) -> str:
        return os.environ.get(key, file_vars.get(key, default))

    # Resolve MT4 Directory
    raw_dir = get_var("MT4_FILES_DIR", "./mt4_files")
    mt4_dir = Path(raw_dir)
    mt4_dir.mkdir(parents=True, exist_ok=True)

    raw_max_open = get_var("MAX_OPEN_TRADES", "1")
    max_open_trades_val: Optional[int] = None
    if raw_max_open and raw_max_open.strip().lower() not in ("0", "none", "unlimited", "null", ""):
        max_open_trades_val = int(raw_max_open)

    raw_max_trades = get_var("MAX_DAILY_TRADES", "")
    max_daily_trades_val: Optional[int] = None
    if raw_max_trades and raw_max_trades.strip().lower() not in ("0", "none", "unlimited", "null", ""):
        max_daily_trades_val = int(raw_max_trades)

    raw_max_loss = get_var("MAX_DAILY_LOSS_PCT", "0.03")
    max_daily_loss_pct_val: Optional[Decimal] = None
    if raw_max_loss and raw_max_loss.strip().lower() not in ("0", "0.0", "none", "unlimited", "null", ""):
        max_daily_loss_pct_val = Decimal(raw_max_loss)

    return AppConfig(
        mt4_files_dir=mt4_dir,
        symbol=get_var("TRADING_SYMBOL", "USDCADm").strip().replace("/", ""),
        timeframe=get_var("TRADING_TIMEFRAME", "M5").upper(),
        strategy_mode=get_var("STRATEGY_MODE", "strict_compliance").strip().lower(),
        enable_intrabar_sweep=get_var("ENABLE_INTRABAR_SWEEP", "true").lower() in ("true", "1", "yes"),
        initial_balance=Decimal(get_var("ACCOUNT_INITIAL_BALANCE", "10000.00")),
        risk_pct=Decimal(get_var("RISK_PER_TRADE_PCT", "0.01")),
        max_daily_loss_pct=max_daily_loss_pct_val,
        max_open_trades=max_open_trades_val,
        max_daily_trades=max_daily_trades_val,
        max_spread_pips=Decimal(get_var("MAX_SPREAD_PIPS", "2.5")),
        session_filter_enabled=get_var("SESSION_FILTER_ENABLED", "true").lower() in ("true", "1", "yes"),
        session_start_hour=int(get_var("SESSION_START_HOUR", "7")),
        session_end_hour=int(get_var("SESSION_END_HOUR", "18")),
        emergency_halt=get_var("EMERGENCY_HALT", "false").lower() in ("true", "1", "yes"),
        confirmation_timeout_sec=float(get_var("CONFIRMATION_TIMEOUT_SEC", "10.0")),
        max_heartbeat_age_sec=float(get_var("MAX_HEARTBEAT_AGE_SEC", "900.0")),
        telegram_token=get_var("TELEGRAM_BOT_TOKEN", "") or None,
        telegram_chat_id=get_var("TELEGRAM_CHAT_ID", "") or None,
        webhook_url=get_var("ALERT_WEBHOOK_URL", "") or None,
        db_enabled=get_var("DB_ENABLED", "true").lower() in ("true", "1", "yes"),
        db_path=Path(get_var("DB_PATH", "data/trading.db")),
        mt4_exe_path=Path(get_var("MT4_EXE_PATH", r"C:\Program Files (x86)\MetaTrader 4\terminal.exe"))
        if get_var("MT4_EXE_PATH", r"C:\Program Files (x86)\MetaTrader 4\terminal.exe").strip()
        else None,
        risk_percent=float(get_var("RISK_PERCENT", str(RISK_PERCENT))),
        risk_basis=get_var("RISK_BASIS", RISK_BASIS),
        commission_per_lot_round_turn=float(get_var("COMMISSION_PER_LOT_ROUND_TURN", str(COMMISSION_PER_LOT_ROUND_TURN))),
        lot_rounding=get_var("LOT_ROUNDING", LOT_ROUNDING),
        min_lot_policy=get_var("MIN_LOT_POLICY", MIN_LOT_POLICY),
        balance_max_age_seconds=float(get_var("BALANCE_MAX_AGE_SECONDS", str(BALANCE_MAX_AGE_SECONDS))),
        risk_deviation_tolerance_pct=float(get_var("RISK_DEVIATION_TOLERANCE_PCT", str(RISK_DEVIATION_TOLERANCE_PCT))),
        allow_post_entry_modifications=get_var("ALLOW_POST_ENTRY_MODIFICATIONS", "false").lower() in ("true", "1", "yes"),
    )
