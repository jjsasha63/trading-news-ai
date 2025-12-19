import pandas as pd
from datetime import datetime

class SimpleNewsStrategy:
    def __init__(self, store):
        self.store = store
    
    def generate_signals_live(self, universe, prices):
        today = datetime.utcnow().date().isoformat()
        symbols = list(universe)
        
        if not symbols:
            return pd.DataFrame(columns=['symbol', 'signal', 'confidence'])
        
        with self.store.connect() as con:
            placeholders = ','.join(['?'] * len(symbols))
            query = f'''
                SELECT symbol, news_count, news_sentiment_mean, 
                       news_sentiment_pos, news_sentiment_neg
                FROM features_daily
                WHERE date = ? AND symbol IN ({placeholders})
            '''
            rows = con.execute(query, [today] + symbols).fetchall()
        
        signals = []
        for row in rows:
            symbol, news_count, sentiment_mean, pos, neg = row
            
            if news_count == 0 or symbol not in prices:
                continue
            
            if sentiment_mean > 0.5:
                signals.append({'symbol': symbol, 'signal': 1, 'confidence': sentiment_mean})
            elif sentiment_mean < -0.3:
                signals.append({'symbol': symbol, 'signal': -1, 'confidence': abs(sentiment_mean)})
        
        return pd.DataFrame(signals)
