from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import feedparser
from dateutil import parser as dtparser

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_parse_time_to_utc_iso(value: Any) -> str | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None

def _make_id(source: str, link: str | None, published_utc: str | None, title: str | None) -> str:
    raw = f"{source}|{link or ''}|{published_utc or ''}|{title or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; trading-news-ai/1.0)"})
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

def fetch_rss_feed(url: str, timeout: int = 15) -> str:
    """
    Fetch RSS feed content as text using a browser-like User-Agent and retries.
    Returns raw feed text.
    """
    session = _make_session()
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text

def parse_rss(source: str, feed_url: str, content: bytes, fetched_time_utc: str | None = None) -> list[dict]:
    fetched_time_utc = fetched_time_utc or _utc_now_iso()
    parsed = feedparser.parse(content)
    out: list[dict] = []

    for e in parsed.entries:
        title = getattr(e, "title", None)
        link = getattr(e, "link", None)
        summary = getattr(e, "summary", None) or getattr(e, "description", None)

        published = getattr(e, "published", None) or getattr(e, "updated", None) or getattr(e, "pubDate", None)
        published_utc = _safe_parse_time_to_utc_iso(published)

        _id = _make_id(source=source, link=link, published_utc=published_utc, title=title)

        out.append({
            "id": _id,
            "source": source,
            "feed_url": feed_url,
            "article_url": link,
            "title": title,
            "summary": summary,
            "published_time_utc": published_utc,
            "fetched_time_utc": fetched_time_utc,
            "entry": {k: str(v) for k, v in dict(e).items() if k not in ("summary_detail", "content")},
        })
    return out
