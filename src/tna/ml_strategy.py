from datetime import date
from typing import Dict, Any

class NewsMLStrategy:
    """ML strategy that generates signals based on news sentiment"""
    
    def __init__(self, store, model):
        self.store = store
        self.model = model
        from .risk_manager import DynamicRiskManager
        self.risk_manager = DynamicRiskManager(initial_capital=100000)
    
    def generate_signals(self, dt: date, universe: Dict[str, Any]) -> Dict[str, float]:
        """Generate position weights for each symbol based on ML predictions"""
        symbols = list(universe.keys())
        if not symbols:
            return {}
        
        # Fetch ALL 10 features in correct order
        with self.store.connect() as con:
            placeholders = ",".join("?" * len(symbols))
            sql = f"""
            SELECT symbol, 
                   news_count, news_sentiment_mean, news_sentiment_pos, 
                   news_sentiment_neg, news_volume_spike, sentiment_change_1d,
                   price_ret1d, price_ret5d, price_vol5d, distance_ma5
            FROM features_daily
            WHERE date = ? AND symbol IN ({placeholders})
            """
            rows = con.execute(sql, [dt.isoformat()] + symbols).fetchall()
        
        if not rows:
            return {}
        
        # Build feature matrix with all 10 features
        X = []
        sym_order = []
        for row in rows:
            sym_order.append(row[0])
            X.append([
                row[1] or 0,   # news_count
                row[2] or 0,   # news_sentiment_mean
                row[3] or 0,   # news_sentiment_pos
                row[4] or 0,   # news_sentiment_neg
                row[5] or 0,   # news_volume_spike
                row[6] or 0,   # sentiment_change_1d
                row[7] or 0,   # price_ret1d
                row[8] or 0,   # price_ret5d
                row[9] or 0,   # price_vol5d
                row[10] or 0   # distance_ma5
            ])
        
        # Get predictions
        proba = self.model.predict_proba(X)
        predictions = proba[:, 1]
        
        # Convert to signals
        raw_signals = {}
        for sym, pred in zip(sym_order, predictions):
            raw_signals[sym] = (pred - 0.5) * 2
        
        # Scale by confidence
        scale_long = 0.15
        scale_short = 0.10
        
        signals = {}
        for sym, weight in raw_signals.items():
            if weight > 0:
                signals[sym] = weight * scale_long
            else:
                signals[sym] = weight * scale_short
        
        # Apply risk controls
        signals = self._apply_risk_management(signals, dt, universe)
        
        return signals
    
    def _apply_risk_management(self, signals: Dict[str, float], dt: date, universe: Dict[str, Any]) -> Dict[str, float]:
        """Apply risk controls"""
        from .risk_manager import RiskMetrics
        
        with self.store.connect() as con:
            placeholders = ",".join("?" * len(signals))
            sql = f"""
            SELECT symbol, price_vol5d 
            FROM features_daily 
            WHERE date = ? AND symbol IN ({placeholders})
            """
            rows = con.execute(sql, [dt.isoformat()] + list(signals.keys())).fetchall()
            vols = dict(rows) if rows else {}
        
        metrics = RiskMetrics(
            equity=100000, peak_equity=100000, current_drawdown_pct=0,
            daily_pnl=0, volatility_5d=0.02,
            gross_exposure=sum(abs(w) for w in signals.values()),
            net_exposure=sum(signals.values()), concentration_top3=0
        )
        
        return self.risk_manager.apply_risk_limits(signals, metrics, vols)
