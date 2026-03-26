"""
Main orchestration script for evaluating all detection models.

Uses the synthetic JSON data generated in Phase 1 to construct features,
train all Phase 2 ML models, and prints terminal-based performance reports.
"""

import os
import json
import pandas as pd
import warnings

# Suppress sklearn/pytorch warnings for cleaner output
warnings.filterwarnings('ignore')

from detection_models.features.graph_features import GraphFeatureExtractor
from detection_models.features.account_features import AccountFeatureExtractor

from detection_models.models.layering_gnn import LayeringGNNDetector
from detection_models.models.round_trip_xgb import RoundTripDetector
from detection_models.models.structuring_iforest import StructuringDetector
from detection_models.models.dormant_svm import DormantActivationDetector
from detection_models.models.profile_mismatch_lgbm import ProfileMismatchDetector


def load_dataset(data_dir: str):
    print("Loading Phase 1 Data...")
    acc_path = os.path.join(data_dir, "accounts.json")
    txn_path = os.path.join(data_dir, "transactions.json")
    gt_path = os.path.join(data_dir, "ground_truth.json")

    with open(acc_path, 'r') as f:
        accounts = json.load(f)
    with open(txn_path, 'r') as f:
        transactions = json.load(f)
    with open(gt_path, 'r') as f:
        ground_truth = json.load(f)
        
    accounts_df = pd.DataFrame(accounts)
    transactions_df = pd.DataFrame(transactions)
    
    return accounts_df, transactions_df, ground_truth


def extract_features(accounts_df, transactions_df):
    print("Extracting Account Features (Pandas)...")
    acc_extractor = AccountFeatureExtractor(accounts_df, transactions_df)
    account_features = acc_extractor.get_all_features()
    
    print("Extracting Graph Features (Neo4j)...")
    try:
        graph_extractor = GraphFeatureExtractor()
        graph_features = graph_extractor.get_all_features()
        graph_extractor.close()
    except Exception as e:
        print(f"\n[!] Neo4j connection failed: {e}")
        print("Falling back to empty graph features for evaluation...\n")
        graph_features = pd.DataFrame(index=accounts_df["account_id"])
        
    return account_features, graph_features


def evaluate_models(accounts_df, transactions_df, account_features, graph_features, ground_truth):
    print("\n" + "="*50)
    print("EVALUATING LAYER 2: ML DETECTION MODELS")
    print("="*50 + "\n")
    
    # 1. Round Tripping (XGBoost)
    try:
        round_trip_detector = RoundTripDetector()
        X_rt, y_rt = round_trip_detector.prepare_data(graph_features, account_features, ground_truth)
        round_trip_detector.train_and_evaluate(X_rt, y_rt)
    except Exception as e:
        print(f"Round Tripping Failed: {e}")
    print("\n" + "-"*40 + "\n")

    # 2. Structuring (Isolation Forest)
    try:
        struct_detector = StructuringDetector()
        daily_df, X_st, y_st = struct_detector.prepare_data(transactions_df, ground_truth)
        struct_detector.train_and_evaluate(daily_df, X_st, y_st)
    except Exception as e:
        print(f"Structuring Failed: {e}")
    print("\n" + "-"*40 + "\n")

    # 3. Dormant Activation (One-Class SVM)
    try:
        dormant_detector = DormantActivationDetector()
        df_dormant, X_dorm, y_dorm = dormant_detector.prepare_data(account_features, ground_truth)
        dormant_detector.train_and_evaluate(df_dormant, X_dorm, y_dorm)
    except Exception as e:
        print(f"Dormant Activation Failed: {e}")
    print("\n" + "-"*40 + "\n")

    # 4. Profile Mismatch (LightGBM)
    try:
        profile_detector = ProfileMismatchDetector()
        df_pm, X_pm, y_pm = profile_detector.prepare_data(accounts_df, transactions_df, ground_truth)
        profile_detector.train_and_evaluate(df_pm, X_pm, y_pm)
    except Exception as e:
        print(f"Profile Mismatch Failed: {e}")
    print("\n" + "-"*40 + "\n")

    # 5. Layering (GraphSAGE GNN)
    try:
        layering_detector = LayeringGNNDetector()
        data_g, df_g, acc_g = layering_detector.prepare_data(
            graph_features, account_features, transactions_df, ground_truth
        )
        layering_detector.train_and_evaluate(data_g)
    except Exception as e:
        print(f"Layering GNN Failed: {e}")
    print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data-generator", "output")
    
    if not os.path.exists(DATA_DIR):
        print(f"Error: Could not find Phase 1 output at {DATA_DIR}")
        print("Please run the data generator first.")
        exit(1)
        
    acc_df, txn_df, gt = load_dataset(DATA_DIR)
    acc_feats, graph_feats = extract_features(acc_df, txn_df)
    
    evaluate_models(acc_df, txn_df, acc_feats, graph_feats, gt)
