from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Config:
    db_path: str
    price_provider: str = "stooq"  # default to working provider
    news_sources: list[str] | None = None


def load_config(path: str = "config.yml") -> Config:
    """Load config with sensible defaults."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(p, "r") as f:
        raw = yaml.safe_load(f) or {}
    
    return Config(
        db_path=raw.get("db_path", "data/tna.sqlite"),
        price_provider=raw.get("price_provider", "stooq"),
        news_sources=raw.get("news_sources", ["bbc_business", "nytimes_business"]),
    )
