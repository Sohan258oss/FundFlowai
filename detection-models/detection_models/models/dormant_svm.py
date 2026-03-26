"""
One-Class SVM model for detecting dormant account activation.

Learns the boundary of "normal" low-velocity behavior and flags accounts
that suddenly exhibit massive spikes breaking out of their historical norm.
"""

import pandas as pd
import numpy as np
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, average_precision_score

class DormantActivationDetector:
    def __init__(self):
        self.scaler = StandardScaler()
        self.model = OneClassSVM(
            kernel="rbf", 
            gamma="scale", 
            nu=0.02 # Expected outlier fraction
        )

    def prepare_data(self, account_features: pd.DataFrame, ground_truth: list):
        """Prepare X and y using account velocity and dormancy features."""
        df = account_features.copy().fillna(0)
        
        features = ["max_dormancy_days", "max_daily_outflow", "avg_daily_outflow", "annual_income"]
        for f in features:
            if f not in df.columns:
                df[f] = 0.0
                
        # The key anomaly is high dormancy combined with high current outflow
        df["outflow_to_income_ratio"] = df["max_daily_outflow"] / (df["annual_income"] / 365 + 1)
        features.append("outflow_to_income_ratio")
        
        X = df[features].copy()
        
        # Ground truth
        dormant_accounts = set()
        for p in ground_truth:
            if p.get("pattern_type") == "DORMANT_ACTIVATION":
                dormant_accounts.add(p.get("account_id"))
                
        y = pd.Series(0, index=df.index)
        y.loc[y.index.isin(dormant_accounts)] = 1
        
        return df, X, y

    def train_and_evaluate(self, df: pd.DataFrame, X: pd.DataFrame, y: pd.Series):
        if sum(y) < 2:
            print("Not enough dormant activation examples.")
            return None

        # Standardize for SVM
        X_scaled = self.scaler.fit_transform(X)
        
        # Fit on mostly normal data (One-class SVM)
        # In a real setup, we'd fit only on y=0
        X_train_normal = X_scaled[y == 0]
        if len(X_train_normal) > 0:
            self.model.fit(X_train_normal)
        else:
            self.model.fit(X_scaled)
            
        preds = self.model.predict(X_scaled)
        # OCSVM returns -1 for outlier, 1 for inlier
        binary_preds = np.where(preds == -1, 1, 0)
        
        # Decision function: smaller values are more anomalous
        scores = -self.model.decision_function(X_scaled)
        
        print("--- Dormant Activation One-Class SVM Results ---")
        print(classification_report(y, binary_preds, zero_division=0))
        print(f"PR-AUC: {average_precision_score(y, scores):.4f}")
        
        return self.model
