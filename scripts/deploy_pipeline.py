#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Step:
    name: str
    rel_script: str
    args: list[str]


def project_root() -> Path:
    # scripts/deploy_pipeline.py -> scripts -> project root
    return Path(__file__).resolve().parent.parent  # robust vs cwd [web:432]


def run_step(py: str, root: Path, step: Step) -> None:
    script_path = root / step.rel_script
    if not script_path.exists():
        raise FileNotFoundError(f"Missing script: {script_path}")

    cmd = [py, str(script_path), *step.args]
    print(f"\n=== {step.name} ===")
    print(" ".join(cmd))

    # check=True => raise CalledProcessError on failure [web:439]
    subprocess.run(cmd, cwd=str(root), check=True, env=os.environ.copy())


def pipeline_steps(start: str, end: str) -> list[Step]:
    # Keep this aligned with your repo scripts
    return [
        Step("Init DB", "scripts/init_db.py", []),
        Step("Backfill universe", "scripts/backfill_universe.py", []),
        Step("Backfill prices", "scripts/backfill_prices.py", ["--provider", "stooq"]),
        Step("Ingest news", "scripts/ingest_news_once.py", []),
        Step("Normalize news", "scripts/normalize_news.py", []),
        Step("Build features", "scripts/build_features.py", []),
        # Optional (only if you have it in your repo)
        Step("Train model (optional)", "scripts/train_news_model.py", []),
        Step("Run backtest (optional)", "scripts/run_backtest.py", ["--start", start, "--end", end]),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end deploy pipeline runner.")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2024-12-01")
    ap.add_argument("--loop", action="store_true", help="Run forever with a sleep interval.")
    ap.add_argument("--sleep-seconds", type=int, default=1800, help="Sleep between loops when --loop is set.")
    ap.add_argument("--skip-train", action="store_true", help="Skip scripts/train_news_model.py if present.")
    ap.add_argument("--skip-backtest", action="store_true", help="Skip scripts/run_backtest.py if present.")
    args = ap.parse_args()

    root = project_root()
    py = sys.executable  # the current interpreter (venv or container)

    print(f"Project root: {root}")
    print(f"Python: {py}")

    while True:
        steps = pipeline_steps(args.start, args.end)

        # Drop optional steps if user requested
        if args.skip_train:
            steps = [s for s in steps if s.rel_script != "scripts/train_news_model.py"]
        if args.skip_backtest:
            steps = [s for s in steps if s.rel_script != "scripts/run_backtest.py"]

        # Drop optional steps if scripts don't exist in this repo
        filtered: list[Step] = []
        for s in steps:
            if (root / s.rel_script).exists():
                filtered.append(s)
            else:
                # Only warn for optional ones; hard-fail on missing core scripts
                if s.rel_script in {"scripts/train_news_model.py", "scripts/run_backtest.py"}:
                    print(f"Skipping missing optional script: {s.rel_script}")
                else:
                    raise FileNotFoundError(f"Required script missing: {root / s.rel_script}")

        try:
            for step in filtered:
                run_step(py, root, step)
        except subprocess.CalledProcessError as e:
            print(f"\nPipeline failed: {e}")
            return e.returncode
        except Exception as e:
            print(f"\nPipeline failed: {e}")
            return 1

        print("\nPipeline finished OK.")

        if not args.loop:
            return 0

        print(f"Sleeping {args.sleep_seconds}s ...")
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
