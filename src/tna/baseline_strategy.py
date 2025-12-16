from __future__ import annotations
from datetime import date
from typing import Dict
from .storage_sqlite import SQLiteStore

def baseline_momentum(store: SQLiteStore):
    """Simple 5-day momentum baseline"""
    def generate_signals(dt: date, universe: Dict[str, dict]) -> Dict[str, float]:
        date_str = dt.date().isoformat()
        symbols = list(universe.keys())
        
        # Get last 5 trading days returns
        with store.connect() as con:
            sql = """
            SELECT p1.symbol, 
                   (p1.close - p5.close) / p5.close as ret5d
            FROM prices_daily p1
            LEFT JOIN prices_daily p5 ON p1.symbol = p5.symbol 
                AND p5.date BETWEEN date(?, '-5 days') AND date(?, '-1 days')
            WHERE p1.date = ? AND p1.symbol IN ({})
            """.format(",".join("?" * len(symbols)))
            
            rows = con.execute(sql, [date_str] * 6 + symbols).fetchall()
        
        signals = {}
        for sym, ret5d in rows:
            if ret5d and abs(ret5d) > 0.02:  # 2% threshold
                signals[sym] = 0.1 * (1 if ret5d > 0 else -1)  # ±10% position
        
        return signals
    return generate_signals
