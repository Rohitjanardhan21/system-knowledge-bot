# ---------------------------------------------------------
# 🧠 MULTIMODAL INTELLIGENCE ENGINE (PRODUCTION-GRADE)
# ---------------------------------------------------------

from backend.signal_schema import build_signal_packet
from backend.feature_encoder import extract_features
from backend.anomaly_model import AnomalyModel
from backend.causal_engine import infer_cause

from collections import deque
from datetime import datetime
import numpy as np


# ---------------------------------------------------------
# 🧠 ENGINE CLASS (STATEFUL)
# ---------------------------------------------------------

class MultiModalEngine:

    def __init__(self):
        self.model = AnomalyModel()

        # Short-term memory (pattern detection)
        self.recent_history = deque(maxlen=50)

        # Long-term anomaly memory
        self.anomaly_history = deque(maxlen=100)

    # -----------------------------------------------------
    # 📊 NORMALIZATION (DOMAIN AGNOSTIC)
    # -----------------------------------------------------
    def normalize_features(self, features):

        return {
            "compute": min(1.0, features.get("compute", 0) / 100),
            "thermal": min(1.0, features.get("thermal", 0) / 100),
            "electrical": min(1.0, features.get("electrical", 0) / 100),

            "acoustic_energy": min(1.0, features.get("acoustic_energy", 0)),
            "vibration_intensity": min(1.0, features.get("vibration_intensity", 0)),
        }

    # -----------------------------------------------------
    # 🔮 PATTERN DETECTION (TEMPORAL)
    # -----------------------------------------------------
    def detect_patterns(self):

        if len(self.recent_history) < 10:
            return []

        patterns = []

        thermal_vals = [h["thermal"] for h in self.recent_history]
        vib_vals = [h["vibration_intensity"] for h in self.recent_history]

        # Sustained overheating
        if all(t > 0.7 for t in thermal_vals[-5:]):
            patterns.append({
                "type": "gradual_overheating",
                "severity": "high"
            })

        # Mechanical instability
        if np.std(vib_vals) > 0.2:
            patterns.append({
                "type": "mechanical_instability",
                "severity": "medium"
            })

        return patterns

    # -----------------------------------------------------
    # 🧠 ANOMALY INTERPRETATION
    # -----------------------------------------------------
    def interpret_anomaly(self, score):

        if score > 2.5:
            return {"level": "critical", "severity": 1.0}
        elif score > 1.5:
            return {"level": "high", "severity": 0.8}
        elif score > 0.7:
            return {"level": "medium", "severity": 0.5}
        else:
            return {"level": "low", "severity": 0.2}

    # -----------------------------------------------------
    # 🔗 CALIBRATED CONFIDENCE (IMPORTANT)
    # -----------------------------------------------------
    def compute_confidence(self, anomaly_score):

        data_points = len(self.recent_history)

        base = 0.5

        if anomaly_score > 1.5:
            base += 0.2

        if data_points > 20:
            base += 0.2
        else:
            base -= 0.2  # LOW DATA → LOW TRUST

        return round(max(0.1, min(0.95, base)), 2)

    # -----------------------------------------------------
    # 🧠 EVIDENCE BUILDER (ANTI-HALLUCINATION)
    # -----------------------------------------------------
    def build_evidence(self, features):

        evidence = []

        if features["compute"] > 0.8:
            evidence.append("High compute load")

        if features["thermal"] > 0.75:
            evidence.append("Elevated temperature")

        if features["vibration_intensity"] > 0.7:
            evidence.append("High vibration detected")

        if features["acoustic_energy"] > 0.7:
            evidence.append("Abnormal acoustic energy")

        return evidence

    # -----------------------------------------------------
    # 🧠 MAIN PROCESSOR
    # -----------------------------------------------------
    def process(self, raw):

        # 1️⃣ BUILD SIGNAL PACKET
        packet = build_signal_packet(raw)

        # 2️⃣ FEATURE EXTRACTION
        features = extract_features(packet)

        # 3️⃣ NORMALIZATION
        normalized = self.normalize_features(features)

        # 4️⃣ UPDATE MODEL
        self.model.update(normalized)

        # 5️⃣ ANOMALY SCORE
        anomaly_score = self.model.score(normalized)

        # 6️⃣ CAUSAL INFERENCE
        cause = infer_cause(normalized)

        # 7️⃣ STORE HISTORY
        self.recent_history.append(normalized)

        if anomaly_score > 1.0:
            self.anomaly_history.append({
                "time": datetime.utcnow().isoformat(),
                "score": anomaly_score,
                "cause": cause
            })

        # 8️⃣ PATTERNS
        patterns = self.detect_patterns()

        # 9️⃣ INTERPRETATION
        anomaly_info = self.interpret_anomaly(anomaly_score)

        # 🔟 CONFIDENCE
        confidence = self.compute_confidence(anomaly_score)

        # 11️⃣ EVIDENCE (CRITICAL)
        evidence = self.build_evidence(normalized)

        # -----------------------------------------------------
        # FINAL OUTPUT (AUDITABLE)
        # -----------------------------------------------------
        return {
            "timestamp": packet.get("timestamp"),

            "features": normalized,

            "anomaly": {
                "score": round(anomaly_score, 2),
                "level": anomaly_info["level"],
                "severity": anomaly_info["severity"]
            },

            "cause": {
                "label": cause,
                "confidence": confidence,
                "evidence": evidence
            },

            "patterns": patterns,

            "confidence": confidence,

            # 🔥 FOR TRUTH ENGINE
            "trace": {
                "data_points": len(self.recent_history),
                "model_type": "statistical_baseline",
                "validated": True if evidence else False
            }
        }


# ---------------------------------------------------------
# 🔥 GLOBAL INSTANCE
# ---------------------------------------------------------

multimodal_engine = MultiModalEngine()


# ---------------------------------------------------------
# 🚀 WRAPPER
# ---------------------------------------------------------

def process_multimodal(raw):
    return multimodal_engine.process(raw)
