"""
Isolation Forest model for detecting structuring (smurfing).

Structuring involves splitting large cash/transfer amounts into smaller 
deposits to avoid reporting thresholds. Isolation Forest is excellent at 
detecting these localized density anomalies in transaction timing/amounts.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, average_precision_score

class StructuringDetector:
    def __init__(self):
        # We expect a very small contamination rate assuming real-world skewed data
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.01, 
            random_state=42
        )

    def prepare_data(self, transactions_df: pd.DataFrame, ground_truth: list):
        """Prepare daily aggregation features for detecting structuring."""
        # Structuring usually happens within 1-3 days on the same account
        df = transactions_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp_initiated"]):
            df["timestamp_initiated"] = pd.to_datetime(df["timestamp_initiated"])
        df["date"] = df["timestamp_initiated"].dt.date
        
        # Group by receiver (deposits) per day
        daily = df.groupby(["receiver_account_id", "date"]).agg(
            daily_txns=("txn_id", "count"),
            daily_inflow=("amount_value", "sum"),
            max_single_inflow=("amount_value", "max"),
            min_single_inflow=("amount_value", "min")
        ).reset_index()

        daily["avg_inflow"] = daily["daily_inflow"] / daily["daily_txns"]
        
        # Features for IF: high frequency of txns, but max inflow is suspiciously below threshold
        features = ["daily_txns", "daily_inflow", "max_single_inflow", "avg_inflow"]
        X = daily[features].fillna(0)

        # Labels
        struct_accounts = set()
        for pattern in ground_truth:
            if pattern.get("pattern_type") == "STRUCTURING":
                struct_accounts.add(pattern.get("account_id"))

        y = pd.Series(0, index=daily.index)
        y.loc[daily["receiver_account_id"].isin(struct_accounts)] = 1
        
        return daily, X, y

    def train_and_evaluate(self, daily_df: pd.DataFrame, X: pd.DataFrame, y: pd.Series):
        if sum(y) < 2:
            print("Not enough structuring examples.")
            return None

        # Isolation forest represents anomalies as -1, normal as 1
        preds = self.model.fit_predict(X)
        scores = -self.model.score_samples(X) # Higher score = more anomalous
        
        # Convert -1/1 to 1/0
        binary_preds = np.where(preds == -1, 1, 0)
        
        print("--- Structuring Isolation Forest Results ---")
        print(classification_report(y, binary_preds, zero_division=0))
        print(f"PR-AUC: {average_precision_score(y, scores):.4f}")
        
        daily_df["is_anomalous"] = binary_preds
        daily_df["anomaly_score"] = scores
        
        return daily_df
