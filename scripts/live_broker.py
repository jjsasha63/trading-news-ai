from __future__ import annotations
import os
from dataclasses import dataclass, field
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

@dataclass
class LivePaperBroker:
    """
    Wrapper around Alpaca paper trading.
    Your code treats this as the broker; Alpaca simulates fills and PnL.
    """
    api_key: str = field(default_factory=lambda: os.environ["ALPACA_API_KEY"])
    api_secret: str = field(default_factory=lambda: os.environ["ALPACA_API_SECRET"])
    paper: bool = field(default_factory=lambda: os.environ.get("ALPACA_PAPER", "TRUE").upper() == "TRUE")

    def __post_init__(self):
        self.client = TradingClient(self.api_key, self.api_secret, paper=self.paper)

    def get_account(self):
        return self.client.get_account()

    def get_portfolio_value(self) -> float:
        acct = self.get_account()
        return float(acct.equity)

    def list_positions(self):
        return self.client.get_all_positions()

    def place_market_order(self, symbol: str, qty: int, side: str):
        if qty <= 0:
            return None
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        order_req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_req)

    def close_position(self, symbol: str):
        try:
            return self.client.close_position(symbol)
        except Exception:
            return None
