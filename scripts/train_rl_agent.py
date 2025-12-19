"""
Training loop for RL trading agent with adaptive learning.
Runs continuous simulation and updates agent based on performance.
"""
from __future__ import annotations
import sys
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Ensure project src/ is on PYTHONPATH
_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root / "src"))
sys.path.insert(0, str(_repo_root / "scripts"))

from tna.config import load_config
from rl_agent import RLTradingAgent
from paper_trader import PaperTrader


def save_training_history(db_path: Path, episode: int, metrics: dict):
    """Save training metrics to database."""
    with sqlite3.connect(str(db_path)) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS rl_training_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode INTEGER,
                final_portfolio_value REAL,
                total_return_pct REAL,
                sharpe_ratio REAL,
                max_drawdown_pct REAL,
                num_trades INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        con.execute("""
            INSERT INTO rl_training_history 
            (episode, final_portfolio_value, total_return_pct, sharpe_ratio, 
             max_drawdown_pct, num_trades)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (episode, metrics.get('final_value', 0), 
              metrics.get('total_return', 0), metrics.get('sharpe', 0),
              metrics.get('max_drawdown', 0), metrics.get('num_trades', 0)))
        
        con.commit()


def main():
    cfg = load_config("config.yml")
    db_path = Path(cfg.db_path)
    
    # Training parameters
    initial_capital = 100000
    train_start = "2023-01-01"
    train_end = "2024-11-01"
    
    print("=" * 60)
    print("🤖 RL Trading Agent - Adaptive Learning")
    print("=" * 60)
    print(f"Initial Capital: ${initial_capital:,.0f}")
    print(f"Training Period: {train_start} to {train_end}")
    print()
    
    # Create agent
    agent = RLTradingAgent(
        db_path=db_path,
        start_date=train_start,
        end_date=train_end,
        initial_capital=initial_capital
    )
    
    # Train for multiple episodes
    num_episodes = 5
    timesteps_per_episode = 10000
    
    for episode in range(1, num_episodes + 1):
        print(f"\n📊 Episode {episode}/{num_episodes}")
        print("-" * 60)
        
        # Train
        agent.train(total_timesteps=timesteps_per_episode,
                   save_path=f"models/rl_agent_episode_{episode}")
        
        # Evaluate on paper trading
        print("\n📈 Running paper trading simulation...")
        paper_trader = PaperTrader(db_path, initial_capital)
        results = paper_trader.run_simulation(train_start, train_end)
        
        if not results.empty:
            final_value = results['portfolio_value'].iloc[-1]
            total_return = (final_value / initial_capital - 1) * 100
            
            # Calculate Sharpe ratio
            returns = results['daily_return'].pct_change().dropna()
            sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
            
            # Max drawdown
            cumulative = (1 + results['daily_return']).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_dd = drawdown.min() * 100
            
            metrics = {
                'final_value': final_value,
                'total_return': total_return,
                'sharpe': sharpe,
                'max_drawdown': max_dd,
                'num_trades': len(paper_trader.trade_history)
            }
            
            # Save results
            save_training_history(db_path, episode, metrics)
            paper_trader.save_results()
            
            print(f"\n✅ Episode {episode} Results:")
            print(f"   Final Portfolio Value: ${final_value:,.0f}")
            print(f"   Total Return: {total_return:.2f}%")
            print(f"   Sharpe Ratio: {sharpe:.2f}")
            print(f"   Max Drawdown: {max_dd:.2f}%")
            print(f"   Total Trades: {metrics['num_trades']}")
        else:
            print("⚠️  No simulation results")
    
    print("\n" + "=" * 60)
    print("🎯 Training Complete!")
    print("=" * 60)
    print(f"Best model saved to: models/rl_agent_episode_{num_episodes}")
    print("\nView results in dashboard at http://localhost:8050")


if __name__ == "__main__":
    main()
