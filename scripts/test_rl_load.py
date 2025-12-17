from pathlib import Path
from stable_baselines3 import PPO

print("Loading model...")
model = PPO.load("models/rl_agent_episode_3")
print("✅ Model loaded")

import numpy as np
obs = np.zeros(81, dtype=np.float32)
print("Testing prediction...")
action, _ = model.predict(obs, deterministic=True)
print(f"✅ Action shape: {action.shape}, sample: {action[:5]}")
