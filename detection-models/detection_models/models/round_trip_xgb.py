"""
XGBoost model to detect round-tripping patterns (circular flows).

This model heavily relies on structural graph features like finding cycles,
pass-through velocities, and amount preservation ratios.
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, average_precision_score

class RoundTripDetector:
    def __init__(self):
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=10, # Imbalanced class handling
            random_state=42
        )
        self.features = [
            "total_degree", "flow_ratio", "rapid_pass_ratio",
            "rapid_txns", "fan_out_ratio", "max_dormancy_days"
        ]

    def prepare_data(self, graph_features: pd.DataFrame, account_features: pd.DataFrame, ground_truth: list):
        """Prepare X and y for training/testing."""
        df = account_features.join(graph_features, how="left").fillna(0)
        
        # Ensure all feature columns exist
        for f in self.features:
            if f not in df.columns:
                df[f] = 0.0

        X = df[self.features]
        
        # Build binary labels from ground truth
        rt_accounts = set()
        for pattern in ground_truth:
            if pattern.get("pattern_type") == "ROUND_TRIPPING":
                # Mark originators and intermediaries
                if "account_cycle" in pattern:
                    rt_accounts.update(pattern["account_cycle"])
                if "originator_account" in pattern:
                    rt_accounts.add(pattern["originator_account"])

        y = pd.Series(0, index=df.index)
        y.loc[y.index.isin(rt_accounts)] = 1
        
        return X, y

    def train_and_evaluate(self, X: pd.DataFrame, y: pd.Series):
        if sum(y) < 5:
            print("Not enough round-tripping examples to train XGBoost properly.")
            return None

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )
        
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False
        )

        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)[:, 1]

        print("--- Round Tripping XGBoost Results ---")
        print(classification_report(y_test, y_pred, zero_division=0))
        print(f"PR-AUC: {average_precision_score(y_test, y_prob):.4f}")
        
        return self.model
