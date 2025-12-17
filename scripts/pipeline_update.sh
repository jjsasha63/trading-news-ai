# Add paper trading to pipeline (runs in background)
cat >> /app/scripts/pipeline.sh << 'PIPELINE'

# === Start paper trading (background) ===
echo "=== Start paper trading ==="
# Kill any existing paper trader
pkill -f "run_paper_trading.py" || true
# Start new instance in background
nohup $PYTHON /app/scripts/run_paper_trading.py > /tmp/paper_trading.log 2>&1 &
echo "Paper trading started (PID: $!)"
PIPELINE
