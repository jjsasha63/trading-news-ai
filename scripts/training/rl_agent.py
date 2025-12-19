"""
Reinforcement Learning agent that learns to trade stocks.
Uses PPO (Proximal Policy Optimization) from stable-baselines3.
"""
from __future__ import annotations
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Any
import sqlite3
from pathlib import Path
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv


class TradingEnvironment(gym.Env):
    """Custom Gym environment for stock trading with news signals."""
    
    metadata = {'render.modes': ['human']}
    
    def __init__(self, db_path: Path, start_date: str, end_date: str, 
                 initial_capital: float = 100000):
        super().__init__()
        
        self.db_path = db_path
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.max_stocks = 20  # Define BEFORE loading data
        
        # Load all data at initialization
        self._load_data()
        
        # Action space: 3 actions per stock (buy, sell, hold) for top 20 stocks
        # Simplified: [-1, 1] continuous for each stock (negative=sell, positive=buy, ~0=hold)
        self.action_space = spaces.Box(
            low=-1, high=1, shape=(self.max_stocks,), dtype=np.float32
        )
        
        # Observation space: portfolio state + market features + news sentiment
        # [cash_ratio, 20x position_weights, 20x returns, 20x volatility, 20x news_sentiment]
        obs_dim = 1 + (self.max_stocks * 4)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        
        # Initialize state
        self.current_step = 0
        self.cash = initial_capital
        self.positions = {}  # {symbol: shares}
        self.portfolio_history = []
        
    def _load_data(self):
        """Load prices and features from database."""
        with sqlite3.connect(str(self.db_path)) as con:
            # Get top stocks by liquidity
            self.universe = pd.read_sql("""
                SELECT DISTINCT symbol
                FROM prices_daily
                WHERE date >= ? AND date <= ?
                GROUP BY symbol
                HAVING COUNT(*) > 200
                ORDER BY AVG(close * 1000000) DESC
                LIMIT ?
            """, con, params=(self.start_date, self.end_date, self.max_stocks))
            
            self.symbols = self.universe['symbol'].tolist()
            
            if not self.symbols:
                raise ValueError("No symbols found in database for given date range")
            
            # Load prices
            placeholders = ','.join('?' * len(self.symbols))
            self.prices = pd.read_sql(f"""
                SELECT date, symbol, close
                FROM prices_daily
                WHERE date >= ? AND date <= ?
                AND symbol IN ({placeholders})
                ORDER BY date, symbol
            """, con, params=[self.start_date, self.end_date] + self.symbols)
            
            # Load features (news sentiment, etc.)
            self.features = pd.read_sql(f"""
                SELECT date, symbol, 
                       news_sentiment_mean,
                       price_ret1d, price_ret5d, price_vol5d
                FROM features_daily
                WHERE date >= ? AND date <= ?
                AND symbol IN ({placeholders})
                ORDER BY date, symbol
            """, con, params=[self.start_date, self.end_date] + self.symbols)
        
        self.dates = sorted(self.prices['date'].unique())
        
        if len(self.dates) == 0:
            raise ValueError("No price data found for given date range")
        
    def _get_observation(self) -> np.ndarray:
        """Build observation vector for current state."""
        date = self.dates[self.current_step]
        
        # Current prices
        day_prices = self.prices[self.prices['date'] == date]
        price_dict = dict(zip(day_prices['symbol'], day_prices['close']))
        
        # Portfolio value
        holdings_value = sum(
            self.positions.get(sym, 0) * price_dict.get(sym, 0)
            for sym in self.symbols
        )
        total_value = self.cash + holdings_value
        
        obs = [self.cash / total_value if total_value > 0 else 1.0]  # Cash ratio
        
        # For each stock: position weight, return, volatility, news sentiment
        day_features = self.features[self.features['date'] == date]
        
        for symbol in self.symbols:
            price = price_dict.get(symbol, 0)
            shares = self.positions.get(symbol, 0)
            position_value = shares * price
            
            # Position weight
            obs.append(position_value / total_value if total_value > 0 else 0)
            
            # Features
            feat = day_features[day_features['symbol'] == symbol]
            if not feat.empty:
                obs.extend([
                    feat['price_ret1d'].iloc[0] if pd.notna(feat['price_ret1d'].iloc[0]) else 0,
                    feat['price_vol5d'].iloc[0] if pd.notna(feat['price_vol5d'].iloc[0]) else 0,
                    feat['news_sentiment_mean'].iloc[0] if pd.notna(feat['news_sentiment_mean'].iloc[0]) else 0
                ])
            else:
                obs.extend([0, 0, 0])
        
        return np.array(obs, dtype=np.float32)
    
    def _calculate_reward(self, prev_value: float, curr_value: float) -> float:
        """Calculate reward based on portfolio return."""
        # Daily return
        ret = (curr_value / prev_value - 1) if prev_value > 0 else 0
        
        # Penalize large drawdowns
        penalty = 0
        if ret < -0.02:  # More than 2% loss
            penalty = abs(ret) * 10
        
        # Reward: Sharpe-like (return / volatility proxy)
        return ret - penalty
    
    def _execute_trades(self, actions: np.ndarray):
        """Execute trades based on agent actions."""
        date = self.dates[self.current_step]
        day_prices = self.prices[self.prices['date'] == date]
        price_dict = dict(zip(day_prices['symbol'], day_prices['close']))
        
        total_value = self.cash + sum(
            self.positions.get(sym, 0) * price_dict.get(sym, 0)
            for sym in self.symbols
        )
        
        fee_pct = 0.001  # 0.1% transaction fee
        
        for i, symbol in enumerate(self.symbols):
            if i >= len(actions):
                break
                
            action = actions[i]
            price = price_dict.get(symbol, 0)
            if price == 0:
                continue
            
            current_shares = self.positions.get(symbol, 0)
            
            # Action > 0.3: Buy, < -0.3: Sell, else: Hold
            if action > 0.3:
                # Buy: allocate 5% of portfolio
                target_value = total_value * 0.05 * action  # Scale by action strength
                shares_to_buy = int(target_value / price)
                cost = shares_to_buy * price * (1 + fee_pct)
                
                if cost <= self.cash and shares_to_buy > 0:
                    self.cash -= cost
                    self.positions[symbol] = current_shares + shares_to_buy
            
            elif action < -0.3 and current_shares > 0:
                # Sell: liquidate portion based on action strength
                shares_to_sell = int(current_shares * abs(action))
                proceeds = shares_to_sell * price * (1 - fee_pct)
                
                self.cash += proceeds
                self.positions[symbol] = current_shares - shares_to_sell
                if self.positions[symbol] <= 0:
                    del self.positions[symbol]
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        """Execute one time step."""
        # Get current portfolio value
        date = self.dates[self.current_step]
        day_prices = self.prices[self.prices['date'] == date]
        price_dict = dict(zip(day_prices['symbol'], day_prices['close']))
        
        prev_value = self.cash + sum(
            self.positions.get(sym, 0) * price_dict.get(sym, 0)
            for sym in self.symbols
        )
        
        # Execute trades
        self._execute_trades(action)
        
        # Move to next day
        self.current_step += 1
        done = self.current_step >= len(self.dates) - 1
        
        if done:
            # Final observation
            obs = self._get_observation()
            reward = 0
            info = {'final_value': prev_value}
        else:
            # Get new observation
            obs = self._get_observation()
            
            # Calculate reward
            date_new = self.dates[self.current_step]
            day_prices_new = self.prices[self.prices['date'] == date_new]
            price_dict_new = dict(zip(day_prices_new['symbol'], day_prices_new['close']))
            
            curr_value = self.cash + sum(
                self.positions.get(sym, 0) * price_dict_new.get(sym, 0)
                for sym in self.symbols
            )
            
            reward = self._calculate_reward(prev_value, curr_value)
            info = {'portfolio_value': curr_value}
        
        self.portfolio_history.append(info)
        
        return obs, reward, done, False, info
    
    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, dict]:
        """Reset environment to initial state."""
        super().reset(seed=seed)
        self.current_step = 0
        self.cash = self.initial_capital
        self.positions = {}
        self.portfolio_history = []
        
        obs = self._get_observation()
        return obs, {}
    
    def render(self, mode='human'):
        """Render environment state."""
        if len(self.portfolio_history) > 0:
            last = self.portfolio_history[-1]
            print(f"Step: {self.current_step}, Portfolio Value: ${last.get('portfolio_value', 0):,.0f}")


class RLTradingAgent:
    """Wrapper for PPO agent with training utilities."""
    
    def __init__(self, db_path: Path, start_date: str, end_date: str,
                 initial_capital: float = 100000):
        self.env = TradingEnvironment(db_path, start_date, end_date, initial_capital)
        self.model = None
        
    def train(self, total_timesteps: int = 10000, save_path: str = "models/rl_agent_ppo"):
        """Train the RL agent."""
        # Wrap environment
        vec_env = DummyVecEnv([lambda: self.env])
        
        # Create PPO model WITHOUT tensorboard logging
        self.model = PPO(
            "MlpPolicy",
            vec_env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1
        )
        
        # Train
        print(f"Training for {total_timesteps} timesteps...")
        self.model.learn(total_timesteps=total_timesteps)
        
        # Save
        self.model.save(save_path)
        print(f"Model saved to {save_path}")
        
        return self.model
    
    def load(self, model_path: str):
        """Load trained model."""
        self.model = PPO.load(model_path)
        return self.model
    
    def predict(self, observation: np.ndarray) -> np.ndarray:
        """Get trading actions from trained model."""
        if self.model is None:
            raise ValueError("Model not trained or loaded")
        
        action, _ = self.model.predict(observation, deterministic=True)
        return action
