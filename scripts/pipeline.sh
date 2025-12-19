#!/bin/bash
set -e

PROJECT_ROOT=/app
PYTHON=/usr/local/bin/python

cd $PROJECT_ROOT
echo "Project root: $PROJECT_ROOT"
echo "Python: $PYTHON"

# === Init DB ===
echo ""
echo "=== Init DB ==="
$PYTHON /app/scripts/init_db.py

# === Backfill universe ===
echo ""
echo "=== Backfill universe ==="
$PYTHON /app/scripts/backfill_universe.py

# === Backfill prices ===
echo ""
echo "=== Backfill prices ==="
$PYTHON /app/scripts/backfill_prices.py --provider yahoo

# === Ingest news ===
echo ""
echo "=== Ingest news ==="
$PYTHON /app/scripts/ingest_news_once.py

# === Normalize news ===
echo ""
echo "=== Normalize news ==="
$PYTHON /app/scripts/normalize_news.py

# === Build features ===
echo ""
echo "=== Build features ==="
$PYTHON /app/scripts/build_features.py

# === Train model (optional) ===
echo ""
echo "=== Train model (optional) ==="
$PYTHON /app/scripts/train_news_model.py

# === Run backtest (optional) ===
echo ""
echo "=== Run backtest (optional) ==="
$PYTHON /app/scripts/run_backtest.py --start 2024-01-01 --end 2024-12-01

# === Start Alpaca live trading (background) ===
echo ""
echo "=== Starting Alpaca live trader ==="
pkill -f run_live_paper_trader.py 2>/dev/null || true
nohup $PYTHON /app/scripts/run_live_paper_trader.py > /tmp/alpaca_live.log 2>&1 &
echo "Alpaca live trader started (PID: $!)"

echo ""
echo "Pipeline finished OK."
echo "Sleeping 3600s ..."
sleep 3600
