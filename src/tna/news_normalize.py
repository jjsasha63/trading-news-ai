from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

TICKER_RE = re.compile(r"(?:\$(?P<t>[A-Z]{1,5}))\b")

def clean_text(title: str | None, summary: str | None) -> str:
    t = (title or "").strip()
    s = (summary or "").strip()
    text = (t + " " + s).strip()
    text = re.sub(r"\s+", " ", text)
    return text

def extract_tickers_simple(text: str) -> set[str]:
    # Very conservative: $AAPL style only
    return {m.group("t") for m in TICKER_RE.finditer(text)}

def map_to_sp500(text: str, sp500_dict: dict[str, dict]) -> tuple[list[str], dict]:
    """
    v1 mapping:
      1) tickers from $TICKER mentions
      2) if none, attempt company-name substring matches (very conservative)
    """
    debug = {"mode": None, "matches": []}
    tickers = extract_tickers_simple(text)
    if tickers:
        found = sorted([t for t in tickers if t in sp500_dict])
        debug["mode"] = "dollar_ticker"
        debug["matches"] = found
        return found, debug

    # Conservative company-name match: exact word substring for longer unique names
    lowered = text.lower()
    found = []
    for sym, meta in sp500_dict.items():
        name = (meta.get("company_name") or "").strip()
        if len(name) < 8:
            continue
        if name.lower() in lowered:
            found.append(sym)

    found = sorted(set(found))
    debug["mode"] = "company_name_substring" if found else "none"
    debug["matches"] = found[:25]
    return found[:25], debug

def normalize_rows(raw_rows: list[dict], sp500_dict: dict[str, dict]) -> list[dict]:
    out = []
    for r in raw_rows:
        text = clean_text(r.get("title"), r.get("summary"))
        tickers, dbg = map_to_sp500(text, sp500_dict=sp500_dict)

        out.append({
            "id": r["id"],
            "source": r["source"],
            "article_url": r.get("article_url"),
            "published_time_utc": r.get("published_time_utc"),
            "fetched_time_utc": r.get("fetched_time_utc"),
            "title": r.get("title"),
            "summary": r.get("summary"),
            "text_clean": text,
            "tickers": tickers,
            "mapping_debug": dbg,
        })
    return out
