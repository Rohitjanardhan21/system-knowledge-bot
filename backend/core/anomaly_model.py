import numpy as np
from collections import deque
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os


class AnomalyModel:
    """
    🧠 HYBRID ANOMALY ENGINE (STATISTICAL + ML)

    Combines:
    - Baseline deviation (Z-score)
    - Temporal trends
    - Pattern spikes
    - ML anomaly detection (Isolation Forest)

    Result = Robust + Explainable + Trainable
    """

    def __init__(self, max_history=200, model_path="models/anomaly.pkl"):
        self.history = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)

        self.model_path = model_path
        self.model = None
        self.scaler = StandardScaler()

        # buffer for training
        self.training_buffer = []

        # load existing model if available
        if os.path.exists(model_path):
            saved = joblib.load(model_path)
            self.model = saved["model"]
            self.scaler = saved["scaler"]

    # ---------------------------------------------------------
    # SAFE FEATURE CLEANING
    # ---------------------------------------------------------
    def clean_features(self, features):
        clean = {}

        for k, v in features.items():
            try:
                val = float(v)
                if np.isnan(val) or np.isinf(val):
                    val = 0.0
            except:
                val = 0.0

            clean[k] = val

        return clean

    # ---------------------------------------------------------
    def update(self, features: dict):
        features = self.clean_features(features)

        if not features:
            return

        self.history.append(features)
        self.timestamps.append(datetime.utcnow())

        # store for ML training
        self.training_buffer.append(list(features.values()))

    # ---------------------------------------------------------
    def has_sufficient_data(self):
        return len(self.history) >= 10

    # ---------------------------------------------------------
    # BASELINE
    # ---------------------------------------------------------
    def compute_baseline(self):
        if not self.has_sufficient_data():
            return None

        baseline = {}
        keys = set().union(*self.history)

        for k in keys:
            values = [h.get(k, 0) for h in self.history]

            baseline[k] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)) if len(values) > 1 else 0.0
            }

        return baseline

    # ---------------------------------------------------------
    def z_score(self, value, mean, std):
        if std < 1e-5:
            return 0.0
        return abs(value - mean) / std

    # ---------------------------------------------------------
    def temporal_anomaly(self):
        if len(self.history) < 5:
            return 0.0

        recent = list(self.history)[-5:]
        scores = []

        for key in set().union(*recent):
            vals = [r.get(key, 0) for r in recent]

            try:
                slope = np.polyfit(range(len(vals)), vals, 1)[0]
                scores.append(abs(slope))
            except:
                scores.append(0)

        return float(np.mean(scores)) if scores else 0.0

    # ---------------------------------------------------------
    def pattern_anomaly(self):
        if len(self.history) < 10:
            return 0.0

        recent = list(self.history)[-10:]
        spike_count, total = 0, 0

        for i in range(1, len(recent)):
            keys = set(recent[i]) | set(recent[i - 1])

            for k in keys:
                v1 = recent[i].get(k, 0)
                v0 = recent[i - 1].get(k, 0)

                if abs(v1 - v0) > 0.2:  # normalized scale fix
                    spike_count += 1
                total += 1

        return spike_count / total if total else 0.0

    # ---------------------------------------------------------
    # 🔥 ML TRAINING
    # ---------------------------------------------------------
    def train(self):
        if len(self.training_buffer) < 50:
            return False

        X = np.array(self.training_buffer)

        self.scaler.fit(X)
        X_scaled = self.scaler.transform(X)

        self.model = IsolationForest(
            n_estimators=150,
            contamination=0.05,
            random_state=42
        )

        self.model.fit(X_scaled)

        os.makedirs("models", exist_ok=True)
        joblib.dump({
            "model": self.model,
            "scaler": self.scaler
        }, self.model_path)

        return True

    # ---------------------------------------------------------
    # 🔥 ML SCORE
    # ---------------------------------------------------------
    def ml_score(self, features):
        if self.model is None:
            return 0.0

        try:
            x = np.array(list(features.values())).reshape(1, -1)
            x_scaled = self.scaler.transform(x)
            score = -self.model.decision_function(x_scaled)[0]
            return float(score)
        except:
            return 0.0

    # ---------------------------------------------------------
    def calibrate_confidence(self, score, stability_factor):
        confidence = 0.5

        if score > 2:
            confidence += 0.2
        elif score > 1:
            confidence += 0.1

        confidence += stability_factor * 0.2

        if len(self.history) < 20:
            confidence -= 0.3

        return max(0.1, min(0.95, confidence))

    # ---------------------------------------------------------
    def score(self, features: dict):

        features = self.clean_features(features)
        baseline = self.compute_baseline()

        if baseline is None:
            return {
                "score": 0.0,
                "severity": "low",
                "confidence": 0.1,
                "method": "insufficient_data"
            }

        # -----------------------------
        # STATISTICAL SCORE
        # -----------------------------
        total_score, count = 0, 0
        evidence = []

        for key, value in features.items():
            if key not in baseline:
                continue

            mean = baseline[key]["mean"]
            std = baseline[key]["std"]

            z = self.z_score(value, mean, std)
            total_score += z
            count += 1

            if z > 2:
                evidence.append(f"{key} deviates")

        avg_score = total_score / count if count else 0

        temporal_score = self.temporal_anomaly()
        pattern_score = self.pattern_anomaly()

        stat_score = (
            0.6 * avg_score +
            0.2 * temporal_score +
            0.2 * pattern_score
        )

        # -----------------------------
        # ML SCORE
        # -----------------------------
        ml_score = self.ml_score(features)

        # -----------------------------
        # 🔥 HYBRID FUSION
        # -----------------------------
        final_score = 0.6 * stat_score + 0.4 * ml_score

        # -----------------------------
        # SEVERITY
        # -----------------------------
        if final_score > 3:
            severity = "critical"
        elif final_score > 2:
            severity = "high"
        elif final_score > 1:
            severity = "medium"
        else:
            severity = "low"

        stability_factor = max(0, 1 - pattern_score)
        confidence = self.calibrate_confidence(final_score, stability_factor)

        return {
            "score": round(final_score, 2),
            "severity": severity,
            "confidence": round(confidence, 2),
            "stat_score": round(stat_score, 2),
            "ml_score": round(ml_score, 2),
            "temporal": round(temporal_score, 2),
            "pattern": round(pattern_score, 2),
            "evidence": evidence,
            "method": "hybrid"
        }

    # ---------------------------------------------------------
    def analyze(self, features):
        self.update(features)
        anomaly = self.score(features)

        return {
            "anomaly": anomaly
        }
