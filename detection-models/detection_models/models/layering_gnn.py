"""
GraphSAGE model for Layering Pattern Detection.

Uses PyTorch Geometric to train a Graph Neural Network on the constructed
transaction graph. The GNN embeddings capture multi-hop structural signatures
characteristic of layering behavior.
"""

import pandas as pd
import numpy as np
import torch
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv
from sklearn.metrics import classification_report, average_precision_score

class GraphSAGE(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.out = torch.nn.Linear(hidden_channels, out_channels)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.4, training=self.training)
        
        x = self.conv2(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.4, training=self.training)
        
        return self.out(x)


class LayeringGNNDetector:
    def __init__(self):
        self.model = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def prepare_data(self, graph_features: pd.DataFrame, account_features: pd.DataFrame, 
                     transactions_df: pd.DataFrame, ground_truth: list):
        """Construct a PyG Data object."""
        
        # 1. Combine all features
        df = account_features.join(graph_features, how="left").fillna(0)
        
        # 2. Map account IDs to integer indices
        accounts = list(df.index)
        acc_to_idx = {acc: i for i, acc in enumerate(accounts)}
        
        # 3. Create Node Feature Tensor (X)
        feature_cols = [
            "annual_income", "average_monthly_balance", "max_daily_outflow", 
            "outflow_std_dev", "in_degree", "out_degree", "total_inflow", 
            "total_outflow", "fan_out_ratio"
        ]
        
        for c in feature_cols:
            if c not in df.columns:
                df[c] = 0.0
                
        # Normalize node features
        x_np = df[feature_cols].values
        x_mean = x_np.mean(axis=0)
        x_std = x_np.std(axis=0) + 1e-6
        x_np = (x_np - x_mean) / x_std
        x = torch.tensor(x_np, dtype=torch.float)
        
        # 4. Create Edge Index (COO format)
        edges = []
        for _, row in transactions_df.iterrows():
            sender = row['sender_account_id']
            receiver = row['receiver_account_id']
            if sender in acc_to_idx and receiver in acc_to_idx:
                edges.append([acc_to_idx[sender], acc_to_idx[receiver]])
                
        if not edges: # Fallback if empty graph
            edge_index = torch.empty((2, 0), dtype=torch.long)
        else:
            edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
            
        # 5. Build Ground Truth Labels
        layering_accs = set()
        for p in ground_truth:
            if p.get("pattern_type") == "LAYERING":
                layering_accs.update(p.get("account_chain", []))
                
        y = torch.zeros(len(accounts), dtype=torch.long)
        for idx, acc in enumerate(accounts):
            if acc in layering_accs:
                y[idx] = 1
                
        # Train/Test masks
        indices = np.random.permutation(len(accounts))
        train_size = int(0.7 * len(accounts))
        
        train_mask = torch.zeros(len(accounts), dtype=torch.bool)
        test_mask = torch.zeros(len(accounts), dtype=torch.bool)
        
        train_mask[indices[:train_size]] = True
        test_mask[indices[train_size:]] = True
        
        data = Data(x=x, edge_index=edge_index, y=y)
        data.train_mask = train_mask
        data.test_mask = test_mask
        
        return data, df, accounts

    def train_and_evaluate(self, data: Data):
        if data.y.sum().item() < 3:
            print("Not enough layering examples to train GNN properly.")
            return None

        self.model = GraphSAGE(
            in_channels=data.x.size(1), 
            hidden_channels=32, 
            out_channels=2
        ).to(self.device)
        
        data = data.to(self.device)
        
        # Class weights for extreme imbalance
        num_neg = (data.y[data.train_mask] == 0).sum()
        num_pos = (data.y[data.train_mask] == 1).sum()
        weight = torch.tensor([1.0, float(num_neg)/max(float(num_pos), 1.0)]).to(self.device)
        
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.01, weight_decay=5e-4)
        criterion = torch.nn.CrossEntropyLoss(weight=weight)
        
        # Train
        self.model.train()
        for epoch in range(100):
            optimizer.zero_grad()
            out = self.model(data.x, data.edge_index)
            loss = criterion(out[data.train_mask], data.y[data.train_mask])
            loss.backward()
            optimizer.step()
            
        # Evaluate
        self.model.eval()
        out = self.model(data.x, data.edge_index)
        probs = F.softmax(out, dim=1)[:, 1].detach().cpu().numpy()
        preds = out.argmax(dim=1).cpu().numpy()
        y_true = data.y.cpu().numpy()
        
        test_mask = data.test_mask.cpu().numpy()
        
        print("--- Layering GraphSAGE Results ---")
        print(classification_report(y_true[test_mask], preds[test_mask], zero_division=0))
        print(f"PR-AUC: {average_precision_score(y_true[test_mask], probs[test_mask]):.4f}")
        
        return self.model
