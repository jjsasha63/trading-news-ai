from __future__ import annotations
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from live_broker import LivePaperBroker
from rl_agent import RLTradingAgent

load_dotenv()

POLL_INTERVAL_SEC = 300  # 5 minutes (less frequent than supervised model)
UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "WMT"]

def get_latest_prices(symbols):
    """Fetch live prices from Alpaca."""
    data_client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_API_SECRET"],
    )
    req = StockLatestQuoteRequest(symbol_or_symbols=symbols)
    quotes = data_client.get_stock_latest_quote(req)
    prices = {}
    for sym in symbols:
        q = quotes.get(sym)
        if q is not None and q.bid_price and q.ask_price:
            prices[sym] = float((q.bid_price + q.ask_price) / 2.0)
    return prices

def get_latest_features(store, symbols):
    """Get most recent features from database."""
    with store.connect() as con:
        latest_date = con.execute(
            "SELECT MAX(date) FROM features_daily WHERE symbol IN ({})".format(
                ",".join("?" * len(symbols))
            ), symbols
        ).fetchone()[0]
        
        if not latest_date:
            return None, {}
        
        sql = """
        SELECT symbol, news_sentiment_mean, price_ret1d, price_ret5d, price_vol5d
        FROM features_daily 
        WHERE date = ? AND symbol IN ({})
        """.format(",".join("?" * len(symbols)))
        
        rows = con.execute(sql, [latest_date] + symbols).fetchall()
    
    features = {}
    for row in rows:
        features[row[0]] = {
            'news_sentiment': row[1] or 0.0,
            'ret1d': row[2] or 0.0,
            'ret5d': row[3] or 0.0,
            'vol5d': row[4] or 0.0
        }
    
    return latest_date, features

def build_observation(broker, prices, features, universe):
    """Build RL observation matching TradingEnvironment format."""
    # Get portfolio state
    equity = broker.get_portfolio_value()
    account = broker.get_account()
    cash = float(account.cash)
    
    positions = {p.symbol: int(p.qty) for p in broker.list_positions()}
    
    # Build observation: [cash_ratio, then 4 features per stock (20 stocks padded)]
    obs = [cash / equity if equity > 0 else 1.0]
    
    max_stocks = 20
    for i, symbol in enumerate(universe[:max_stocks]):
        price = prices.get(symbol, 0)
        shares = positions.get(symbol, 0)
        position_value = shares * price
        
        # Position weight
        obs.append(position_value / equity if equity > 0 else 0)
        
        # Features
        feat = features.get(symbol, {})
        obs.extend([
            feat.get('ret1d', 0.0),
            feat.get('vol5d', 0.0),
            feat.get('news_sentiment', 0.0)
        ])
    
    # Pad to 20 stocks if needed
    while len(obs) < (1 + max_stocks * 4):
        obs.extend([0.0, 0.0, 0.0, 0.0])
    
    return np.array(obs[:81], dtype=np.float32)  # 1 + 20*4 = 81

def execute_rl_actions(broker, actions, universe, prices):
    """Convert RL agent actions to broker orders."""
    equity = broker.get_portfolio_value()
    positions = {p.symbol: int(p.qty) for p in broker.list_positions()}
    
    for i, symbol in enumerate(universe[:len(actions)]):
        if i >= len(actions):
            break
        
        action = actions[i]
        price = prices.get(symbol)
        if price is None or price <= 0:
            continue
        
        current_shares = positions.get(symbol, 0)
        
        # Action > 0.3: Buy
        if action > 0.3:
            target_value = equity * 0.05 * action
            shares_to_buy = int(target_value / price)
            if shares_to_buy > 0:
                print(f"  BUY {shares_to_buy} {symbol} @${price:.2f} (action={action:.2f})")
                broker.place_market_order(symbol, shares_to_buy, "buy")
        
        # Action < -0.3: Sell
        elif action < -0.3 and current_shares > 0:
            shares_to_sell = int(current_shares * abs(action))
            if shares_to_sell > 0:
                print(f"  SELL {shares_to_sell} {symbol} @${price:.2f} (action={action:.2f})")
                broker.place_market_order(symbol, shares_to_sell, "sell")

def main():
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))
    
    # Load trained RL agent
    model_path = "models/rl_agent_episode_3"
    print(f"Loading RL agent from {model_path}...")
    
    agent = RLTradingAgent(
        db_path=Path(cfg.db_path),
        start_date="2023-01-01",
        end_date="2024-11-01",
        initial_capital=1000
    )
    agent.load(model_path)
    
    broker = LivePaperBroker()
    
    print("\n" + "="*60)
    print("🤖 RL Agent Live Paper Trading")
    print("="*60)
    print(f"Universe: {len(UNIVERSE)} stocks")
    print(f"Starting Equity: ${broker.get_portfolio_value():.2f}")
    print(f"Poll Interval: {POLL_INTERVAL_SEC}s")
    print("="*60 + "\n")
    
    iteration = 0
    
    while True:
        iteration += 1
        now = datetime.now()
        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] Iteration {iteration}")
        print("-" * 60)
        
        # Get live data
        prices = get_latest_prices(UNIVERSE)
        if not prices:
            print("⚠️  No prices available, sleeping...")
            time.sleep(POLL_INTERVAL_SEC)
            continue
        
        latest_date, features = get_latest_features(store, UNIVERSE)
        if not features:
            print("⚠️  No features available, sleeping...")
            time.sleep(POLL_INTERVAL_SEC)
            continue
        
        print(f"Latest features date: {latest_date}")
        print(f"Prices received: {len(prices)} symbols")
        
        # Build observation
        obs = build_observation(broker, prices, features, UNIVERSE)
        
        # Get RL agent decision
        actions = agent.predict(obs)
        
        # Execute trades
        print("\n📊 RL Agent Actions:")
        execute_rl_actions(broker, actions, UNIVERSE, prices)
        
        # Report status
        equity = broker.get_portfolio_value()
        positions = broker.list_positions()
        print(f"\n💰 Portfolio Status:")
        print(f"   Equity: ${equity:.2f}")
        print(f"   Positions: {len(positions)}")
        if positions:
            for p in positions[:5]:  # Show top 5
                print(f"     {p.symbol}: {p.qty} shares @ ${float(p.current_price):.2f}")
        
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
