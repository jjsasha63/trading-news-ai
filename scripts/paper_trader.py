"""
Paper trading simulator with transaction costs and position limits.
Extends the existing backtesting infrastructure.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List
import pandas as pd
import numpy as np


@dataclass
class Position:
    symbol: str
    shares: int
    avg_cost: float


@dataclass
class SimulatedPortfolio:
    cash: float
    positions: Dict[str, Position]
    transaction_fee_pct: float = 0.001  # 0.1%
    max_position_pct: float = 0.20  # Max 20% per stock
    
    def total_value(self, prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        holdings_value = sum(
            pos.shares * prices.get(pos.symbol, 0) 
            for pos in self.positions.values()
        )
        return self.cash + holdings_value
    
    def can_buy(self, symbol: str, price: float, shares: int) -> bool:
        """Check if trade is allowed."""
        cost = price * shares * (1 + self.transaction_fee_pct)
        if cost > self.cash:
            return False
        
        # Check position limit
        total_value = self.total_value({symbol: price})
        position_value = price * shares
        return (position_value / total_value) <= self.max_position_pct
    
    def execute_buy(self, symbol: str, price: float, shares: int) -> bool:
        """Execute buy order with fees."""
        if not self.can_buy(symbol, price, shares):
            return False
        
        cost = price * shares
        fee = cost * self.transaction_fee_pct
        total_cost = cost + fee
        
        self.cash -= total_cost
        
        if symbol in self.positions:
            pos = self.positions[symbol]
            total_shares = pos.shares + shares
            pos.avg_cost = (pos.avg_cost * pos.shares + cost) / total_shares
            pos.shares = total_shares
        else:
            self.positions[symbol] = Position(symbol, shares, price)
        
        return True
    
    def execute_sell(self, symbol: str, price: float, shares: int) -> bool:
        """Execute sell order with fees."""
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        if pos.shares < shares:
            return False
        
        proceeds = price * shares
        fee = proceeds * self.transaction_fee_pct
        net_proceeds = proceeds - fee
        
        self.cash += net_proceeds
        pos.shares -= shares
        
        if pos.shares == 0:
            del self.positions[symbol]
        
        return True


class PaperTrader:
    """Simulates trading with realistic constraints."""
    
    def __init__(self, db_path: Path, initial_capital: float = 100000):
        self.db_path = db_path
        self.initial_capital = initial_capital
        self.portfolio = SimulatedPortfolio(cash=initial_capital, positions={})
        self.trade_history: List[dict] = []
        
    def run_simulation(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Run paper trading simulation over date range."""
        with sqlite3.connect(str(self.db_path)) as con:
            # Get daily prices
            prices_df = pd.read_sql("""
                SELECT date, symbol, close
                FROM prices_daily
                WHERE date >= ? AND date <= ?
                ORDER BY date, symbol
            """, con, params=(start_date, end_date))
        
        results = []
        
        for date in prices_df['date'].unique():
            day_prices = prices_df[prices_df['date'] == date]
            price_dict = dict(zip(day_prices['symbol'], day_prices['close']))
            
            # Get signals for this date (from your ML model)
            signals = self._get_signals(date)
            
            # Execute trades based on signals
            for signal in signals:
                self._execute_signal(signal, price_dict)
            
            # Record daily portfolio value
            total_value = self.portfolio.total_value(price_dict)
            results.append({
                'date': date,
                'portfolio_value': total_value,
                'cash': self.portfolio.cash,
                'num_positions': len(self.portfolio.positions),
                'daily_return': (total_value / self.initial_capital - 1) if self.initial_capital > 0 else 0
            })
        
        return pd.DataFrame(results)
    
    def _get_signals(self, date: str) -> List[dict]:
        """Placeholder: Get trading signals from ML model."""
        # TODO: Connect to your NewsMLStrategy
        return []
    
    def _execute_signal(self, signal: dict, prices: Dict[str, float]):
        """Execute a trading signal."""
        symbol = signal['symbol']
        action = signal['action']  # 'buy' or 'sell'
        price = prices.get(symbol)
        
        if price is None:
            return
        
        if action == 'buy':
            # Buy shares worth 5% of portfolio
            portfolio_value = self.portfolio.total_value(prices)
            target_value = portfolio_value * 0.05
            shares = int(target_value / price)
            
            if self.portfolio.execute_buy(symbol, price, shares):
                self.trade_history.append({
                    'date': signal['date'],
                    'symbol': symbol,
                    'action': 'buy',
                    'shares': shares,
                    'price': price
                })
        
        elif action == 'sell' and symbol in self.portfolio.positions:
            shares = self.portfolio.positions[symbol].shares
            if self.portfolio.execute_sell(symbol, price, shares):
                self.trade_history.append({
                    'date': signal['date'],
                    'symbol': symbol,
                    'action': 'sell',
                    'shares': shares,
                    'price': price
                })
    
    def save_results(self):
        """Save simulation results to database."""
        with sqlite3.connect(str(self.db_path)) as con:
            # Create table if not exists
            con.execute("""
                CREATE TABLE IF NOT EXISTS simulated_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    symbol TEXT,
                    action TEXT,
                    shares INTEGER,
                    price REAL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert trades
            for trade in self.trade_history:
                con.execute("""
                    INSERT INTO simulated_trades (date, symbol, action, shares, price)
                    VALUES (?, ?, ?, ?, ?)
                """, (trade['date'], trade['symbol'], trade['action'], 
                      trade['shares'], trade['price']))
            
            con.commit()
