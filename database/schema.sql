-- =============================================================================
-- AK Forex Trading System — PostgreSQL Database Schema
-- Production DDL for Market Data, Signals, Execution Telemetry, and Journaling
--
-- INVARIANTS:
-- 1. All financial values (prices, balances, lots) use NUMERIC. Zero floating point.
-- 2. All timestamps use TIMESTAMPTZ (stored in UTC).
-- 3. Composite uniqueness on (symbol, timeframe, timestamp) for candles.
-- 4. Idempotency enforced on client_order_id and mt4_ticket.
-- =============================================================================

CREATE TABLE IF NOT EXISTS candles (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(16) NOT NULL,
    timeframe VARCHAR(8) NOT NULL DEFAULT 'M5',
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC(14, 5) NOT NULL,
    high NUMERIC(14, 5) NOT NULL,
    low NUMERIC(14, 5) NOT NULL,
    close NUMERIC(14, 5) NOT NULL,
    volume NUMERIC(16, 2) NOT NULL DEFAULT 0.0,
    is_closed BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_candles_symbol_timeframe_timestamp UNIQUE (symbol, timeframe, timestamp),
    CONSTRAINT chk_candle_high_bounds CHECK (high >= open AND high >= close),
    CONSTRAINT chk_candle_low_bounds CHECK (low <= open AND low <= close)
);

CREATE INDEX IF NOT EXISTS idx_candles_lookup 
    ON candles (symbol, timeframe, timestamp DESC);

-- -----------------------------------------------------------------------------
-- Sweep Events
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sweep_events (
    id BIGSERIAL PRIMARY KEY,
    candle_id BIGINT REFERENCES candles(id) ON DELETE SET NULL,
    symbol VARCHAR(16) NOT NULL,
    timeframe VARCHAR(8) NOT NULL DEFAULT 'M5',
    timestamp TIMESTAMPTZ NOT NULL,
    direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    sweep_type VARCHAR(16) NOT NULL CHECK (sweep_type IN ('VARIANT_A', 'VARIANT_B')),
    swept_price NUMERIC(14, 5) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'CONFIRMED', 'INVALIDATED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sweep_events_timestamp 
    ON sweep_events (symbol, timestamp DESC);

-- -----------------------------------------------------------------------------
-- Trade Signals
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trade_signals (
    id BIGSERIAL PRIMARY KEY,
    sweep_id BIGINT REFERENCES sweep_events(id) ON DELETE SET NULL,
    symbol VARCHAR(16) NOT NULL,
    timeframe VARCHAR(8) NOT NULL DEFAULT 'M5',
    direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    entry_price NUMERIC(14, 5) NOT NULL,
    stop_loss NUMERIC(14, 5) NOT NULL,
    take_profit NUMERIC(14, 5) NOT NULL,
    risk_distance NUMERIC(14, 5) NOT NULL,
    reward_distance NUMERIC(14, 5) NOT NULL,
    rr_ratio NUMERIC(6, 2) NOT NULL DEFAULT 10.00,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_rr_ratio CHECK (rr_ratio >= 9.99 AND rr_ratio <= 10.01)
);

CREATE INDEX IF NOT EXISTS idx_signals_timestamp 
    ON trade_signals (symbol, timestamp DESC);

-- -----------------------------------------------------------------------------
-- Orders
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    client_order_id VARCHAR(64) UNIQUE NOT NULL,
    signal_id BIGINT REFERENCES trade_signals(id) ON DELETE SET NULL,
    symbol VARCHAR(16) NOT NULL,
    direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    lots NUMERIC(8, 2) NOT NULL CHECK (lots >= 0.01),
    target_entry NUMERIC(14, 5) NOT NULL,
    stop_loss NUMERIC(14, 5) NOT NULL,
    take_profit NUMERIC(14, 5) NOT NULL,
    magic_number INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'SUBMITTED' 
        CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'REJECTED', 'CANCELLED', 'CLOSED')),
    risk_rejected_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_status 
    ON orders (status, created_at DESC);

-- -----------------------------------------------------------------------------
-- Fills (Live & Demo Execution Tracking)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fills (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
    mt4_ticket INTEGER UNIQUE NOT NULL,
    fill_price NUMERIC(14, 5) NOT NULL,
    fill_time TIMESTAMPTZ NOT NULL,
    slippage_pips NUMERIC(8, 2) NOT NULL DEFAULT 0.0,
    commission NUMERIC(10, 2) NOT NULL DEFAULT 0.0,
    swap NUMERIC(10, 2) NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Comprehensive Trade Journal (Telemetry for Backtest, Demo & Live)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trade_journal (
    id BIGSERIAL PRIMARY KEY,
    mt4_ticket INTEGER UNIQUE,
    symbol VARCHAR(16) NOT NULL,
    direction VARCHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    open_time TIMESTAMPTZ NOT NULL,
    close_time TIMESTAMPTZ,
    open_price NUMERIC(14, 5) NOT NULL,
    close_price NUMERIC(14, 5),
    stop_loss NUMERIC(14, 5) NOT NULL,
    take_profit NUMERIC(14, 5) NOT NULL,
    lots NUMERIC(8, 2) NOT NULL,
    realized_pnl_currency NUMERIC(14, 2),
    realized_pnl_pips NUMERIC(10, 2),
    realized_r NUMERIC(8, 2),
    exit_reason VARCHAR(16) CHECK (exit_reason IN ('TP', 'SL', 'CIRCUIT_BREAKER', 'MANUAL', 'END_OF_DATA')),
    environment VARCHAR(8) NOT NULL CHECK (environment IN ('BACKTEST', 'DEMO', 'LIVE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_journal_env_date 
    ON trade_journal (environment, open_time DESC);

-- -----------------------------------------------------------------------------
-- Daily Performance Metrics & Circuit Breaker Tracking
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_metrics (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE UNIQUE NOT NULL,
    environment VARCHAR(8) NOT NULL DEFAULT 'LIVE' CHECK (environment IN ('BACKTEST', 'DEMO', 'LIVE')),
    starting_balance NUMERIC(14, 2) NOT NULL,
    ending_balance NUMERIC(14, 2) NOT NULL,
    realized_pnl NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    win_count INTEGER NOT NULL DEFAULT 0,
    loss_count INTEGER NOT NULL DEFAULT 0,
    max_drawdown_pct NUMERIC(6, 2) NOT NULL DEFAULT 0.0,
    circuit_breaker_tripped BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Append-Only Audit Log
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    source_component VARCHAR(32) NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event_time 
    ON audit_logs (event_type, created_at DESC);
