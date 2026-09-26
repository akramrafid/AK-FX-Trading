#!/usr/bin/env bash
# =============================================================================
# AK Forex Trading System — Linux / Container Launcher
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "[INFO] Validating production configuration..."
python3 -c "import config; cfg = config.load_config(); print(f'[CONFIG] Loaded symbol: {cfg.symbol}, MT4 dir: {cfg.mt4_files_dir}')"

echo "[INFO] Starting bridge execution loop..."
while true; do
    python3 -m bridge.executor || {
        EXIT_CODE=$?
        echo "[WARNING] Bridge process exited with code $EXIT_CODE. Restarting in 5s..."
        sleep 5
    }
done
