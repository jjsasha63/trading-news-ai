#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore

def main():
    config = load_config()
    print("🚀 Trading News AI CLI")
    print(f"Config: {config.db_path}, Provider: {config.price_provider}")
    
    store = SQLiteStore(config.db_path)
    print("✅ Database ready!")

if __name__ == '__main__':
    main()
