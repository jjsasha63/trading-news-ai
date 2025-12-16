"""Live dashboard - run in separate terminal"""
import sqlite3
import pandas as pd
from pathlib import Path
import time

def live_dashboard():
    db_path = Path("data/tna.sqlite")
    
    while True:
        try:
            con = sqlite3.connect(str(db_path))
            
            # Portfolio snapshot
            df_port = pd.read_sql("""
            SELECT date, equity, cash, gross_exposure, daily_pnl, alive
            FROM portfolio_live 
            ORDER BY date DESC LIMIT 1
            """, con)
            
            # Top signals today
            df_signals = pd.read_sql("""
            SELECT symbol, target_weight, confidence 
            FROM signals_today 
            ORDER BY abs(target_weight) DESC LIMIT 10
            """, con)
            
            print(f"\n{'='*60}")
            print(f"📊 LIVE STATUS  {pd.Timestamp.now().strftime('%H:%M ET')}")
            print(f"{'='*60}")
            if not df_port.empty:
                row = df_port.iloc[0]
                print(f"💰 Equity: ${row['equity']:,.0f} | PnL: ${row['daily_pnl']:.2f}")
                print(f"⚖️  Gross: {row['gross_exposure']:.1%} | Alive: {'✅' if row['alive'] else '❌'}")
            
            print("\n🎯 TOP SIGNALS:")
            print(df_signals.to_string(index=False))
            
            con.close()
        except Exception as e:
            print(f"Dashboard error: {e}")
        
        time.sleep(300)  # 5min refresh

if __name__ == "__main__":
    live_dashboard()
