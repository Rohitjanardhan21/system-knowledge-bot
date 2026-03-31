import numpy as np
from collections import deque
from datetime import datetime


class AnomalyModel:
    """
    🧠 Production-Grade Multi-Modal Anomaly Detection Engine

    Features:
    - Rolling statistical baseline
    - Z-score anomaly detection
    - Temporal + pattern anomaly detection
    - Confidence calibration (ANTI-HALLUCINATION)
    - Data sufficiency awareness
    - Explainable outputs
    """

    def __init__(self, max_history=200):
        self.history = deque(maxlen=max_history)
        self.timestamps = deque(maxlen=max_history)

    # ---------------------------------------------------------
    # UPDATE HISTORY
    # ---------------------------------------------------------
    def update(self, features: dict):
        self.history.append(features)
        self.timestamps.append(datetime.utcnow())

    # ---------------------------------------------------------
    # DATA SUFFICIENCY CHECK
    # ---------------------------------------------------------
    def has_sufficient_data(self):
        return len(self.history) >= 10

    # ---------------------------------------------------------
    # BASELINE (MEAN + STD)
    # ---------------------------------------------------------
    def compute_baseline(self):

        if not self.has_sufficient_data():
            return None

        keys = self.history[0].keys()

        baseline = {}
        for k in keys:
            values = [h[k] for h in self.history]

            baseline[k] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)) if len(values) > 1 else 0
            }

        return baseline

    # ---------------------------------------------------------
    # SAFE Z-SCORE
    # ---------------------------------------------------------
    def z_score(self, value, mean, std):
        if std < 1e-5:
            return 0.0
        return abs(value - mean) / std

    # ---------------------------------------------------------
    # TEMPORAL ANOMALY (TREND-BASED)
    # ---------------------------------------------------------
    def temporal_anomaly(self):

        if len(self.history) < 5:
            return 0.0

        recent = list(self.history)[-5:]
        scores = []

        for key in recent[0]:
            vals = [r[key] for r in recent]

            try:
                slope = np.polyfit(range(len(vals)), vals, 1)[0]
                scores.append(abs(slope))
            except:
                scores.append(0)

        return float(np.mean(scores))

    # ---------------------------------------------------------
    # PATTERN ANOMALY (SPIKES / INSTABILITY)
    # ---------------------------------------------------------
    def pattern_anomaly(self):

        if len(self.history) < 10:
            return 0.0

        recent = list(self.history)[-10:]
        spike_count = 0

        for i in range(1, len(recent)):
            for k in recent[i]:
                if abs(recent[i][k] - recent[i - 1][k]) > 20:
                    spike_count += 1

        return spike_count / (len(recent) * len(recent[0]))

    # ---------------------------------------------------------
    # 🔥 CONFIDENCE CALIBRATION (CRITICAL)
    # ---------------------------------------------------------
    def calibrate_confidence(self, score, stability_factor):

        confidence = 0.5

        # anomaly contribution
        if score > 2:
            confidence += 0.2
        elif score > 1:
            confidence += 0.1

        # stability factor (inverse of noise)
        confidence += stability_factor * 0.2

        # penalize low data
        if len(self.history) < 20:
            confidence -= 0.3

        return max(0.1, min(0.95, confidence))

    # ---------------------------------------------------------
    # 🔥 MAIN ANOMALY SCORE
    # ---------------------------------------------------------
    def score(self, features: dict):

        baseline = self.compute_baseline()

        if baseline is None:
            return {
                "score": 0.0,
                "severity": "low",
                "confidence": 0.1,
                "details": {},
                "evidence": ["Insufficient historical data"]
            }

        z_scores = {}
        total_score = 0
        evidence = []

        for key in features:
            mean = baseline[key]["mean"]
            std = baseline[key]["std"]

            z = self.z_score(features[key], mean, std)
            z_scores[key] = round(z, 2)

            total_score += z

            # Evidence collection (NO HALLUCINATION)
            if z > 2:
                evidence.append(f"{key} deviates significantly from baseline")

        avg_score = total_score / len(features)

        temporal_score = self.temporal_anomaly()
        pattern_score = self.pattern_anomaly()

        final_score = (
            0.6 * avg_score +
            0.2 * temporal_score +
            0.2 * pattern_score
        )

        # ---------------------------------------------------------
        # SEVERITY
        # ---------------------------------------------------------
        if final_score > 3:
            severity = "critical"
        elif final_score > 2:
            severity = "high"
        elif final_score > 1:
            severity = "medium"
        else:
            severity = "low"

        # ---------------------------------------------------------
        # STABILITY FACTOR (LESS noise = more trust)
        # ---------------------------------------------------------
        stability_factor = max(0, 1 - pattern_score)

        confidence = self.calibrate_confidence(final_score, stability_factor)

        return {
            "score": round(final_score, 2),
            "severity": severity,
            "confidence": round(confidence, 2),
            "details": z_scores,
            "temporal": round(temporal_score, 2),
            "pattern": round(pattern_score, 2),
            "evidence": evidence
        }

    # ---------------------------------------------------------
    # 🔮 PREDICTION
    # ---------------------------------------------------------
    def predict_next(self):

        if len(self.history) < 5:
            return None

        prediction = {}

        for key in self.history[0]:
            values = [h[key] for h in list(self.history)[-5:]]

            try:
                slope = np.polyfit(range(len(values)), values, 1)[0]
                prediction[key] = float(values[-1] + slope * 2)
            except:
                prediction[key] = values[-1]

        return prediction

    # ---------------------------------------------------------
    # 🔍 VALIDATION (TRUTH HOOK)
    # ---------------------------------------------------------
    def validate(self, anomaly):

        if anomaly["confidence"] > 0.9 and anomaly["score"] < 1:
            return {
                "valid": False,
                "reason": "High confidence but low anomaly score"
            }

        return {"valid": True}

    # ---------------------------------------------------------
    # 📊 FULL PIPELINE
    # ---------------------------------------------------------
    def analyze(self, features):

        self.update(features)

        anomaly = self.score(features)
        prediction = self.predict_next()
        validation = self.validate(anomaly)

        return {
            "anomaly": anomaly,
            "prediction": prediction,
            "validation": validation
        }
