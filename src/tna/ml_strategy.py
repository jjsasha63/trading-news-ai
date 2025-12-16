from __future__ import annotations
from datetime import date
from typing import Dict
from .sentiment_model import NewsSentimentModel
from .storage_sqlite import SQLiteStore

class NewsMLStrategy:
    def __init__(self, store: SQLiteStore, model: NewsSentimentModel):
        self.store = store
        self.model = model
    
    def generate_signals(self, dt: date, universe: Dict[str, dict]) -> Dict[str, float]:
        """Generate target weights from news model predictions"""
        date_str = dt.date().isoformat()
        signals = {}
        
        # Get features for all symbols
        with self.store.connect() as con:
            sql = """
            SELECT symbol, news_count, news_sentiment_mean, news_sentiment_pos, 
                   news_sentiment_neg, news_volume_spike, sentiment_change_1d,
                   price_ret1d, price_ret5d, price_vol5d, distance_ma5
            FROM features_daily 
            WHERE date = ? AND symbol IN ({})
            """.format(",".join("?" * len(universe)))
            
            rows = con.execute(sql, [date_str] + list(universe.keys())).fetchall()
        
        for row in rows:
            sym = row[0]
            features = np.array([row[1:]]).reshape(1, -1)  # 1 sample, all features
            
            try:
                prob_up = self.model.predict_proba(features)[0, 1]
                
                # Position sizing: confidence * max position * direction
                confidence = abs(prob_up - 0.5) * 2  # 0-1 scale
                direction = 1 if prob_up > 0.5 else -1
                target_weight = 0.15 * confidence * direction  # Max 15% per name
                
                signals[sym] = target_weight
            except Exception:
                continue
        
        return signals
