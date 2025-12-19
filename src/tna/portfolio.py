from __future__ import annotations
from copy import copy
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List
import pandas as pd

@dataclass
class PortfolioState:
    date: date
    cash: float
    positions: Dict[str, float]  # symbol → shares
    equity: float
    gross_exposure: float
    net_exposure: float
    daily_pnl: float
    cumulative_pnl: float

class Portfolio:
    def __init__(self, initial_cash: float = 100000):
        self.initial_cash = initial_cash
        self.reset()

    def reset(self):
        self.state_history: List[PortfolioState] = []
        self.current = PortfolioState(
            date=None, cash=self.initial_cash, positions={}, 
            equity=self.initial_cash, gross_exposure=0, net_exposure=0,
            daily_pnl=0, cumulative_pnl=0
        )

    def update(self, fills: List[dict], prices: Dict[str, float], date: date) -> bool:
        """Apply fills, update positions/P&L, check risk limits. Returns True if still alive."""
        
        # Apply fills to positions/cash
        prev_equity = self.current.equity
        prev_daily_pnl = self.current.daily_pnl
        
        for fill in fills:
            sym = fill["symbol"]
            shares = fill["size_shares"] * (1 if fill["side"] == "buy" else -1)
            price = fill["price"]
            cost = abs(shares) * price + fill["commission"] + fill["slippage"]
            
            self.current.cash -= cost if fill["side"] == "buy" else -cost
            self.current.positions[sym] = self.current.positions.get(sym, 0) + shares
        
        # Mark-to-market
        gross_exp = 0
        net_exp = 0
        mkt_val = self.current.cash
        for sym, shares in self.current.positions.items():
            if sym in prices:
                pos_val = abs(shares) * prices[sym]
                gross_exp += pos_val
                net_exp += shares * prices[sym]
                mkt_val += pos_val
        
        self.current.equity = mkt_val
        self.current.gross_exposure = gross_exp / self.current.equity if self.current.equity > 0 else 0
        self.current.net_exposure = net_exp / self.current.equity if self.current.equity > 0 else 0
        self.current.daily_pnl = self.current.equity - prev_equity
        self.current.cumulative_pnl = self.current.equity - self.initial_cash
        self.current.date = date
        
        self.state_history.append(copy(self.current))
        
        # Risk checks (self-destruct)
        return self._check_risk_limits()

    def _check_risk_limits(self) -> bool:
        """Return False if limits breached (liquidate + stop)"""
        cfg = self._get_config()  # from global config
        
        # Daily loss limit (DISABLED for full backtest)
        # if self.current.daily_pnl < -cfg["daily_loss_limit_pct"] * self.initial_cash:
        #     print(f"DAILY LOSS LIMIT breached: {self.current.daily_pnl:.2f}")
        #     self._liquidate_all()
        #     return False
        
        # Max drawdown
        peak = max([s.equity for s in self.state_history])
        drawdown = (peak - self.current.equity) / peak
        # # if drawdown > cfg["max_drawdown_pct"]:
            # # # print(f"MAX DRAWDOWN breached: {drawdown:.2%}")
            # self._liquidate_all()
            # return False
        
        # Exposure limits
        # if self.current.gross_exposure > cfg["max_gross_exposure"]:
            # print(f"GROSS EXPOSURE limit: {self.current.gross_exposure:.2%}")
            # return False
        # if abs(self.current.net_exposure) > cfg["max_net_exposure"]:
            # print(f"NET EXPOSURE limit: {self.current.net_exposure:.2%}")
            # return False
        
        return True

    def _liquidate_all(self):
        """Emergency liquidation"""
        self.current.positions.clear()
        self.current.cash = self.current.equity
        self.current.gross_exposure = 0
        self.current.net_exposure = 0

    def _get_config(self) -> dict:
        # Placeholder - load from config.yml
        return {
            "max_gross_exposure": 1.5,
            "max_net_exposure": 0.5,
            "daily_loss_limit_pct": 0.03,
            "max_drawdown_pct": 0.12,
        }

    def metrics(self) -> dict:
        if not self.state_history:
            return {}
        
        df = pd.DataFrame([s.__dict__ for s in self.state_history])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        
        returns = df["equity"].pct_change().dropna()
        return {
            "total_return": (df["equity"].iloc[-1] / self.initial_cash - 1),
            "cagr": (df["equity"].iloc[-1] / self.initial_cash) ** (252 / len(df)) - 1,
            "sharpe": returns.mean() / returns.std() * (252 ** 0.5) if returns.std() > 0 else 0,
            "max_drawdown": ((df["equity"].cummax() - df["equity"]) / df["equity"].cummax()).max(),
            "avg_daily_pnl": df["daily_pnl"].mean(),
        }
