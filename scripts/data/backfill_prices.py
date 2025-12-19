from __future__ import annotations

import sys
from pathlib import Path

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))

#!/usr/bin/env python3
"""
Backfill historical price data for the trading universe.
Uses provider configured in config.yml (default: stooq).
"""

import argparse

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.prices_yfinance import download_daily_prices, download_corp_actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-01")
    parser.add_argument("--provider", help="Override config provider: stooq|yfinance|auto")
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = SQLiteStore(db_path=Path(cfg.db_path))
    store.init_db()

    universe = store.read_latest_universe()
    if not universe:
        print("ERROR: Universe is empty. Run: python scripts/backfill_universe.py")
        return 1

    symbols = sorted(universe.keys())
    provider = args.provider or cfg.price_provider

    print(f"Backfilling prices for {len(symbols)} symbols ({args.start} to {args.end})")
    print(f"Provider: {provider}")

    # Download prices
    price_rows = download_daily_prices(
        provider=provider,
        symbols=symbols,
        start=args.start,
        end=args.end,
        progress=False,  # Reduce console spam
    )

    if not price_rows:
        print("WARNING: No price data downloaded. Check provider or date range.")
        return 1

    # Upsert to DB
    n = store.upsert_prices_daily(price_rows)
    print(f"Upserted prices_daily rows: {n:,}")

    # Corp actions (optional, yfinance-only)
    try:
        ca_rows = download_corp_actions(
            symbols=symbols[:50],  # Limit to avoid timeout
            start=args.start,
            end=args.end,
        )
        n_ca = store.upsert_corp_actions(ca_rows)
        print(f"Upserted corp_actions rows: {n_ca} (symbols scanned: 50)")
    except Exception as e:
        print(f"Corp actions failed (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
