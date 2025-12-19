#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tna.storage_sqlite import SQLiteStore
from tna.universe_stoxx600 import fetch_stoxx600
from tna.config import Config

def main():
    cfg = Config(db_path="data/tna.sqlite")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    
    today = date.today()
    fetch_stoxx600(store, today)
    print(f"✅ STOXX 600 universe updated")

if __name__ == "__main__":
    main()
