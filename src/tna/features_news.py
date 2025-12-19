# src/tna/features_news.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple
import json
import math

import pandas as pd

from .storage_sqlite import SQLiteStore
from .sentiment_model import simple_sentiment_score


DDL_FEATURES_DAILY = """
CREATE TABLE IF NOT EXISTS features_daily (
  symbol TEXT NOT NULL,
  date TEXT NOT NULL,                      -- decision date (US business day)
  decision_time_utc TEXT NOT NULL,

  -- News features over window (prev_decision_time, decision_time]
  news_count INTEGER NOT NULL,
  news_sentiment_mean REAL NOT NULL,
  news_sentiment_pos REAL NOT NULL,        -- fraction of articles with score > 0
  news_sentiment_neg REAL NOT NULL,        -- fraction of articles with score < 0
  news_volume_spike REAL NOT NULL,         -- count / avg(count last 7d)

  sentiment_change_1d REAL NOT NULL,       -- mean - mean(prev day)

  -- Price features known at decision time (computed from CLOSE up to prior day)
  price_ret1d REAL NOT NULL,
  price_ret5d REAL NOT NULL,
  price_vol5d REAL NOT NULL,
  distance_ma5 REAL NOT NULL,

  PRIMARY KEY(symbol, date)
);
"""


def _parse_iso_utc(ts: str | None) -> pd.Timestamp | None:
    if not ts:
        return None
    t = pd.to_datetime(ts, utc=True, errors="coerce")
    if pd.isna(t):
        return None
    return t


def _business_days(start_date: str, end_date: str) -> pd.DatetimeIndex:
    return pd.date_range(start_date, end_date, freq="B")


def _decision_time_utc_for_day(d: date, decision_time_et: str = "10:00") -> pd.Timestamp:
    hh, mm = map(int, decision_time_et.split(":"))
    dt_et = datetime.combine(d, time(hh, mm), tzinfo=ZoneInfo("America/New_York"))
    return pd.Timestamp(dt_et.astimezone(timezone.utc))


def _ensure_features_table(store: SQLiteStore) -> None:
    with store.connect() as con:
        con.executescript(DDL_FEATURES_DAILY)


def _upsert_features_daily(store: SQLiteStore, rows: List[dict]) -> int:
    sql = """
    INSERT INTO features_daily(
      symbol, date, decision_time_utc,
      news_count, news_sentiment_mean, news_sentiment_pos, news_sentiment_neg, news_volume_spike,
      sentiment_change_1d,
      price_ret1d, price_ret5d, price_vol5d, distance_ma5
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(symbol, date) DO UPDATE SET
      decision_time_utc=excluded.decision_time_utc,
      news_count=excluded.news_count,
      news_sentiment_mean=excluded.news_sentiment_mean,
      news_sentiment_pos=excluded.news_sentiment_pos,
      news_sentiment_neg=excluded.news_sentiment_neg,
      news_volume_spike=excluded.news_volume_spike,
      sentiment_change_1d=excluded.sentiment_change_1d,
      price_ret1d=excluded.price_ret1d,
      price_ret5d=excluded.price_ret5d,
      price_vol5d=excluded.price_vol5d,
      distance_ma5=excluded.distance_ma5
    """
    data = []
    for r in rows:
        data.append((
            r["symbol"], r["date"], r["decision_time_utc"],
            int(r["news_count"]),
            float(r["news_sentiment_mean"]),
            float(r["news_sentiment_pos"]),
            float(r["news_sentiment_neg"]),
            float(r["news_volume_spike"]),
            float(r["sentiment_change_1d"]),
            float(r["price_ret1d"]),
            float(r["price_ret5d"]),
            float(r["price_vol5d"]),
            float(r["distance_ma5"]),
        ))
    with store.connect() as con:
        cur = con.executemany(sql, data)
        return cur.rowcount


def _load_prices(store: SQLiteStore, start_date: str, end_date: str, universe_syms: set[str]) -> pd.DataFrame:
    with store.connect() as con:
        df = pd.read_sql(
            "SELECT symbol, date, close FROM prices_daily WHERE date BETWEEN ? AND ?",
            con,
            params=(start_date, end_date),
        )
    if df.empty:
        return df

    df = df[df["symbol"].isin(universe_syms)].copy()
    df["date"] = pd.to_datetime(df["date"], format="ISO8601")
    df = df.sort_values(["symbol", "date"])
    df = df[df["close"].notna()]
    return df


