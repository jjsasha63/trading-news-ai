from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
import requests
import pandas as pd

@dataclass
class SP500Constituent:
    symbol: str
    company_name: str
    sector: str
    industry: str

def fetch_sp500_current() -> list[SP500Constituent]:
    WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; trading-news-ai/1.0; +https://github.com/)"
    }
    resp = requests.get(WIKI_SP500_URL, headers=headers, timeout=15)
    resp.raise_for_status()

    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]
    members: list[SP500Constituent] = []
    for _, row in df.iterrows():
        members.append(
            SP500Constituent(
                symbol=row["Symbol"],
                company_name=row["Security"],
                sector=row.get("GICS Sector", "") or "",
                industry=row.get("GICS Sub-Industry", "") or "",
            )
        )
    return members

def universe_snapshot_rows(constituents: list[SP500Constituent] | list[dict], asof: datetime | None = None) -> list[dict]:
    asof = asof or datetime.now(timezone.utc)
    asof_utc = asof.isoformat()
    out: list[dict] = []
    for c in constituents:
        if isinstance(c, dict):
            symbol = c.get("symbol") or c.get("Symbol") or ""
            company_name = c.get("company_name") or c.get("Security") or ""
            sector = c.get("sector") or c.get("GICS Sector") or ""
            industry = c.get("industry") or c.get("GICS Sub-Industry") or ""
        else:
            symbol = getattr(c, "symbol", "")
            company_name = getattr(c, "company_name", "")
            sector = getattr(c, "sector", "")
            industry = getattr(c, "industry", "")
        out.append({
            "symbol": symbol,
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "asof_date_utc": asof_utc,
        })
    return out
