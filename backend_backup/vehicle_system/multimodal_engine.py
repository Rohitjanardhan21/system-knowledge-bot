# ---------------------------------------------------------
# 🧠 MULTIMODAL INTELLIGENCE ENGINE (LEVEL 9 - PERCEPTION AI)
# ---------------------------------------------------------

from backend.core.anomaly_model import AnomalyModel
from backend.core.feature_encoder import extract_features
from backend.core.causal_engine import infer_cause

from backend.vehicle_system.vehicle_context import enrich_vehicle_context
from backend.vehicle_system.vehicle_causal_engine import infer_vehicle_cause
from backend.vehicle_system.vehicle_signal_analyzer import analyze_vehicle_signals
from backend.vehicle_system.vehicle_hazard_engine import compute_vehicle_hazard
from backend.vehicle_system.vision_engine import detect_objects

from backend.signal_schema import build_signal_packet

from backend.vehicle_system.adaptive_learning import adaptive_learning
from backend.vehicle_system.context_memory import context_memory

from backend.core.explanation_engine import explanation_engine
from backend.vehicle_system.future_engine import future_engine
from backend.core.meta_engine import meta_engine

from collections import deque
import numpy as np
import time


# ---------------------------------------------------------
# 🔮 PREDICTIVE ENGINE
# ---------------------------------------------------------
class PredictiveEngine:
    def __init__(self):
        self.history = deque(maxlen=50)

    def update(self, signals):
        self.history.append(signals)

    def predict(self):
        if len(self.history) < 5:
            return []

        temps = [h.get("thermal", 0) for h in self.history]
        vib = [h.get("vibration_intensity", 0) for h in self.history]

        predictions = []

        if temps[-1] - temps[0] > 0.12:
            predictions.append({
                "type": "engine_overheating",
                "time_to_risk": "2-5 min",
                "confidence": round(min(1.0, abs(temps[-1] - temps[0])), 2)
            })

        if np.std(vib) > 0.18:
            predictions.append({
                "type": "mechanical_instability",
                "time_to_risk": "immediate",
                "confidence": round(min(1.0, np.std(vib)), 2)
            })

        return predictions


# ---------------------------------------------------------
# ⚙️ COMPONENT HEALTH
# ---------------------------------------------------------
class ComponentHealthModel:
    def analyze(self, signals, thresholds):
        issues = []

        if signals.get("thermal", 0) > thresholds["thermal"]:
            issues.append({
                "component": "engine",
                "issue": "overheating_risk",
                "severity": "HIGH"
            })

        if signals.get("vibration_intensity", 0) > thresholds["vibration"]:
            issues.append({
                "component": "suspension",
                "issue": "mechanical_stress",
                "severity": "MEDIUM"
            })

        return issues


# ---------------------------------------------------------
# 🚗 DRIVER MODEL
# ---------------------------------------------------------
class DriverBehaviorModel:
    def __init__(self):
        self.profile = {"aggressive": False, "smooth": True}

    def update(self, raw):
        accel = raw.get("acceleration", 0)
        brake = raw.get("braking", 0)

        if accel > 8 or brake > 8:
            self.profile["aggressive"] = True
            self.profile["smooth"] = False

        return self.profile


# ---------------------------------------------------------
# ⚠️ ADVISORY ENGINE
# ---------------------------------------------------------
class AdvisoryEngine:
    def generate(self, predictions, issues, driver_profile, confidence):
        advisories = []

        for p in predictions:
            if p["type"] == "engine_overheating":
                advisories.append(
                    f"Reduce speed (heat rising {int(p['confidence']*100)}%)"
                )

        for i in issues:
            if i["component"] == "suspension":
                advisories.append("Rough surface detected — slow down")

        if driver_profile["aggressive"]:
            advisories.append("Aggressive driving detected")

        if confidence < 0.5:
            advisories.append("Low confidence — verify conditions")

        return advisories


