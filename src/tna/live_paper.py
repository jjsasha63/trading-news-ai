from __future__ import annotations
import sys
from pathlib import Path

# ensure project src/ is on PYTHONPATH when running scripts directly
_repo_root = Path(__file__).resolve().parents[1]  # repo root (parent of scripts/)
sys.path.insert(0, str(_repo_root / "src"))
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict
import joblib
from pytz import timezone as pytz_tz

from .config import load_config
from .storage_sqlite import SQLiteStore
from .ml_strategy import NewsMLStrategy
from .sentiment_model import NewsSentimentModel
from .portfolio import Portfolio
from .execution import simulate_close_execution
from .events import MarketEvent

class LivePaperTrader:
    def __init__(self, config_path: str):
        self.cfg = load_config(config_path)
        self.store = SQLiteStore(db_path=self.cfg.db_path)
        self.model = joblib.load("models/news_sentiment_v1.pkl")
        self.strategy = NewsMLStrategy(self.store, self.model)
        self.portfolio = Portfolio(initial_cash=100000)
        self.trading_halt = False
        
        self.et_tz = pytz_tz('America/New_York')
    
    async def run_forever(self):
        """Main live trading loop"""
        print("🚀 Live Paper Trader started (10am ET decisions, close execution)")
        
        while not self.trading_halt:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(self.et_tz)
            
            # Decision time check (10am ET)
            if self._is_decision_time(now_et):
                await self._make_daily_decision(now_et.date())
            
            # EOD: check fills if market closed
            if self._is_after_close(now_et):
                await self._process_eod_fills(now_et.date())
            
            await asyncio.sleep(60)  # Check every minute
    
    def _is_decision_time(self, now_et: datetime) -> bool:
        """10:00am ET on trading days"""
        if now_et.weekday() >= 5:  # Weekend
            return False
        
        target = now_et.replace(hour=10, minute=0, second=0, microsecond=0)
        return now_et >= target and now_et < target + timedelta(minutes=5)
    
    def _is_after_close(self, now_et: datetime) -> bool:
        """After 4pm ET on trading days"""
        if now_et.weekday() >= 5:
            return False
        
        close_time = now_et.replace(hour=16, minute=5, second=0)  # 5min after close
        return now_et >= close_time
    
    async def _make_daily_decision(self, date: date):
        """10am ET: ingest news → generate signals → place orders"""
        print(f"🧠 Decision time: {date}")
        
        # Fresh news ingest
        await self._ingest_latest_news()
        
        # Generate signals
        universe = self.store.read_latest_universe()
        signals = self.strategy.generate_signals(date, universe)
        
        print(f"📊 Signals generated: {len(signals)} symbols")
        for sym, weight in sorted(signals.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
            print(f"   {sym}: {weight:.3f}")
        
        # Convert to orders (held until EOD execution)
        self.pending_orders = self._signals_to_orders(signals, self.portfolio.current)
    
    async def _process_eod_fills(self, date: date):
        """4pm ET: get close prices → simulate fills → update portfolio"""
        date_str = date.isoformat()
        
        # Get EOD prices
        universe = self.store.read_latest_universe()
        close_prices = self._get_close_prices(date_str, universe.keys())
        
        if not close_prices or not self.pending_orders:
            return
        
        # Simulate execution
        fills = simulate_close_execution(
            self.pending_orders, close_prices,
            commission_per_share=0.005, spread_bps=2, slippage_bps=1
        )
        
        # Update portfolio + risk checks
        market_event = MarketEvent(date=date, prices=close_prices)
        alive = self.portfolio.update(fills, close_prices, date)
        
        print(f"💰 EOD {date_str}: PnL ${self.portfolio.current.daily_pnl:.2f}, "
              f"Equity ${self.portfolio.current.equity:,.0f}, "
              f"Alive: {alive}")
        
        if not alive:
            print("🛑 RISK LIMITS BREACHED - TRADING HALTED")
            self.trading_halt = True
    
    def _get_close_prices(self, date_str: str, symbols: list[str]) -> Dict[str, float]:
        """Get today's close prices"""
        prices = {}
        with self.store.connect() as con:
            placeholders = ",".join("?" * len(symbols))
            sql = f"""
            SELECT symbol, close FROM prices_daily 
            WHERE date = ? AND symbol IN ({placeholders})
            """
            rows = con.execute(sql, [date_str] + symbols).fetchall()
            for sym, close in rows:
                if close:
                    prices[sym] = float(close)
        return prices
    
    async def _ingest_latest_news(self):
        """Quick news refresh before decision"""
        from .news_rss_ingest import ingest_news_once  # Import here to avoid circular
        ingest_news_once()  # Your existing ingest script
    
    def _signals_to_orders(self, signals: Dict[str, float], portfolio) -> list[dict]:
        """Same logic as backtester"""
        orders = []
        equity = portfolio.equity
        
        for sym, target_weight in signals.items():
            if abs(target_weight) < 0.005:  # No-trade threshold
                continue
            
            current_shares = portfolio.positions.get(sym, 0)
            target_shares = int(target_weight * equity / 100)  # $100/share sizing
            
            if abs(target_shares - current_shares) > 10:  # Min 10 shares
                side = "buy" if target_shares > current_shares else "sell"
                size = abs(target_shares - current_shares)
                orders.append({
                    "date": portfolio.date,
                    "symbol": sym,
                    "side": side,
                    "size_shares": size,
                })
        return orders
