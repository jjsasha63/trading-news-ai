import sys
from pathlib import Path

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))

import yaml
from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.news_rss_ingest import fetch_rss_feed, parse_rss
from pathlib import Path as _Path

if __name__ == "__main__":
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    store.init_db()

    allow_path = _Path("sources_allowlist.yml")
    if not allow_path.exists():
        print("sources_allowlist.yml not found — no feeds to ingest. Create the file in the repo root.")
        feeds = []
    else:
        allow = yaml.safe_load(allow_path.read_text(encoding="utf-8"))
        feeds = allow.get("rss_feeds", [])

    all_rows = []
    for f in feeds:
        url = f["url"]
        source = f.get("source", "UNKNOWN")
        try:
            content = fetch_rss_feed(url)
            rows = parse_rss(source=source, feed_url=url, content=content)
            all_rows.extend(rows)
            print(f"Fetched {len(rows)} items from {source} {url}")
        except Exception as e:
            print(f"Failed feed {url}: {e}")

    n = store.upsert_news_raw(all_rows)
    print(f"Inserted news_raw rows: {n} (parsed total: {len(all_rows)})")
