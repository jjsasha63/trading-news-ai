import sys
import argparse
from pathlib import Path
from datetime import datetime

_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.features_news import build_features_daily

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    args = ap.parse_args()
    
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    store.init_db()

    build_features_daily(
        store=store,
        start_date=args.start,
        end_date=args.end,
        decision_time_et="10:00",
    )
    print(f"✅ Built features_daily from {args.start} to {args.end}")
