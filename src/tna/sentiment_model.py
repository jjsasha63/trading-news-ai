from __future__ import annotations
from typing import List, Dict, Tuple
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import joblib

class NewsSentimentModel:
    def __init__(self):
        self.model = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, random_state=42,
            learning_rate=0.1
        )
        self.scaler = StandardScaler()
        self.feature_names = [
            'news_count', 'news_sentiment_mean', 'news_sentiment_pos', 
            'news_sentiment_neg', 'news_volume_spike', 'sentiment_change_1d',
            'price_ret1d', 'price_ret5d', 'price_vol5d', 'distance_ma5'
        ]
        self.is_fitted = False
    
    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train on features → next-day return direction"""
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.is_fitted = True
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)
    
    def walk_forward_validate(self, features_df: pd.DataFrame, labels_df: pd.DataFrame) -> Dict:
        """TimeSeriesSplit validation for trading models"""
        tscv = TimeSeriesSplit(n_splits=5)
        scores = []
        
        for train_idx, test_idx in tscv.split(features_df):
            X_train, X_test = features_df.iloc[train_idx], features_df.iloc[test_idx]
            y_train, y_test = labels_df.iloc[train_idx], labels_df.iloc[test_idx]
            
            model = NewsSentimentModel()
            model.fit(X_train.values, y_train.values)
            
            probs = model.predict_proba(X_test.values)[:, 1]  # P(up)
            pred_dir = (probs > 0.5).astype(int)
            accuracy = (pred_dir == y_test.values).mean()
            scores.append(accuracy)
        
        return {"walk_forward_accuracy": np.mean(scores), "splits": scores}

def simple_sentiment_score(text: str) -> float:
    """Quick baseline sentiment (replace with FinBERT later)"""
    # Naive: positive/negative word ratios
    pos_words = {'growth', 'rise', 'gain', 'profit', 'beat', 'strong', 'surge'}
    neg_words = {'loss', 'fall', 'drop', 'miss', 'weak', 'crash', 'cut'}
    
    words = set(text.lower().split())
    pos_score = len(words & pos_words)
    neg_score = len(words & neg_words)
    
    if pos_score + neg_score == 0:
        return 0.0
    return (pos_score - neg_score) / (pos_score + neg_score)