# ---------------------------------------------------------
# 🧠 MAIN ENGINE
# ---------------------------------------------------------
class MultiModalEngine:

    def __init__(self):
        self.model = AnomalyModel()

        self.recent_history = deque(maxlen=50)
        self.temporal_window = deque(maxlen=20)

        self.predictive = PredictiveEngine()
        self.component_model = ComponentHealthModel()
        self.driver_model = DriverBehaviorModel()
        self.advisory = AdvisoryEngine()

    # -----------------------------------------------------
    def normalize_features(self, f):
        return {
            "compute": min(1.0, f.get("compute", 0) / 100),
            "thermal": min(1.0, f.get("thermal", 0) / 100),
            "electrical": min(1.0, f.get("electrical", 0) / 100),
            "acoustic_energy": min(1.0, f.get("acoustic_energy", 0)),
            "vibration_intensity": min(1.0, f.get("vibration_intensity", 0)),
        }

    def interpret_anomaly(self, score):
        if score > 2.5: return "CRITICAL"
        elif score > 1.5: return "HIGH"
        elif score > 0.7: return "MEDIUM"
        return "LOW"

    def smooth_hazard(self, current):
        self.temporal_window.append(current)
        if len(self.temporal_window) < 5:
            return current
        return float(np.mean(self.temporal_window))

    def detect_patterns(self):
        if len(self.recent_history) < 10:
            return []

        vib = [h.get("vibration_intensity", 0) for h in self.recent_history]
        temp = [h.get("thermal", 0) for h in self.recent_history]

        patterns = []

        if np.mean(vib) > 0.55:
            patterns.append({"pattern": "persistent_vibration", "severity": "MEDIUM"})

        if temp[-1] > temp[0] + 0.15:
            patterns.append({"pattern": "thermal_rise_trend", "severity": "HIGH"})

        if np.std(vib) > 0.25:
            patterns.append({"pattern": "unstable_surface", "severity": "MEDIUM"})

        return patterns

    def calibrate_confidence(self):
        if len(self.recent_history) < 5:
            return 0.5

        vals = [h.get("vibration_intensity", 0) for h in self.recent_history]
        var = np.var(vals)

        uncertainty = min(1.0, var)
        return round(1 - uncertainty, 2)

    # -----------------------------------------------------
    def process(self, raw):

        # -----------------------------
        # FEATURE PIPELINE
        # -----------------------------
        packet = build_signal_packet(raw)
        features = extract_features(packet)
        normalized = self.normalize_features(features)
        normalized = enrich_vehicle_context(normalized, raw.get("vehicle_type", "generic"))

        # -----------------------------
        # 👁️ VISION (YOLO + TRACKING)
        # -----------------------------
        vision, obstacle, prediction = {}, None, None
        vision_hazard = 0
        objects = []

        frame = raw.get("camera_frame")

        if frame is not None:
            try:
                detections = detect_objects(frame)

                objects = detections.get("objects", [])
                vision_hazard = detections.get("collision_risk", 0)

                if objects:
                    obj = objects[0]
                    obstacle = obj
                    vision = obj

                    prediction = {
                        "time_to_impact": obj.get("time_to_impact"),
                        "velocity": obj.get("velocity")
                    }

            except Exception as e:
                print("Vision error:", e)

        # -----------------------------
        # ANOMALY
        # -----------------------------
        try:
            self.model.update(normalized)
            anomaly = self.model.score(normalized)
            anomaly_score = float(anomaly.get("score", anomaly))
        except:
            anomaly_score = 0.0

        adaptive_learning.update(normalized, anomaly_score)
        thresholds = adaptive_learning.get_thresholds()

        # -----------------------------
        # CAUSAL
        # -----------------------------
        system_cause = infer_cause(normalized)
        vehicle_cause = infer_vehicle_cause(normalized)

        # -----------------------------
        # HISTORY
        # -----------------------------
        self.recent_history.append(normalized)
        signals = analyze_vehicle_signals(normalized, list(self.recent_history))

        # -----------------------------
        # PREDICTION
        # -----------------------------
        self.predictive.update(normalized)
        predictions = self.predictive.predict()

        # -----------------------------
        # COMPONENT HEALTH
        # -----------------------------
        issues = self.component_model.analyze(normalized, thresholds)

        # -----------------------------
        # DRIVER
        # -----------------------------
        driver_profile = self.driver_model.update(raw)

        # -----------------------------
        # CONFIDENCE
        # -----------------------------
        confidence = self.calibrate_confidence()

        context_memory.update(issues)
        memory = context_memory.get_recent()

        # -----------------------------
        # FUTURE + EXPLANATION
        # -----------------------------
        future = future_engine.simulate(normalized)

        explanation = explanation_engine.generate(
            normalized,
            anomaly_score,
            vehicle_cause,
            predictions
        )

        meta = meta_engine.evaluate(confidence, anomaly_score)

        # -----------------------------
        # COLLISION ALERT
        # -----------------------------
        collision_alert = None
        if objects:
            tti = objects[0].get("time_to_impact")
            if tti is not None:
                if tti < 2:
                    collision_alert = "IMMINENT"
                elif tti < 5:
                    collision_alert = "POSSIBLE"

        # -----------------------------
        # ADVISORIES
        # -----------------------------
        advisories = self.advisory.generate(
            predictions,
            issues,
            driver_profile,
            confidence
        )

        # -----------------------------
        # HAZARD (FUSION)
        # -----------------------------
        base_hazard = compute_vehicle_hazard(
            anomaly_score,
            vehicle_cause.get("type", "unknown"),
            signals,
            prediction
        )

        raw_hazard = min(1.0, base_hazard * 0.6 + vision_hazard * 0.4)
        hazard = self.smooth_hazard(raw_hazard)

        # -----------------------------
        # FINAL OUTPUT
        # -----------------------------
        return {
            "timestamp": time.time(),

            "perception": {
                "vision": vision,
                "objects": objects,
                "signals": signals,
                "features": normalized
            },

            "analysis": {
                "anomaly_score": anomaly_score,
                "anomaly_level": self.interpret_anomaly(anomaly_score),
                "causes": {
                    "system": system_cause,
                    "vehicle": vehicle_cause
                }
            },

            "prediction": {
                "future": future,
                "predictions": predictions,
                "collision_alert": collision_alert,
                "pre_impact": {
                    "obstacle": obstacle,
                    "prediction": prediction
                }
            },

            "intelligence": {
                "confidence": confidence,
                "meta": meta,
                "patterns": self.detect_patterns()
            },

            "learning": {
                "adaptive_thresholds": thresholds,
                "context_memory": memory
            },

            "decision_support": {
                "component_issues": issues,
                "driver_profile": driver_profile,
                "advisories": advisories,
                "action_required": False
            },

            "risk": {
                "hazard": hazard
            },

            "explainability": {
                "chain": explanation
            }
        }


# ---------------------------------------------------------
# GLOBAL
# ---------------------------------------------------------
multimodal_engine = MultiModalEngine()


def process_multimodal(raw):
    return multimodal_engine.process(raw)
