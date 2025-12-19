import os
from dataclasses import dataclass, field
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

@dataclass
class LivePaperBroker:
    api_key: str = field(default_factory=lambda: os.environ["APCA_API_KEY_ID"])
    api_secret: str = field(default_factory=lambda: os.environ["APCA_API_SECRET_KEY"])
    client: TradingClient = field(init=False)

    def __post_init__(self):
        self.client = TradingClient(self.api_key, self.api_secret, paper=True)

    def get_account(self):
        return self.client.get_account()

    def get_portfolio_value(self):
        acct = self.get_account()
        return float(acct.equity)

    def get_positions(self):
        return self.client.get_all_positions()

    def place_order(self, symbol: str, side: str, qty: int):
        """Place order with share quantity instead of notional."""
        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY
        )
        return self.client.submit_order(order_data=order_data)

    def close_position(self, symbol: str):
        self.client.close_position(symbol)
