from __future__ import annotations

import sys
from pathlib import Path

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))

import re
from typing import Iterable, Dict, Any
from dataclasses import dataclass
from urllib.parse import urlparse

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.news_normalize import normalize_rows

# Industry → S&P 500 symbols mapping (v1 seed; expand with GICS)
INDUSTRY_MAP = {
    "semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "TXN", "MU", "AVGO"],
    "memory_ram": ["MU", "AVGO"],  # Micron, Broadcom
    "smartphones": ["AAPL", "SSNLF"],  # Apple, Samsung (if in S&P)
    "oil_gas": ["XOM", "CVX", "COP", "SLB"],
    "banking": ["JPM", "BAC", "WFC", "GS", "MS"],
    "tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    # Add more as you discover patterns
}

KEYWORD_INDUSTRY_MAP = {
    "ram shortage": "memory_ram",
    "semiconductor shortage": "semiconductors",
    "oil price": "oil_gas",
    "fed rate": "banking",
    "interest rate": "banking",
    # Expand with common supply chain triggers
}

TICKER_RE = re.compile(r"(?:\$(?P<t>[A-Z]{1,5}))\b")

@dataclass
class MappingDebug:
    mode: str
    direct_tickers: list[str]
    industry_signals: list[str]
    company_matches: list[str]
    confidence: str  # "high", "medium", "low"

def clean_text(title: str | None, summary: str | None) -> str:
    t = (title or "").strip()
    s = (summary or "").strip()
    text = (t + " " + s).strip()
    text = re.sub(r"\s+", " ", text)
    return text.lower()

def extract_direct_tickers(text: str) -> set[str]:
    return {m.group("t") for m in TICKER_RE.finditer(text)}

def detect_industry_signals(text: str) -> list[str]:
    """Find industry-trigger keywords and map to affected sectors"""
    signals = []
    text_lower = text.lower()
    for keyword, industry in KEYWORD_INDUSTRY_MAP.items():
        if keyword in text_lower:
            signals.append(industry)
    return signals

def map_industry_to_symbols(industry_signals: list[str], sp500_symbols: set[str]) -> list[str]:
    found = set()
    for signal in industry_signals:
        if signal in INDUSTRY_MAP:
            found.update(set(INDUSTRY_MAP[signal]) & sp500_symbols)
    return sorted(list(found))

def map_company_names(text: str, sp500_dict: dict[str, dict]) -> list[str]:
    """Conservative company-name substring matching"""
    lowered = text.lower()
    found = []
    for sym, meta in sp500_dict.items():
        name = (meta.get("company_name") or "").strip().lower()
        if len(name) < 8:
            continue
        if name in lowered:
            found.append(sym)
    return sorted(set(found))[:10]

def map_to_sp500_enhanced(
    text: str, 
    sp500_dict: dict[str, dict], 
    sp500_symbols: set[str]
) -> tuple[list[str], MappingDebug]:
    """
    Enhanced mapping: direct tickers → industry signals → company names
    """
    debug = MappingDebug(
        mode="none", direct_tickers=[], industry_signals=[], 
        company_matches=[], confidence="low"
    )
    
    tickers = extract_direct_tickers(text)
    direct = sorted([t for t in tickers if t in sp500_symbols])
    
    if direct:
        debug.mode = "direct_ticker"
        debug.direct_tickers = direct
        debug.confidence = "high"
        return direct, debug
    
    # Industry/supply chain signals
    industry_signals = detect_industry_signals(text)
    if industry_signals:
        industry_symbols = map_industry_to_symbols(industry_signals, sp500_symbols)
        if industry_symbols:
            debug.mode = "industry_signal"
            debug.industry_signals = industry_signals
            debug.confidence = "medium"
            return industry_symbols, debug
    
    # Company name fallback
    company_matches = map_company_names(text, sp500_dict)
    if company_matches:
        debug.mode = "company_name"
        debug.company_matches = company_matches
        debug.confidence = "low"
        return company_matches, debug
    
    return [], debug

def normalize_rows(raw_rows: list[dict], sp500_dict: dict[str, dict]) -> list[dict]:
    sp500_symbols = set(sp500_dict.keys())
    out = []
    
    for r in raw_rows:
        text_raw = clean_text(r.get("title"), r.get("summary"))
        text = text_raw  # already lowercased in clean_text
        
        tickers, dbg = map_to_sp500_enhanced(text, sp500_dict, sp500_symbols)

        out.append({
            "id": r["id"],
            "source": r["source"],
            "article_url": r.get("article_url"),
            "published_time_utc": r.get("published_time_utc"),
            "fetched_time_utc": r.get("fetched_time_utc"),
            "title": r.get("title"),
            "summary": r.get("summary"),
            "text_clean": text_raw,
            "tickers": tickers,
            "mapping_debug": {
                "mode": dbg.mode,
                "direct_tickers": dbg.direct_tickers,
                "industry_signals": dbg.industry_signals,
                "company_matches": dbg.company_matches,
                "confidence": dbg.confidence,
                "sample_text": text_raw[:200] + "..." if len(text_raw) > 200 else text_raw
            },
        })
    return out
