"""
SHAP Explainability Module.

Generates feature importance and single-prediction explanations 
for the tabular detection models.
"""

import pandas as pd
import shap
import matplotlib.pyplot as plt
import os

class ModelExplainer:
    def __init__(self, model, feature_names):
        """
        model: Trained sklearn/XGB/LGBM model.
        feature_names: List of column names used in X.
        """
        self.model = model
        self.feature_names = feature_names
        # SHAP TreeExplainer supports XGBoost, LightGBM, Random Forest, Isolation Forest
        self.explainer = shap.TreeExplainer(model)
        
    def explain_global(self, X: pd.DataFrame, output_path: str = "shap_summary.png"):
        """Generate global feature importance plot via SHAP summary."""
        shap_values = self.explainer.shap_values(X)
        
        # Determine if binary classification or single output (like isolation forest)
        if isinstance(shap_values, list):
            sv = shap_values[1] # Use positive class
        else:
            sv = shap_values
            
        plt.figure(figsize=(10, 6))
        shap.summary_plot(sv, X, feature_names=self.feature_names, show=False)
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        print(f"Global SHAP summary saved to {output_path}")
        
    def explain_instance(self, X_instance: pd.DataFrame, instance_id: str, output_path: str = None):
        """Generate a force plot or waterfall for a single prediction."""
        shap_values = self.explainer(X_instance)
        
        if output_path is None:
            output_path = f"shap_force_{instance_id}.png"
            
        # Due to matplotlib constraints inside notebooks/scripts without JS, 
        # we plot a standard waterfall chart if available
        plt.figure(figsize=(8, 5))
        try:
            shap.plots.waterfall(shap_values[0], show=False)
            plt.tight_layout()
            plt.savefig(output_path)
            plt.close()
            print(f"Local instance SHAP saved to {output_path}")
        except Exception as e:
            print(f"Could not generate waterfall plot: {e}")
