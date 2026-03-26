"""
LightGBM Profile Mismatch Scorer.

Detects transactions that severely violate an account's expected profile
(e.g. Student account processing millions in SWIFT corporate transfers).
"""

import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, average_precision_score

class ProfileMismatchDetector:
    def __init__(self):
        self.model = lgb.LGBMClassifier(
            n_estimators=100,
            learning_rate=0.05,
            class_weight='balanced',
            random_state=42,
            verbose=-1
        )
        self.features = [
            "amount_value", 
            "annual_income", 
            "tx_to_income_ratio",
            "is_swift", 
            "is_trade",
            "is_high_risk_occupation"
        ]

    def prepare_data(self, accounts_df: pd.DataFrame, transactions_df: pd.DataFrame, ground_truth: list):
        # Merge txn with sender details
        df = transactions_df.merge(
            accounts_df[["account_id", "annual_income", "occupation"]], 
            left_on="sender_account_id", 
            right_on="account_id",
            how="left"
        )
        
        df["tx_to_income_ratio"] = df["amount_value"] / (df["annual_income"] / 12 + 1)
        df["is_swift"] = (df["source_system"] == "SWIFT").astype(int)
        df["is_trade"] = (df["purpose_code"] == "TRADE_PAYMENT").astype(int)
        
        high_risk_occ = ["STUDENT", "HOMEMAKER", "AGRICULTURE", "UNEMPLOYED"]
        df["is_high_risk_occupation"] = df["occupation"].isin(high_risk_occ).astype(int)
        
        X = df[self.features].fillna(0)
        
        # Extract ground truth transaction IDs directly
        mismatch_txns = set()
        for p in ground_truth:
            if p.get("pattern_type") == "PROFILE_MISMATCH":
                mismatch_txns.update(p.get("transaction_ids", []))
                
        y = df["txn_id"].isin(mismatch_txns).astype(int)
        
        return df, X, y

    def train_and_evaluate(self, df: pd.DataFrame, X: pd.DataFrame, y: pd.Series):
        if sum(y) < 5:
            print("Not enough profile mismatch examples.")
            return None

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )
        
        self.model.fit(X_train, y_train)
        
        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)[:, 1]

        print("--- Profile Mismatch LightGBM Results ---")
        print(classification_report(y_test, y_pred, zero_division=0))
        print(f"PR-AUC: {average_precision_score(y_test, y_prob):.4f}")
        
        # Feature importance
        importance = pd.DataFrame({
            "feature": self.features,
            "importance": self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        print("Top Features:", importance.head(3).to_dict('records'))
        
        return self.model
