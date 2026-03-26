"""
YAML configuration for Risk Scoring Weights.

Allows tuning the importance of different ML models and rule-based
signals without changing code.
"""

import os
import yaml
from typing import Dict, Any

DEFAULT_CONFIG = """
# Risk Scoring Weights and Thresholds

# Base weights for each ML model output (0.0 to 1.0)
models:
  layering_gnn: 0.35
  round_tripping_xgb: 0.30
  structuring_iforest: 0.15
  dormant_activation_svm: 0.10
  profile_mismatch_lgbm: 0.10

# Amplifiers (Multipliers applied if certain high-risk conditions are met)
amplifiers:
  high_risk_jurisdiction: 1.5
  pep_involved: 2.0
  rapid_pass_through: 1.3

# Thresholds for alert generation
thresholds:
  low_risk: 30
  medium_risk: 60
  high_risk: 80
"""

class ScoringConfig:
    def __init__(self, config_path: str = None):
        if config_path and os.path.exists(config_path):
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = yaml.safe_load(DEFAULT_CONFIG)

    def get_model_weight(self, model_name: str) -> float:
        return self.config.get("models", {}).get(model_name, 0.0)

    def get_amplifier(self, condition: str) -> float:
        return self.config.get("amplifiers", {}).get(condition, 1.0)

    def get_threshold(self, level: str) -> int:
        return self.config.get("thresholds", {}).get(level, 0)

config = ScoringConfig()