def _compute_price_features_known_at_decision(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute features from CLOSE history, then shift by 1 row per symbol so that
    features for date D are known at 10:00 ET on D (i.e., last close is D-1).
    """
    if prices.empty:
        return prices

    out = prices.copy()
    out = out.sort_values(["symbol", "date"])
    g = out.groupby("symbol", group_keys=False)

    # Returns
    out["ret1d_raw"] = g["close"].pct_change(1)
    out["ret5d_raw"] = g["close"].pct_change(5)

    # 5-day realized vol of daily returns
    out["vol5d_raw"] = (
        out.groupby("symbol")["ret1d_raw"]
           .rolling(5, min_periods=2)
           .std()
           .reset_index(level=0, drop=True)
    )

    # MA distance
    out["ma5_raw"] = (
        out.groupby("symbol")["close"]
           .rolling(5, min_periods=2)
           .mean()
           .reset_index(level=0, drop=True)
    )
    out["dist_ma5_raw"] = (out["close"] / out["ma5_raw"]) - 1.0

    # Shift forward by 1 trading row per symbol to avoid lookahead
    out["price_ret1d"] = g["ret1d_raw"].shift(1)
    out["price_ret5d"] = g["ret5d_raw"].shift(1)
    out["price_vol5d"] = g["vol5d_raw"].shift(1)
    out["distance_ma5"] = g["dist_ma5_raw"].shift(1)

    feats = out[["symbol", "date", "price_ret1d", "price_ret5d", "price_vol5d", "distance_ma5"]].copy()
    feats["date"] = pd.to_datetime(feats["date"]).dt.date.astype(str)
    return feats.fillna(0.0)



def _load_news(store: SQLiteStore, start_date: str, end_date: str, universe_syms: set[str]) -> pd.DataFrame:
    """
    Load normalized news and explode tickers_json into one row per (article, symbol).
    Note: this uses published_time_utc from the RSS feeds.
    """
    with store.connect() as con:
        df = pd.read_sql(
            """
            SELECT id, source, published_time_utc, fetched_time_utc, title, summary, text_clean, tickers_json
            FROM news_normalized
            """,
            con,
        )

    if df.empty:
        return df

    df["published_ts"] = df["published_time_utc"].apply(_parse_iso_utc)
    df = df[df["published_ts"].notna()].copy()
    if df.empty:
        return df

    # Limit to overall time range (with buffer because we use a rolling window)
    start_ts = pd.to_datetime(start_date, utc=True) - pd.Timedelta(days=3)
    end_ts = pd.to_datetime(end_date, utc=True) + pd.Timedelta(days=3)
    df = df[(df["published_ts"] >= start_ts) & (df["published_ts"] <= end_ts)].copy()

    # Parse tickers_json
    def parse_tickers(x):
        try:
            arr = json.loads(x) if x else []
            if not isinstance(arr, list):
                return []
            return [t for t in arr if t in universe_syms]
        except Exception:
            return []

    df["tickers"] = df["tickers_json"].apply(parse_tickers)
    df = df[df["tickers"].map(len) > 0].copy()
    if df.empty:
        return df

    # Sentiment per article (v1 naive; replace later with FinBERT/LLM)
    df["sentiment"] = df["text_clean"].fillna("").map(simple_sentiment_score)

    # Explode: one row per symbol
    df = df.explode("tickers").rename(columns={"tickers": "symbol"})
    return df[["id", "symbol", "published_ts", "sentiment"]]


def build_features_daily(
    store: SQLiteStore,
    start_date: str,
    end_date: str,
    decision_time_et: str = "10:00",
) -> None:
    """
    Produces features_daily(symbol, date) for each US business day in [start_date, end_date]
    and for each symbol in latest universe snapshot.
    """
    _ensure_features_table(store)

    universe = store.read_latest_universe()
    universe_syms = set(universe.keys())

    # 1) Price features
    prices = _load_prices(store, start_date, end_date, universe_syms)
    if prices.empty:
        raise RuntimeError("prices_daily has no rows for the requested date range/universe.")
    price_feats = _compute_price_features_known_at_decision(prices)

    # 2) News features
    news = _load_news(store, start_date, end_date, universe_syms)
    # news can be empty (that’s allowed); we’ll generate zeros

    # Create decision times per business day (UTC)
    bdays = _business_days(start_date, end_date)
    decision_times = []
    for ts in bdays:
        d = ts.date()
        decision_times.append((d.isoformat(), _decision_time_utc_for_day(d, decision_time_et)))
    decision_df = pd.DataFrame(decision_times, columns=["date", "decision_time_utc"])

    # Build per-day news windows: (prev_decision, this_decision]
    # For the first day we just use last 24h as a fallback.
    decision_df["decision_time_utc_prev"] = decision_df["decision_time_utc"].shift(1)
    decision_df["decision_time_utc_prev"] = decision_df["decision_time_utc_prev"].fillna(
        decision_df["decision_time_utc"] - pd.Timedelta(hours=24)
    )

    # Precompute per (symbol, date) news aggregates
    news_aggs = []
    if not news.empty:
        # For efficient window filtering, sort once
        news = news.sort_values("published_ts")

        # Loop days and filter by window (fast enough for v1; optimize later)
        for _, r in decision_df.iterrows():
            d = r["date"]
            t0 = r["decision_time_utc_prev"]
            t1 = r["decision_time_utc"]
            window = news[(news["published_ts"] > t0) & (news["published_ts"] <= t1)]
            if window.empty:
                continue

            g = window.groupby("symbol")["sentiment"]
            df_day = pd.DataFrame({
                "symbol": g.size().index,
                "date": d,
                "news_count": g.size().values,
                "news_sentiment_mean": g.mean().values,
                "news_sentiment_pos": g.apply(lambda s: float((s > 0).mean())).values,
                "news_sentiment_neg": g.apply(lambda s: float((s < 0).mean())).values,
            })
            news_aggs.append(df_day)

    if news_aggs:
        news_feats = pd.concat(news_aggs, ignore_index=True)
    else:
        news_feats = pd.DataFrame(columns=["symbol", "date", "news_count", "news_sentiment_mean", "news_sentiment_pos", "news_sentiment_neg"])

    # Ensure numeric + fill missing
    for col in ["news_count", "news_sentiment_mean", "news_sentiment_pos", "news_sentiment_neg"]:
        if col in news_feats.columns:
            news_feats[col] = pd.to_numeric(news_feats[col], errors="coerce").fillna(0.0)

    # Build full grid (date x symbol) so missing news becomes zeros
    grid = decision_df.assign(key=1).merge(
        pd.DataFrame({"symbol": sorted(universe_syms), "key": 1}),
        on="key",
        how="inner"
    ).drop(columns=["key"])

    # Join news aggregates
    merged = grid.merge(news_feats, on=["symbol", "date"], how="left")
    merged["news_count"] = merged["news_count"].fillna(0).astype(int)
    merged["news_sentiment_mean"] = merged["news_sentiment_mean"].fillna(0.0)
    merged["news_sentiment_pos"] = merged["news_sentiment_pos"].fillna(0.0)
    merged["news_sentiment_neg"] = merged["news_sentiment_neg"].fillna(0.0)

    # news_volume_spike: count / avg(count last 7 days)
    merged = merged.sort_values(["symbol", "date"])
    merged["news_count_7d_avg"] = (
        merged.groupby("symbol")["news_count"]
        .rolling(7, min_periods=1).mean()
        .reset_index(level=0, drop=True)
    )
    merged["news_volume_spike"] = merged["news_count"] / (merged["news_count_7d_avg"] + 1e-9)

    # sentiment_change_1d
    merged["sentiment_change_1d"] = merged.groupby("symbol")["news_sentiment_mean"].diff(1).fillna(0.0)

    # Join price features (already aligned to be known at decision time)
    merged = merged.merge(price_feats, on=["symbol", "date"], how="left")
    for col in ["price_ret1d", "price_ret5d", "price_vol5d", "distance_ma5"]:
        merged[col] = merged[col].fillna(0.0)

    # Persist to SQLite in batches
    rows = []
    for _, r in merged.iterrows():
        rows.append({
            "symbol": r["symbol"],
            "date": r["date"],
            "decision_time_utc": r["decision_time_utc"].isoformat(),
            "news_count": int(r["news_count"]),
            "news_sentiment_mean": float(r["news_sentiment_mean"]),
            "news_sentiment_pos": float(r["news_sentiment_pos"]),
            "news_sentiment_neg": float(r["news_sentiment_neg"]),
            "news_volume_spike": float(r["news_volume_spike"]),
            "sentiment_change_1d": float(r["sentiment_change_1d"]),
            "price_ret1d": float(r["price_ret1d"]),
            "price_ret5d": float(r["price_ret5d"]),
            "price_vol5d": float(r["price_vol5d"]),
            "distance_ma5": float(r["distance_ma5"]),
        })

    batch = 5000
    total = 0
    for i in range(0, len(rows), batch):
        total += _upsert_features_daily(store, rows[i:i + batch])
    print(f"features_daily upserted rows: {total:,} (grid size: {len(rows):,})")
