"""
Graph Feature Extraction Module.

Extracts structural and temporal features from the Neo4j transaction graph
to be used as inputs for machine learning models.
"""

import pandas as pd
from neo4j import GraphDatabase


class GraphFeatureExtractor:
    """Extracts features from the Neo4j graph into Pandas DataFrames for ML."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "fundflow_pass",
    ):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def extract_degree_features(self) -> pd.DataFrame:
        """
        Extract in-degree, out-degree, and total degree for all accounts.
        Returns a DataFrame indexed by account_id.
        """
        query = """
        MATCH (a:Account)
        OPTIONAL MATCH (a)<-[in_rel:TRANSFERRED_TO]-()
        OPTIONAL MATCH (a)-[out_rel:TRANSFERRED_TO]->()
        RETURN a.account_id AS account_id,
               count(DISTINCT in_rel) AS in_degree,
               count(DISTINCT out_rel) AS out_degree,
               sum(in_rel.amount) AS total_inflow,
               sum(out_rel.amount) AS total_outflow
        """
        with self.driver.session() as session:
            result = session.run(query)
            data = [dict(record) for record in result]
            
        df = pd.DataFrame(data)
        if not df.empty:
            df.set_index("account_id", inplace=True)
            df["total_degree"] = df["in_degree"] + df["out_degree"]
            # Fill missing amounts with 0
            df["total_inflow"] = df["total_inflow"].fillna(0.0)
            df["total_outflow"] = df["total_outflow"].fillna(0.0)
            df["flow_ratio"] = df["total_outflow"] / (df["total_inflow"] + 1)
        return df

    def extract_rapid_pass_through_features(self) -> pd.DataFrame:
        """
        Calculates the ratio of funds that pass through the account within 24h.
        """
        query = """
        MATCH (a:Account)<-[inflow:TRANSFERRED_TO]-(in_acc:Account)
        MATCH (a)-[outflow:TRANSFERRED_TO]->(out_acc:Account)
        WHERE duration.between(
            datetime(inflow.timestamp), 
            datetime(outflow.timestamp)
        ).hours <= 24
        AND datetime(outflow.timestamp) > datetime(inflow.timestamp)
        RETURN a.account_id AS account_id,
               count(outflow) AS rapid_txns,
               sum(outflow.amount) / (sum(inflow.amount) + 1) AS rapid_pass_ratio
        """
        with self.driver.session() as session:
            result = session.run(query)
            data = [dict(record) for record in result]
            
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.groupby("account_id").agg({
                "rapid_txns": "sum",
                "rapid_pass_ratio": "mean" # Average ratio across all rapid pairs
            }).reset_index()
            df.set_index("account_id", inplace=True)
        return df

    def extract_fan_out_features(self) -> pd.DataFrame:
        """
        Extracts fan-out behavior (sending to many distinct accounts).
        """
        query = """
        MATCH (a:Account)-[r:TRANSFERRED_TO]->(dest:Account)
        RETURN a.account_id AS account_id,
               count(DISTINCT dest.account_id) AS distinct_recipients,
               count(DISTINCT dest.account_id) * 1.0 / (count(r) + 1) AS fan_out_ratio
        """
        with self.driver.session() as session:
            result = session.run(query)
            data = [dict(record) for record in result]

        df = pd.DataFrame(data)
        if not df.empty:
            df.set_index("account_id", inplace=True)
        return df

    def get_all_features(self) -> pd.DataFrame:
        """
        Combine all graph features into a single DataFrame.
        """
        degree_df = self.extract_degree_features()
        rapid_df = self.extract_rapid_pass_through_features()
        fan_out_df = self.extract_fan_out_features()

        if degree_df.empty:
            return degree_df

        # Merge them all on account_id
        final_df = degree_df.copy()
        if not rapid_df.empty:
            final_df = final_df.join(rapid_df, how="left")
        else:
            final_df["rapid_txns"] = 0
            final_df["rapid_pass_ratio"] = 0.0

        if not fan_out_df.empty:
            final_df = final_df.join(fan_out_df, how="left")
        else:
            final_df["distinct_recipients"] = 0
            final_df["fan_out_ratio"] = 0.0

        # Fill NaNs from left joins
        final_df.fillna(0, inplace=True)
        return final_df
