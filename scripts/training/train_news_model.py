import joblib
import joblib
from pathlib import Path
import pandas as pd
import numpy as np
from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.sentiment_model import NewsSentimentModel

if __name__ == "__main__":
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    
    # Load features + create labels (next day return direction)
    with store.connect() as con:
        df = pd.read_sql("""
        SELECT f.*, p.close as today_close, p_next.close as tomorrow_close
        FROM features_daily f
        JOIN prices_daily p ON f.symbol = p.symbol AND f.date = p.date
        LEFT JOIN prices_daily p_next ON f.symbol = p_next.symbol 
            AND p_next.date = date(f.date, '+1 day')
        WHERE f.date >= '2024-01-01' AND f.date <= '2024-11-01'
        ORDER BY f.symbol, f.date
        """, con)
    
    # Label: tomorrow's return direction (after simulated costs)
    df['next_ret'] = (df['tomorrow_close'] / df['today_close'] - 1)
    df['label'] = (df['next_ret'] > 0).astype(int)  # 1=up, 0=down
    
    feature_cols = [
        'news_count', 'news_sentiment_mean', 'news_sentiment_pos', 
        'news_sentiment_neg', 'news_volume_spike', 'sentiment_change_1d',
        'price_ret1d', 'price_ret5d', 'price_vol5d', 'distance_ma5'
    ]
    
    X = df[feature_cols].fillna(0).values
    y = df['label'].values
    
    # Walk-forward validation
    model = NewsSentimentModel()
    validation = model.walk_forward_validate(
        pd.DataFrame(X, columns=feature_cols), 
        pd.Series(y)
    )
    
    print("Walk-forward validation:")
    print(f"Accuracy: {validation['walk_forward_accuracy']:.3f}")
    print(f"Splits: {validation['splits']}")
    
    # Train final model on all data
    model.fit(X, y)
    
    # Save model
    joblib.dump(model, "models/news_sentiment_v1.pkl")
    print("✅ News model trained and saved")
