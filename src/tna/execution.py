from __future__ import annotations
from typing import List, Dict
import random

def simulate_close_execution(
    orders: List[dict], 
    close_prices: Dict[str, float], 
    commission_per_share: float = 0.005,
    spread_bps: float = 2,      # 2 basis points = 0.02%
    slippage_bps: float = 1,    # 1 basis point slippage
) -> List[dict]:
    """Simulate fills at close with realistic costs"""
    
    fills = []
    for order in orders:
        sym = order["symbol"]
        if sym not in close_prices:
            continue  # Skip invalid symbols
            
        base_price = close_prices[sym]
        
        # Spread: buy at ask, sell at bid
        spread = base_price * spread_bps / 10000
        exec_price = base_price + spread if order["side"] == "buy" else base_price - spread
        
        # Slippage (random walk around execution price)
        slippage = exec_price * slippage_bps / 10000 * random.uniform(-1, 1)
        fill_price = exec_price + slippage
        
        # Commission
        commission = abs(order["size_shares"]) * commission_per_share
        
        fills.append({
            "date": order["date"],
            "symbol": sym,
            "side": order["side"],
            "size_shares": order["size_shares"],
            "price": fill_price,
            "commission": commission,
            "slippage": abs(slippage),
        })
    
    return fills
