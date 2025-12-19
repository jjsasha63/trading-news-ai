#!/usr/bin/env python3
"""Universal script runner for trading-news-ai"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

if len(sys.argv) < 2:
    print("Usage: python3 run.py <script.py> [args...]")
    print("\nExamples:")
    print("  python3 run.py scripts/utils/init_db.py")
    print("  python3 run.py scripts/trading/run_backtest.py --start 2020-01-01")
    sys.exit(1)

script_path = Path(sys.argv[1]).resolve()

# Copy config.yml if missing
config_file = script_path.parent / 'config.yml'
if not config_file.exists():
    (config_file).write_bytes((Path(__file__).parent / 'config.yml').read_bytes())
    print(f"📋 Copied config.yml to {script_path.parent}")

# Remove run.py from argv, keep script args
sys.argv = sys.argv[1:]

# Execute script
print(f"🚀 Running {script_path.name}")
exec(open(script_path).read(), {'__file__': str(script_path), '__name__': '__main__'})
