import sys
from pathlib import Path

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore

if __name__ == "__main__":
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    store.init_db()
    print(f"Initialized DB at {cfg.db_path}")
