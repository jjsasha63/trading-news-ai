#!/usr/bin/env python3
from pathlib import Path
import sqlite3

from tna.config import load_config

def column_names(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
    return {r[1] for r in rows}

if __name__ == "__main__":
    cfg = load_config("config.yml")
    db_path = Path(cfg.db_path)

    con = sqlite3.connect(str(db_path))
    try:
        # Does table exist?
        tbl = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='features_daily'"
        ).fetchone()

        if not tbl:
            print("features_daily does not exist; nothing to migrate.")
            exit(0)

        cols = column_names(con, "features_daily")

        if "decision_time_utc" not in cols:
            print("Adding column decision_time_utc ...")
            con.execute("ALTER TABLE features_daily ADD COLUMN decision_time_utc TEXT")
            con.commit()
            print("✅ Added decision_time_utc")
        else:
            print("✅ decision_time_utc already exists")

    finally:
        con.close()
