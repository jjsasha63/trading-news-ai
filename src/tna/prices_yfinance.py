# src/tna/prices_yfinance.py
from __future__ import annotations

from typing import Any, Iterator
import random
import time

import pandas as pd
import yfinance as yf


# ----------------------------
# Utilities
# ----------------------------

def _chunks(xs: list[str], n: int) -> Iterator[list[str]]:
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _sleep(base: float) -> None:
    time.sleep(base + random.random() * 0.3)


def _safe_float(x: Any) -> float | None:
    try:
        if x is None or pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _to_yf_symbol(sym: str) -> str:
    return sym.strip().replace(".", "-")


def _from_yf_symbol(sym: str) -> str:
    return sym.strip()


# ----------------------------
# Provider: Stooq
# ----------------------------

def _stooq_candidates(symbol: str) -> list[str]:
    """Generate Stooq ticker variants for US stocks."""
    s = symbol.strip().lower()
    cands = [f"{s}.us"]
    
    if "-" in s:
        cands.append(f"{s.replace('-', '.')}.us")
    if "." in s:
        cands.append(f"{s.replace('.', '-')}.us")
    
    seen = set()
    out = []
    for x in cands:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _stooq_download_one(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Download one symbol from Stooq CSV endpoint."""
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)

    for stooq_sym in _stooq_candidates(symbol):
        url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"
        try:
            df = pd.read_csv(url)
        except Exception:
            continue

        if df is None or df.empty or "Date" not in df.columns:
            continue

        df = df.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df[df["date"].notna()].copy()
        df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)].copy()
        
        if df.empty:
            continue

        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        df["adj_close"] = df["close"]
        df["symbol"] = symbol
        df["date"] = df["date"].dt.date.astype(str)
        df = df[["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"]]
        df = df[df["close"].notna()].copy()
        return df

    return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"])


def _stooq_download_many(symbols: list[str], start: str, end: str, pause_seconds: float = 0.15) -> list[dict]:
    """Download multiple symbols from Stooq."""
    rows: list[dict] = []
    failed: list[str] = []

    for i, sym in enumerate(symbols):
        if i > 0 and i % 50 == 0:
            print(f"  Stooq progress: {i}/{len(symbols)} symbols")
        
        df = _stooq_download_one(sym, start, end)
        if df.empty:
            failed.append(sym)
            _sleep(pause_seconds)
            continue

        for r in df.itertuples(index=False):
            rows.append({
                "symbol": r.symbol,
                "date": r.date,
                "open": _safe_float(r.open),
                "high": _safe_float(r.high),
                "low": _safe_float(r.low),
                "close": _safe_float(r.close),
                "adj_close": _safe_float(r.adj_close),
                "volume": None if pd.isna(r.volume) else int(r.volume),
            })

        _sleep(pause_seconds)

    print(f"Stooq: {len(rows)} price rows, {len(failed)} symbols failed")
    
    if failed:
        import os
        os.makedirs("data", exist_ok=True)
        pd.Series(sorted(set(failed))).to_csv("data/failed_tickers_stooq.csv", index=False, header=["symbol"])

    return rows


# ----------------------------
# Provider: yfinance
# ----------------------------

def _yf_normalize_download_df(df: pd.DataFrame, requested: list[str]) -> pd.DataFrame:
    """Normalize yfinance download output to long dataframe."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"])

    out = df.copy()

    if len(requested) == 1 and not isinstance(out.columns, pd.MultiIndex):
        out.columns = pd.MultiIndex.from_product([[requested[0]], out.columns])

    if not isinstance(out.columns, pd.MultiIndex):
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"])

    long = (
        out.stack(level=0, future_stack=True)
           .rename_axis(["date", "symbol"])
           .reset_index()
    )

    long = long.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    })

    for c in ["open", "high", "low", "close", "adj_close", "volume"]:
        if c not in long.columns:
            long[c] = None

    long["date"] = pd.to_datetime(long["date"]).dt.date.astype(str)
    long["symbol"] = long["symbol"].astype(str)

    for c in ["open", "high", "low", "close", "adj_close", "volume"]:
        long[c] = pd.to_numeric(long[c], errors="coerce")

    long = long[long["close"].notna()].copy()
    long = long[long["symbol"].isin(set(requested))].copy()

    return long[["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"]]


# ----------------------------
# Public API
# ----------------------------

