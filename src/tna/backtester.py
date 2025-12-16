# src/tna/backtester.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List, Iterable, Any

import pandas as pd

from .events import MarketEvent
from .portfolio import Portfolio
from .execution import simulate_close_execution
from .storage_sqlite import SQLiteStore


def _chunks(xs: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


class DailyBacktester:
    """
    Daily event-driven backtester:
      - Load close prices for day D
      - Ask strategy for target weights (signals) at day D
      - Convert signals -> orders
      - Execute orders at close (with spread/slippage/commissions)
      - Update portfolio and enforce risk limits

    NOTE:
    - Strategy function signature:
        signals = signal_generator(dt: datetime.date, universe: dict[str, dict]) -> dict[str, float]
      where signals are target weights in [-1, +1] (approximately).
    """

    def __init__(
        self,
        store: SQLiteStore,
        signal_generator: Callable[[date, Dict[str, dict]], Dict[str, float]],
        initial_cash: float = 100_000.0,
        commission_per_share: float = 0.005,
        spread_bps: float = 2.0,
        slippage_bps: float = 1.0,
        in_clause_chunk: int = 400,
    ):
        self.store = store
        self.signal_generator = signal_generator
        self.portfolio = Portfolio(initial_cash=initial_cash)

        self.commission_per_share = float(commission_per_share)
        self.spread_bps = float(spread_bps)
        self.slippage_bps = float(slippage_bps)
        self.in_clause_chunk = int(in_clause_chunk)

    def run(self, start_date: str, end_date: str) -> dict:
        self.portfolio.reset()

        # Business days; real trading calendar/holidays can be added later
        dates = pd.date_range(start_date, end_date, freq="B")

        universe = self.store.read_latest_universe()
        symbols = list(universe.keys())  # IMPORTANT: dict_keys -> list [web:208][web:211]

        results: List[dict] = []

        for ts in dates:
            d: date = ts.date()
            d_str = d.isoformat()

            # 1) Market data (close prices for this day)
            prices = self._get_close_prices_for_date(d_str, symbols)
            if not prices:
                # No data (holiday / missing)
                continue

            market_event = MarketEvent(date=d, prices=prices)

            # 2) Signals from strategy (target weights)
            signals = self.signal_generator(market_event.date, universe) or {}

            # 3) Convert signals -> orders
            orders = self._signals_to_orders(
                dt=market_event.date,
                signals=signals,
                close_prices=market_event.prices,
            )

            # 4) Execute orders at close (simulation)
            fills = simulate_close_execution(
                orders=orders,
                close_prices=market_event.prices,
                commission_per_share=self.commission_per_share,
                spread_bps=self.spread_bps,
                slippage_bps=self.slippage_bps,
            )

            # 5) Portfolio update + risk checks
            alive = self.portfolio.update(fills=fills, prices=market_event.prices, date=market_event.date)

            results.append(
                {
                    "date": d_str,
                    "equity": self.portfolio.current.equity,
                    "cash": self.portfolio.current.cash,
                    "gross_exposure": self.portfolio.current.gross_exposure,
                    "net_exposure": self.portfolio.current.net_exposure,
                    "daily_pnl": self.portfolio.current.daily_pnl,
                    "alive": bool(alive),
                    "n_orders": len(orders),
                    "n_fills": len(fills),
                }
            )

            if not alive:
                print(f"BACKTEST TERMINATED on {d_str}: risk limits breached")
                break

        return {
            "results": pd.DataFrame(results),
            "metrics": self.portfolio.metrics(),
            "final_state": self.portfolio.current,
        }

    def _get_close_prices_for_date(self, date_str: str, symbols: List[str]) -> Dict[str, float]:
        """
        Reads close prices for a given date and list of symbols.
        Chunks the IN clause to avoid large parameter lists in sqlite3. [web:222][web:223]
        """
        symbols = list(symbols)
        if not symbols:
            return {}

        prices: Dict[str, float] = {}
        with self.store.connect() as con:
            for chunk in _chunks(symbols, self.in_clause_chunk):
                placeholders = ",".join("?" * len(chunk))
                sql = f"""
                    SELECT symbol, close
                    FROM prices_daily
                    WHERE date = ? AND symbol IN ({placeholders})
                """
                # sqlite3 binds parameters positionally to '?' placeholders. [web:223]
                rows = con.execute(sql, [date_str] + chunk).fetchall()
                for sym, close in rows:
                    if close is not None:
                        prices[str(sym)] = float(close)
        return prices

    def _signals_to_orders(
        self,
        dt: date,
        signals: Dict[str, float],
        close_prices: Dict[str, float],
    ) -> List[dict]:
        """
        Convert target weights into share orders.

        This v1 implementation:
        - Uses close price for sizing (since we're executing at close)
        - Tries to move current position weight toward target weight
        - Applies a no-trade threshold and a min-share threshold
        """
        orders: List[dict] = []
        equity = float(self.portfolio.current.equity)
        if equity <= 0:
            return orders

        no_trade_weight = 0.005     # ignore tiny target weights
        min_shares = 10             # ignore very small trades

        for sym, target_weight in (signals or {}).items():
            if sym not in close_prices:
                continue

            tw = float(target_weight)
            if abs(tw) < no_trade_weight:
                continue

            px = float(close_prices[sym])
            if px <= 0:
                continue

            # Current shares
            cur_shares = float(self.portfolio.current.positions.get(sym, 0.0))

            # Target dollar exposure = weight * equity
            target_dollars = tw * equity

            # Convert to target shares
            target_shares = int(target_dollars / px)

            delta = target_shares - int(cur_shares)
            if abs(delta) < min_shares:
                continue

            side = "buy" if delta > 0 else "sell"
            size = abs(delta)

            orders.append(
                {
                    "date": dt,
                    "symbol": sym,
                    "side": side,
                    "size_shares": int(size),
                }
            )

        return orders
