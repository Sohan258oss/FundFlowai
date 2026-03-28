"""
Account Behavioral Feature Extraction.

Extracts tabular and behavioral features directly from JSON datasets (or Pandas DataFrames)
without needing the graph topology.
"""

import pandas as pd
from typing import List, Dict


class AccountFeatureExtractor:
    """Extracts features from plain transaction and account data."""

    def __init__(self, accounts_df: pd.DataFrame, transactions_df: pd.DataFrame):
        self.accounts = accounts_df.copy()
        self.transactions = transactions_df.copy()
        
        # Ensure time is datetime
        if not pd.api.types.is_datetime64_any_dtype(self.transactions["timestamp_initiated"]):
            self.transactions["timestamp_initiated"] = pd.to_datetime(
                self.transactions["timestamp_initiated"]
            )

    def extract_velocity_features(self) -> pd.DataFrame:
        """
        Calculate daily/weekly transaction velocity per account.
        """
        # Outflows
        outflows = self.transactions[["sender_account_id", "timestamp_initiated", "amount_value"]].copy()
        outflows.rename(columns={"sender_account_id": "account_id"}, inplace=True)
        outflows.set_index("timestamp_initiated", inplace=True)
        
        # Group by account and resample daily
        daily_outflow = outflows.groupby("account_id").resample("D")["amount_value"].sum().reset_index()
        
        # Calculate stats
        velocity_stats = daily_outflow.groupby("account_id").agg(
            max_daily_outflow=("amount_value", "max"),
            avg_daily_outflow=("amount_value", "mean"),
            outflow_std_dev=("amount_value", "std")
        ).fillna(0)
        
        return velocity_stats

    def extract_dormancy_features(self) -> pd.DataFrame:
        """
        Calculate time since last transaction (dormancy).
        Returns max gap between transactions in days.
        """
        txns = self.transactions[["sender_account_id", "timestamp_initiated"]].copy()
        txns.rename(columns={"sender_account_id": "account_id"}, inplace=True)
        
        txns = txns.sort_values(by=["account_id", "timestamp_initiated"])
        txns["prev_timestamp"] = txns.groupby("account_id")["timestamp_initiated"].shift(1)
        txns["time_gap_days"] = (txns["timestamp_initiated"] - txns["prev_timestamp"]).dt.total_seconds() / 86400.0
        
        dormancy = txns.groupby("account_id")["time_gap_days"].max().fillna(0).to_frame(name="max_dormancy_days")
        return dormancy

    def extract_profile_features(self) -> pd.DataFrame:
        """
        Extract baseline profile features like income ratio.
        """
        df = self.accounts.copy()
        df.set_index("account_id", inplace=True)
        
        # Keep features useful for ML
        # categorical encoding can be done downstream or here
        cols = ["account_type", "annual_income", "avg_balance_30d", "status"]
        return df[[c for c in cols if c in df.columns]]

    def get_all_features(self) -> pd.DataFrame:
        """
        Merge all tabular account features.
        """
        prof_df = self.extract_profile_features()
        vel_df = self.extract_velocity_features()
        dorm_df = self.extract_dormancy_features()
        
        final = prof_df.join(vel_df, how="left").join(dorm_df, how="left")
        final.fillna(0, inplace=True)
        return final
