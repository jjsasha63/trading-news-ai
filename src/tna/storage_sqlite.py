from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Any
import json

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS news_raw (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  feed_url TEXT NOT NULL,
  article_url TEXT,
  title TEXT,
  summary TEXT,
  published_time_utc TEXT,
  fetched_time_utc TEXT NOT NULL,
  raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_normalized (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  article_url TEXT,
  published_time_utc TEXT,
  fetched_time_utc TEXT,
  title TEXT,
  summary TEXT,
  text_clean TEXT,
  tickers_json TEXT,
  mapping_debug_json TEXT
);

CREATE TABLE IF NOT EXISTS universe_membership (
  symbol TEXT NOT NULL,
  company_name TEXT,
  sector TEXT,
  industry TEXT,
  asof_date_utc TEXT NOT NULL,
  PRIMARY KEY(symbol, asof_date_utc)
);

CREATE TABLE IF NOT EXISTS prices_daily (
  symbol TEXT NOT NULL,
  date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  adj_close REAL,
  volume REAL,
  PRIMARY KEY(symbol, date)
);

CREATE TABLE IF NOT EXISTS corp_actions (
  symbol TEXT NOT NULL,
  date TEXT NOT NULL,
  action_type TEXT NOT NULL,    -- dividend|split
  value REAL NOT NULL,
  PRIMARY KEY(symbol, date, action_type)
);
"""

@dataclass
class SQLiteStore:
    db_path: Path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    def init_db(self) -> None:
        with self.connect() as con:
            con.executescript(DDL)

    def upsert_news_raw(self, rows: Iterable[dict]) -> int:
        sql = """
        INSERT INTO news_raw(id, source, feed_url, article_url, title, summary,
                             published_time_utc, fetched_time_utc, raw_json)
        VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO NOTHING
        """
        data = []
        for r in rows:
            data.append((
                r["id"], r["source"], r["feed_url"], r.get("article_url"),
                r.get("title"), r.get("summary"),
                r.get("published_time_utc"), r["fetched_time_utc"],
                json.dumps(r, ensure_ascii=False)
            ))
        with self.connect() as con:
            cur = con.executemany(sql, data)
            return cur.rowcount

    def read_news_raw_unprocessed(self, limit: int = 1000) -> list[dict]:
        # Anything not in normalized yet
        sql = """
        SELECT nr.raw_json
        FROM news_raw nr
        LEFT JOIN news_normalized nn ON nn.id = nr.id
        WHERE nn.id IS NULL
        ORDER BY nr.fetched_time_utc ASC
        LIMIT ?
        """
        with self.connect() as con:
            rows = con.execute(sql, (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def upsert_news_normalized(self, rows: Iterable[dict]) -> int:
        sql = """
        INSERT INTO news_normalized(
            id, source, article_url, published_time_utc, fetched_time_utc,
            title, summary, text_clean, tickers_json, mapping_debug_json
        )
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            text_clean=excluded.text_clean,
            tickers_json=excluded.tickers_json,
            mapping_debug_json=excluded.mapping_debug_json
        """
        data = []
        for r in rows:
            data.append((
                r["id"], r["source"], r.get("article_url"),
                r.get("published_time_utc"), r.get("fetched_time_utc"),
                r.get("title"), r.get("summary"),
                r.get("text_clean"),
                json.dumps(r.get("tickers", []), ensure_ascii=False),
                json.dumps(r.get("mapping_debug", {}), ensure_ascii=False),
            ))
        with self.connect() as con:
            cur = con.executemany(sql, data)
            return cur.rowcount

    def upsert_universe_snapshot(self, rows: Iterable[dict]) -> int:
        sql = """
        INSERT INTO universe_membership(symbol, company_name, sector, industry, asof_date_utc)
        VALUES(?,?,?,?,?)
        ON CONFLICT(symbol, asof_date_utc) DO NOTHING
        """
        data = []
        for r in rows:
            data.append((r["symbol"], r.get("company_name"), r.get("sector"), r.get("industry"), r["asof_date_utc"]))
        with self.connect() as con:
            cur = con.executemany(sql, data)
            return cur.rowcount

    def read_latest_universe(self) -> dict[str, dict]:
        sql = """
        SELECT symbol, company_name, sector, industry, asof_date_utc
        FROM universe_membership
        WHERE asof_date_utc = (SELECT MAX(asof_date_utc) FROM universe_membership)
        """
        with self.connect() as con:
            rows = con.execute(sql).fetchall()
        out = {}
        for sym, name, sector, industry, asof in rows:
            out[sym] = {"symbol": sym, "company_name": name or "", "sector": sector or "", "industry": industry or "", "asof_date_utc": asof}
        return out

    def upsert_prices_daily(self, rows: Iterable[dict]) -> int:
        sql = """
        INSERT INTO prices_daily(symbol, date, open, high, low, close, adj_close, volume)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(symbol, date) DO UPDATE SET
            open=excluded.open,
            high=excluded.high,
            low=excluded.low,
            close=excluded.close,
            adj_close=excluded.adj_close,
            volume=excluded.volume
        """
        data = []
        for r in rows:
            data.append((r["symbol"], r["date"], r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("adj_close"), r.get("volume")))
        with self.connect() as con:
            cur = con.executemany(sql, data)
            return cur.rowcount

    def upsert_corp_actions(self, rows: Iterable[dict]) -> int:
        sql = """
        INSERT INTO corp_actions(symbol, date, action_type, value)
        VALUES(?,?,?,?)
        ON CONFLICT(symbol, date, action_type) DO UPDATE SET
            value=excluded.value
        """
        data = []
        for r in rows:
            data.append((r["symbol"], r["date"], r["action_type"], float(r["value"])))
        with self.connect() as con:
            cur = con.executemany(sql, data)
            return cur.rowcount
