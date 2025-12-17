"""Paper trading engine for live market simulation"""
from datetime import datetime, date
from typing import Dict
import logging

class PaperPortfolio:
    """Simulates a live portfolio for paper trading"""
    
    def __init__(self, initial_cash: float = 100000):
        self.cash = initial_cash
        self.positions = {}  # {symbol: shares}
        self.equity_history = []
        self.trades = []
        
    def execute_signals(self, signals: Dict[str, float], prices: Dict[str, float], dt: datetime):
        """Convert signals to actual positions"""
        total_equity = self.get_total_equity(prices)
        
        # Calculate target dollar amounts
        targets = {}
        for sym, weight in signals.items():
            if sym in prices:
                targets[sym] = total_equity * weight
        
        # Rebalance positions
        for sym, target_value in targets.items():
            current_shares = self.positions.get(sym, 0)
            current_value = current_shares * prices[sym]
            
            # Calculate shares to trade
            delta_value = target_value - current_value
            shares_to_trade = int(delta_value / prices[sym])
            
            if shares_to_trade != 0:
                self._execute_trade(sym, shares_to_trade, prices[sym], dt)
        
        # Close positions not in signals
        for sym in list(self.positions.keys()):
            if sym not in targets and self.positions[sym] != 0:
                self._execute_trade(sym, -self.positions[sym], prices[sym], dt)
    
    def _execute_trade(self, symbol: str, shares: int, price: float, dt: datetime):
        """Execute a single trade"""
        cost = shares * price
        commission = abs(shares) * 0.005  # $0.005 per share
        
        self.cash -= (cost + commission)
        self.positions[symbol] = self.positions.get(symbol, 0) + shares
        
        self.trades.append({
            'datetime': dt,
            'symbol': symbol,
            'shares': shares,
            'price': price,
            'cost': cost,
            'commission': commission
        })
        
        logging.info(f"Paper trade: {shares:+d} {symbol} @ ${price:.2f}")
    
    def get_total_equity(self, prices: Dict[str, float]) -> float:
        """Calculate total portfolio value"""
        position_value = sum(
            shares * prices.get(sym, 0) 
            for sym, shares in self.positions.items()
        )
        return self.cash + position_value
    
    def record_equity(self, prices: Dict[str, float], dt: datetime):
        """Record equity snapshot"""
        equity = self.get_total_equity(prices)
        self.equity_history.append({
            'datetime': dt,
            'equity': equity,
            'cash': self.cash,
            'positions': dict(self.positions)
        })
        return equity
    
    def get_summary(self) -> dict:
        """Get portfolio summary"""
        if not self.equity_history:
            return {}
        
        current = self.equity_history[-1]
        initial = self.equity_history[0]['equity']
        
        return {
            'equity': current['equity'],
            'cash': current['cash'],
            'num_positions': len([p for p in current['positions'].values() if p != 0]),
            'total_return': (current['equity'] - initial) / initial,
            'num_trades': len(self.trades)
        }
