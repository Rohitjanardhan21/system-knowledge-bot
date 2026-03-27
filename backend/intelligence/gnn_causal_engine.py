import numpy as np


class GNNCausalEngine:
    """
    Lightweight GNN-inspired causal engine using correlation matrix.

    Features:
    - Handles NaN safely
    - Normalizes inputs
    - Optional noise filtering
    - Safe fallback if not trained
    """

    def __init__(self, threshold=0.3):
        """
        threshold: minimum correlation strength to keep (noise filter)
        """
        self.weights = None
        self.threshold = threshold

    # -----------------------------------------
    # Train on historical data
    # -----------------------------------------
    def train(self, history_matrix):
        """
        history_matrix: numpy array of shape [time_steps, features]
        features = [cpu, memory, disk]
        """

        if history_matrix is None or len(history_matrix) < 5:
            # Not enough data to learn
            self.weights = None
            return

        try:
            # Compute correlation matrix
            corr = np.corrcoef(history_matrix.T)

            # Replace NaN values with 0
            corr = np.nan_to_num(corr)

            # Remove weak relationships (noise filtering)
            corr[np.abs(corr) < self.threshold] = 0

            self.weights = corr

        except Exception:
            self.weights = None

    # -----------------------------------------
    # Predict influence
    # -----------------------------------------
    def predict_influence(self, state_vector):
        """
        state_vector: list or array [cpu, memory, disk]
        returns: influence vector
        """

        if self.weights is None:
            return [0.0, 0.0, 0.0]

        try:
            state_vector = np.array(state_vector, dtype=float)

            # Normalize to 0–1 range
            state_vector = state_vector / 100.0

            influence = np.dot(self.weights, state_vector)

            # Clip to safe range
            influence = np.clip(influence, 0, 1)

            return influence.round(3).tolist()

        except Exception:
            return [0.0, 0.0, 0.0]

    # -----------------------------------------
    # Optional: explain relationships
    # -----------------------------------------
    def explain(self):
        """
        Returns readable relationships
        """
        if self.weights is None:
            return {}

        labels = ["cpu", "memory", "disk"]
        explanation = {}

        for i, src in enumerate(labels):
            explanation[src] = {}
            for j, tgt in enumerate(labels):
                if i != j and self.weights[i][j] != 0:
                    explanation[src][tgt] = float(round(self.weights[i][j], 2))

        return explanation
