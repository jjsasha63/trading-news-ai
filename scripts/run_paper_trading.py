#!/usr/bin/env python3
"""Run live paper trading"""
import sys
import time
import logging
import joblib
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tna.storage_sqlite import SQLiteStore
from tna.sentiment_model import NewsSentimentModel
from tna.ml_strategy import NewsMLStrategy
from tna.paper_trader import PaperPortfolio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_sp500_current(store, dt):
    """Get current S&P 500 universe"""
    with store.connect() as con:
        sql = """
        SELECT DISTINCT symbol 
        FROM universe_membership 
        WHERE date <= ? 
        ORDER BY date DESC 
        LIMIT 500
        """
        rows = con.execute(sql, [dt.isoformat()]).fetchall()
        return {row[0]: {} for row in rows}

def get_current_prices(store, symbols):
    """Fetch latest prices"""
    with store.connect() as con:
        placeholders = ",".join("?" * len(symbols))
        sql = f"""
        SELECT symbol, close 
        FROM prices_daily 
        WHERE symbol IN ({placeholders})
        ORDER BY date DESC 
        LIMIT {len(symbols)}
        """
        rows = con.execute(sql, symbols).fetchall()
        return dict(rows)

def main():
    db_path = Path("data/tna.sqlite")
    store = SQLiteStore(db_path=db_path)
    
    # Load trained model (same path as backtest)
    model_path = Path("models/news_sentiment_v1.pkl")
    if model_path.exists():
        model = joblib.load(model_path)
        logging.info(f"✅ Loaded model from {model_path}")
    else:
        logging.error(f"❌ Model not found at {model_path}")
        logging.error("Run training first: docker compose exec trader python /app/scripts/train_news_model.py")
        return
    
    strategy = NewsMLStrategy(store, model)
    portfolio = PaperPortfolio(initial_cash=100000)
    
    logging.info("🚀 Starting paper trading...")
    
    while True:
        now = datetime.now()
        today = date.today()
        
        # Only trade during market hours (9:30 AM - 4:00 PM ET)
        hour = now.hour
        if hour < 9 or hour >= 16:
            logging.info(f"💤 Market closed, sleeping... (hour={hour})")
            time.sleep(300)
            continue
        
        # Get universe
        universe = get_sp500_current(store, today)
        if not universe:
            logging.warning("⚠️  No universe data")
            time.sleep(60)
            continue
        
        # Generate signals
        signals = strategy.generate_signals(today, universe)
        if not signals:
            logging.warning("⚠️  No signals generated")
            time.sleep(60)
            continue
        
        # Get prices
        prices = get_current_prices(store, list(signals.keys()))
        
        # Execute trades
        portfolio.execute_signals(signals, prices, now)
        
        # Record equity
        equity = portfolio.record_equity(prices, now)
        
        # Log summary
        summary = portfolio.get_summary()
        logging.info(f"💰 Equity: ${equity:,.0f} | Positions: {summary['num_positions']} | "
                    f"Return: {summary['total_return']:.2%} | Trades: {summary['num_trades']}")
        
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
