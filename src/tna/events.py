from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Dict, Any

@dataclass
class MarketEvent:
    date: date
    prices: Dict[str, float]  # symbol → close price

@dataclass
class SignalEvent:
    date: date
    weights: Dict[str, float]  # symbol → target weight (-1 to +1)

@dataclass
class OrderEvent:
    date: date
    symbol: str
    side: str        # "buy" or "sell"
    size_shares: int  # positive quantity
    price: float     # execution price

@dataclass
class FillEvent:
    date: date
    symbol: str
    side: str
    size_shares: int
    price: float
    commission: float
    slippage: float
