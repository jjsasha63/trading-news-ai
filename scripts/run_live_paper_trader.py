import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from tna.storage_sqlite import SQLiteStore
from tna.config import load_config
from tna.simple_strategy import SimpleNewsStrategy
from live_broker import LivePaperBroker

def get_latest_prices(symbols: list[str]) -> dict:
    data_client = StockHistoricalDataClient(
        api_key=os.environ["APCA_API_KEY_ID"],
        secret_key=os.environ["APCA_API_SECRET_KEY"]
    )
    
    request_params = StockLatestQuoteRequest(symbol_or_symbols=symbols)
    quotes = data_client.get_stock_latest_quote(request_params)
    
    prices = {}
    for symbol, quote in quotes.items():
        if quote and quote.ask_price:
            prices[symbol] = float(quote.ask_price)
    return prices

def main():
    cfg = load_config("config.yml")
    store = SQLiteStore(Path(cfg.db_path))
    strategy = SimpleNewsStrategy(store)
    broker = LivePaperBroker()
    
    with store.connect() as con:
        rows = con.execute("SELECT DISTINCT symbol FROM universe_membership ORDER BY symbol LIMIT 500").fetchall()
        UNIVERSE = [row[0] for row in rows]
    
    print("Starting live Alpaca paper trader (SIMPLE STRATEGY)...")
    print(f"Universe: {len(UNIVERSE)} stocks")
    print(f"Account equity: {broker.get_portfolio_value()}")
    
    while True:
        now = datetime.utcnow()
        print(f"\n[{now.isoformat()}] Tick...")
        
        prices = get_latest_prices(UNIVERSE)
        print(f"Fetched {len(prices)} prices")
        
        signals = strategy.generate_signals_live(UNIVERSE, prices)
        print(f"Generated {len(signals)} signals")
        
        if not signals.empty:
            print(signals)
            
            # Get existing positions AND pending orders
            existing_positions = {p.symbol for p in broker.get_positions()}
            pending_orders = {o.symbol for o in broker.client.get_orders()}
            already_trading = existing_positions | pending_orders
            
            equity = broker.get_portfolio_value()
            position_value = equity * 0.05  # 5% per position
            
            for _, row in signals.iterrows():
                symbol = row['symbol']
                signal = row['signal']
                
                # Skip if already have position or pending order
                if symbol in already_trading:
                    print(f"⏭️  Skip {symbol} (already trading)")
                    continue
                
                if signal == 1 and symbol in prices:
                    price = prices[symbol]
                    qty = max(1, int(position_value / price))  # Calculate shares
                    
                    try:
                        order = broker.place_order(symbol, "BUY", qty)
                        print(f"✅ BUY {qty} shares of {symbol} @ ${price:.2f}")
                    except Exception as e:
                        print(f"❌ Failed to buy {symbol}: {e}")
                        
                elif signal == -1 and symbol in existing_positions:
                    try:
                        broker.close_position(symbol)
                        print(f"✅ CLOSE {symbol}")
                    except Exception as e:
                        print(f"❌ Failed to close {symbol}: {e}")
        
        print(f"Equity: ${broker.get_portfolio_value():.2f}")
        time.sleep(60)

if __name__ == "__main__":
    main()
