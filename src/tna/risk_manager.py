from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import numpy as np

@dataclass
class RiskMetrics:
    """Current portfolio risk state"""
    equity: float
    peak_equity: float
    current_drawdown_pct: float
    daily_pnl: float
    volatility_5d: float
    gross_exposure: float
    net_exposure: float
    concentration_top3: float  # % in top 3 positions

class DynamicRiskManager:
    """Adaptive risk controls that tighten during drawdowns"""
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.peak_equity = initial_capital
        
        # Base risk limits (when equity at peak)
        self.base_max_position_pct = 0.08  # 8% per position
        self.base_max_exposure = 0.80  # 80% total
        self.base_max_net_exposure = 0.50  # 50% net long/short
        
        # Drawdown thresholds triggering defensive mode [web:6]
        self.dd_levels = {
            0.05: 1.0,    # 0-5% DD: Normal trading
            0.10: 0.75,   # 5-10% DD: Reduce size 25%
            0.15: 0.50,   # 10-15% DD: Reduce size 50%
            0.20: 0.25,   # 15-20% DD: Reduce size 75%
        }
        
    def calculate_drawdown_multiplier(self, equity: float) -> float:
        """Scale down position sizes during drawdowns [web:6]"""
        self.peak_equity = max(self.peak_equity, equity)
        dd = (self.peak_equity - equity) / self.peak_equity
        
        for threshold in sorted(self.dd_levels.keys(), reverse=True):
            if dd >= threshold:
                return self.dd_levels[threshold]
        return 1.0  # No drawdown, full size
    
    def volatility_adjusted_size(self, 
                                 signal_weight: float,
                                 stock_volatility: float,
                                 avg_volatility: float = 0.02) -> float:
        """Scale positions inversely to volatility [web:7]"""
        # Higher vol = smaller position
        vol_ratio = avg_volatility / max(stock_volatility, 0.001)
        vol_adjusted = signal_weight * vol_ratio
        return np.clip(vol_adjusted, -self.base_max_position_pct, 
                       self.base_max_position_pct)
    
    def apply_risk_limits(self, 
                         target_weights: Dict[str, float],
                         metrics: RiskMetrics,
                         stock_vols: Dict[str, float]) -> Dict[str, float]:
        """Apply all risk controls to generate final position sizes"""
        
        # 1. Drawdown-based scaling [web:6]
        dd_multiplier = self.calculate_drawdown_multiplier(metrics.equity)
        
        # 2. Apply volatility adjustment [web:7]
        adjusted = {}
        avg_vol = np.mean(list(stock_vols.values())) if stock_vols else 0.02
        
        for symbol, weight in target_weights.items():
            vol = stock_vols.get(symbol, avg_vol)
            vol_adjusted = self.volatility_adjusted_size(weight, vol, avg_vol)
            adjusted[symbol] = vol_adjusted * dd_multiplier
        
        # 3. Cap per-position size [web:1]
        max_pos = self.base_max_position_pct * dd_multiplier
        for symbol in adjusted:
            adjusted[symbol] = np.clip(adjusted[symbol], -max_pos, max_pos)
        
        # 4. Cap total exposure [web:8]
        total_long = sum(w for w in adjusted.values() if w > 0)
        total_short = abs(sum(w for w in adjusted.values() if w < 0))
        
        max_exposure = self.base_max_exposure * dd_multiplier
        if total_long > max_exposure:
            scale = max_exposure / total_long
            for sym in adjusted:
                if adjusted[sym] > 0:
                    adjusted[sym] *= scale
        
        if total_short > max_exposure:
            scale = max_exposure / total_short
            for sym in adjusted:
                if adjusted[sym] < 0:
                    adjusted[sym] *= scale
        
        # 5. Concentration limits: no more than 30% in top 3 [web:5]
        sorted_positions = sorted(adjusted.items(), 
                                 key=lambda x: abs(x[1]), reverse=True)
        top3_weight = sum(abs(w) for _, w in sorted_positions[:3])
        
        if top3_weight > 0.30:
            scale = 0.30 / top3_weight
            for i in range(3):
                sym, weight = sorted_positions[i]
                adjusted[sym] = weight * scale
        
        return adjusted
    
    def check_circuit_breaker(self, metrics: RiskMetrics) -> bool:
        """Halt trading if daily loss exceeds 10% [web:6]"""
        daily_loss_pct = abs(metrics.daily_pnl / metrics.equity)
        if metrics.daily_pnl < 0 and daily_loss_pct > 0.10:
            return True  # Circuit breaker triggered
        return False
