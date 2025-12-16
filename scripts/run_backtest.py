from __future__ import annotations

import sys
from pathlib import Path

from tna.ml_strategy import NewsMLStrategy

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))

#!/usr/bin/env python3

import argparse
import sqlite3
import pandas as pd
import joblib
from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.backtester import DailyBacktester
from tna.baseline_strategy import baseline_momentum


def db_diagnostics(db_path: Path) -> None:
    print("\n--- DB diagnostics ---")
    print(f"DB path: {db_path.resolve()}")

    if not db_path.exists():
        print("DB file does not exist. Run: python scripts/init_db.py")
        return

    con = sqlite3.connect(str(db_path))
    try:
        # Row counts
        for table in ["universe_membership", "prices_daily", "news_raw", "news_normalized"]:
            try:
                n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"{table}: {n:,} rows")
            except Exception as e:
                print(f"{table}: missing or error: {e}")

        # Price date range
        try:
            row = con.execute("SELECT MIN(date), MAX(date) FROM prices_daily").fetchone()
            print(f"prices_daily date range: {row[0]} .. {row[1]}")
        except Exception as e:
            print(f"prices_daily date range: error: {e}")

        # Universe snapshot date + sample symbols
        try:
            asof = con.execute("SELECT MAX(asof_date_utc) FROM universe_membership").fetchone()[0]
            print(f"universe_membership latest asof_date_utc: {asof}")
            sample = con.execute(
                """
                SELECT symbol, company_name
                FROM universe_membership
                WHERE asof_date_utc = (SELECT MAX(asof_date_utc) FROM universe_membership)
                LIMIT 5
                """
            ).fetchall()
            print("universe sample:", sample)
        except Exception as e:
            print(f"universe sample: error: {e}")

        # Price sample rows
        try:
            sample = con.execute(
                "SELECT symbol, date, close FROM prices_daily ORDER BY date DESC LIMIT 5"
            ).fetchall()
            print("prices_daily sample:", sample)
        except Exception as e:
            print(f"prices_daily sample: error: {e}")

    finally:
        con.close()
    print("--- end diagnostics ---\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-01")
    args = parser.parse_args()

    cfg = load_config(args.config)
    db_path = Path(cfg.db_path)

    store = SQLiteStore(db_path=db_path)
    # Load trained news model
    model = joblib.load("models/news_sentiment_v1.pkl")
    strategy = NewsMLStrategy(store, model)

    # Run baseline backtest
    backtester = DailyBacktester(store, strategy.generate_signals)
    out = backtester.run(args.start, args.end)

    print("Backtest Results (metrics):")
    print(out.get("metrics", {}))

    df = out.get("results")
    if df is None or df.empty:
        print("\nNo backtest rows produced (results DataFrame is empty).")
        print("This usually means: no matching close prices in prices_daily for the date range,")
        print("or the app is pointing to a different DB than the one you populated.")
        db_diagnostics(db_path)
        print("Fix checklist:")
        print("1) Re-run: python scripts/backfill_universe.py")
        print("2) Re-run: python scripts/backfill_prices.py")
        print("3) Verify prices_daily has 2024 dates and non-null close values.")
        return

    # Safe printing
    wanted_cols = [c for c in ["date", "equity", "daily_pnl", "alive"] if c in df.columns]
    print(f"\nFinal equity: ${out['final_state'].equity:,.0f}")
    if wanted_cols:
        print(df[wanted_cols].tail())
    else:
        print("Results columns:", list(df.columns))
        print(df.tail())


if __name__ == "__main__":
    main()
