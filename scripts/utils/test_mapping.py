import sys
from pathlib import Path

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.news_normalize import normalize_rows

if __name__ == "__main__":
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    
    universe = store.read_latest_universe()
    raw_rows = store.read_news_raw_unprocessed(limit=20)
    
    if not raw_rows:
        print("No raw news to test. Run ingest_news_once.py first.")
        exit(1)
    
    normalized = normalize_rows(raw_rows[:5], universe)
    
    print("Enhanced mapping test results:")
    print("-" * 80)
    for i, r in enumerate(normalized):
        dbg = r["mapping_debug"]
        print(f"{i+1}. {r['title'][:60]}...")
        print(f"   Tickers: {r['tickers']}")
        
        # Safe access to debug info
        mode = dbg.get('mode', 'unknown')
        confidence = dbg.get('confidence', 'N/A')
        print(f"   Mode: {mode} (confidence: {confidence})")
        
        industry_signals = dbg.get('industry_signals', [])
        if industry_signals:
            print(f"   Industry signals: {industry_signals}")
        print()
