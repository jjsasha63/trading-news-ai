from __future__ import annotations
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

import joblib
from tna.config import load_config
from tna.storage_sqlite import SQLiteStore
from tna.ml_strategy import NewsMLStrategy
from live_broker import LivePaperBroker

load_dotenv()

POLL_INTERVAL_SEC = 60
UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]

def get_latest_prices(symbols):
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

def main():
    cfg = load_config("config.yml")
    store = SQLiteStore(db_path=Path(cfg.db_path))

    # LOAD MODEL AND PASS INTO STRATEGY
    model = joblib.load("models/news_sentiment_v1.pkl")
    strategy = NewsMLStrategy(store, model)

    broker = LivePaperBroker()

    print("Starting live Alpaca paper trader...")
    print("Universe:", UNIVERSE)
    print("Account equity:", broker.get_portfolio_value())

    while True:
        now = datetime.utcnow()
        print(f"\n[{now.isoformat()}] Tick...")

        prices = get_latest_prices(UNIVERSE)
        if not prices:
            print("No prices, sleeping...")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        # Until implemented, just sleep
        if not hasattr(strategy, "generate_signals_live"):
            print("generate_signals_live not implemented yet; sleeping...")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        signals_df = strategy.generate_signals_live(UNIVERSE, prices)

        for _, row in signals_df.iterrows():
            sym = row["symbol"]
            sig = row["signal"]       # 1=buy, -1=sell, 0=hold
            conf = row.get("confidence", 0.0)
            px = prices.get(sym)

            if px is None:
                continue

            if sig == 1:
                equity = broker.get_portfolio_value()
                target_notional = equity * 0.02 * max(0.1, min(conf, 1.0))
                qty = int(target_notional / px)
                if qty > 0:
                    print(f"BUY {qty} {sym} @~{px:.2f} (conf={conf:.2f})")
                    broker.place_market_order(sym, qty, "buy")

            elif sig == -1:
                print(f"CLOSE {sym} (conf={conf:.2f})")
                broker.close_position(sym)

        print("Equity now:", broker.get_portfolio_value())
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
