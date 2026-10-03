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


@dataclass
class AppConfig:
    """Consolidated production configuration."""
    # MT4 DWX Directory
    mt4_files_dir: Path

    # Market Strategy
    symbol: str = "EURUSD"
    timeframe: str = "M5"
    strategy_mode: str = "c1_wickswap"  # "c1_wickswap" (test strategy) or "institutional"
    initial_balance: Decimal = Decimal("10000.00")
    risk_pct: Decimal = Decimal("0.015")  # 1.5%

    # Risk Guardrails
    max_daily_loss_pct: Optional[Decimal] = Decimal("0.03")  # None = unlimited / disabled
    max_open_trades: int = 1
    max_daily_trades: Optional[int] = None  # None = unlimited daily trades (no trade limits)
    max_spread_pips: Decimal = Decimal("2.5")
    session_filter_enabled: bool = True
    session_start_hour: int = 7   # 07:00 UTC (London Open)
    session_end_hour: int = 21    # 21:00 UTC (NY Close)
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

    def __post_init__(self) -> None:
        self.mt4_files_dir = Path(self.mt4_files_dir).resolve()
        if self.risk_pct <= 0 or self.risk_pct > Decimal("0.05"):
            raise ValueError(f"Risk % must be between 0.001 and 0.05 (got: {self.risk_pct})")
        if self.max_daily_loss_pct is not None:
            if self.max_daily_loss_pct <= 0 or self.max_daily_loss_pct > Decimal("0.10"):
                raise ValueError(f"Daily loss limit must be between 0.01 and 0.10 (got: {self.max_daily_loss_pct})")
        if self.max_open_trades < 1:
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
        symbol=get_var("TRADING_SYMBOL", "EURUSD").strip().replace("/", ""),
        timeframe=get_var("TRADING_TIMEFRAME", "M5").upper(),
        strategy_mode=get_var("STRATEGY_MODE", "c1_wickswap").strip().lower(),
        initial_balance=Decimal(get_var("ACCOUNT_INITIAL_BALANCE", "10000.00")),
        risk_pct=Decimal(get_var("RISK_PER_TRADE_PCT", "0.015")),
        max_daily_loss_pct=max_daily_loss_pct_val,
        max_open_trades=int(get_var("MAX_OPEN_TRADES", "1")),
        max_daily_trades=max_daily_trades_val,
        max_spread_pips=Decimal(get_var("MAX_SPREAD_PIPS", "2.5")),
        session_filter_enabled=get_var("SESSION_FILTER_ENABLED", "true").lower() in ("true", "1", "yes"),
        session_start_hour=int(get_var("SESSION_START_HOUR", "7")),
        session_end_hour=int(get_var("SESSION_END_HOUR", "21")),
        emergency_halt=get_var("EMERGENCY_HALT", "false").lower() in ("true", "1", "yes"),
        confirmation_timeout_sec=float(get_var("CONFIRMATION_TIMEOUT_SEC", "10.0")),
        max_heartbeat_age_sec=float(get_var("MAX_HEARTBEAT_AGE_SEC", "900.0")),
        telegram_token=get_var("TELEGRAM_BOT_TOKEN", "") or None,
        telegram_chat_id=get_var("TELEGRAM_CHAT_ID", "") or None,
        webhook_url=get_var("ALERT_WEBHOOK_URL", "") or None,
        db_enabled=get_var("DB_ENABLED", "true").lower() in ("true", "1", "yes"),
        db_path=Path(get_var("DB_PATH", "data/trading.db")),
    )