def download_daily_prices(
    *,
    provider: str = "yahoo",
    symbols: list[str],
    start: str,
    end: str,
    chunk_size: int = 10,
    pause_seconds: float = 2.0,
    max_retries: int = 6,
    timeout: int = 60,
    threads: bool = False,
    auto_adjust: bool = False,
    progress: bool = False,
) -> list[dict]:
    """
    Download daily OHLCV for prices_daily table.
    
    Provider options:
      - stooq: stable, no rate limits (recommended)
      - yfinance: often rate-limited by Yahoo
      - auto: try yfinance, fallback to stooq
    """
    if not symbols:
        return []

    provider = (provider or "stooq").strip().lower()
    symbols_clean = [s.strip() for s in symbols if s and s.strip()]

    if provider == "stooq":
        print(f"Using Stooq provider for {len(symbols_clean)} symbols")
        return _stooq_download_many(symbols_clean, start, end)

    # yfinance path
    if provider == "yfinance":
        print(f"Using yfinance provider for {len(symbols_clean)} symbols")

    yf_symbols = [_to_yf_symbol(s) for s in symbols_clean]
    all_rows: list[dict] = []
    failures: list[str] = []
    consecutive_all_failed_chunks = 0

    for chunk in _chunks(yf_symbols, chunk_size):
        df_chunk: pd.DataFrame | None = None
        last_err: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                df_chunk = yf.download(
                    tickers=" ".join(chunk),
                    start=start,
                    end=end,
                    interval="1d",
                    group_by="ticker",
                    threads=threads,
                    timeout=timeout,
                    auto_adjust=auto_adjust,
                    progress=progress,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                _sleep(min(60.0, (2.0 ** attempt)))

        long = _yf_normalize_download_df(df_chunk, requested=chunk) if df_chunk is not None else pd.DataFrame()

        if long.empty:
            failures.extend(chunk)
            consecutive_all_failed_chunks += 1
            if last_err is not None:
                print(f"Chunk failed ({len(chunk)} symbols): {last_err}")
            _sleep(pause_seconds)
        else:
            consecutive_all_failed_chunks = 0
            for r in long.itertuples(index=False):
                all_rows.append({
                    "symbol": _from_yf_symbol(r.symbol),
                    "date": r.date,
                    "open": _safe_float(r.open),
                    "high": _safe_float(r.high),
                    "low": _safe_float(r.low),
                    "close": _safe_float(r.close),
                    "adj_close": _safe_float(r.adj_close),
                    "volume": None if pd.isna(r.volume) else int(r.volume),
                })
            _sleep(pause_seconds)

        if provider == "auto" and consecutive_all_failed_chunks >= 2:
            print("yfinance blocked. Falling back to Stooq for remaining symbols.")
            remaining = sorted(set(symbols_clean))
            stooq_rows = _stooq_download_many(remaining, start, end)
            return all_rows + stooq_rows

    if failures:
        import os
        os.makedirs("data", exist_ok=True)
        pd.Series(sorted(set(failures))).to_csv("data/failed_tickers_yfinance.csv", index=False, header=["symbol"])

    return all_rows


def download_corp_actions(
    *,
    symbols: list[str],
    start: str | None = None,
    end: str | None = None,
    max_symbols: int = 50,
    pause_seconds: float = 0.6,
) -> list[dict]:
    """Download dividends/splits via yfinance (non-fatal)."""
    out: list[dict] = []
    if not symbols:
        return out

    for sym in symbols[:max_symbols]:
        yf_sym = _to_yf_symbol(sym)
        try:
            t = yf.Ticker(yf_sym)
            actions = t.actions
            if actions is None or actions.empty:
                _sleep(pause_seconds)
                continue

            actions = actions.copy()
            actions.index = pd.to_datetime(actions.index, errors="coerce")
            actions = actions[actions.index.notna()]

            if start:
                actions = actions[actions.index >= pd.to_datetime(start)]
            if end:
                actions = actions[actions.index <= pd.to_datetime(end)]

            for dt, row in actions.iterrows():
                d = dt.date().isoformat()
                div = row.get("Dividends", 0.0)
                spl = row.get("Stock Splits", 0.0)

                if pd.notna(div) and float(div) != 0.0:
                    out.append({"symbol": sym, "date": d, "action_type": "DIVIDEND", "value": float(div)})
                if pd.notna(spl) and float(spl) != 0.0:
                    out.append({"symbol": sym, "date": d, "action_type": "SPLIT", "value": float(spl)})

        except Exception:
            pass

        _sleep(pause_seconds)

    return out
