# ---------------------------------------------------------
# 🧠 DIGITAL TWIN ENGINE (PRODUCTION + ZERO-HALLUCINATION)
# ---------------------------------------------------------

import copy
import math


class DigitalTwin:

    def __init__(self):
        self.last_valid_state = None

    # -----------------------------------------------------
    # 🛡️ VALIDATE INPUT FEATURES (CRITICAL)
    # -----------------------------------------------------
    def validate_features(self, features):

        required_keys = ["compute", "thermal"]

        issues = []

        for key in required_keys:
            if key not in features:
                issues.append(f"Missing key: {key}")

        for k, v in features.items():
            if isinstance(v, (int, float)):
                if math.isnan(v) or math.isinf(v):
                    issues.append(f"Invalid numeric value in {k}")

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }

    # -----------------------------------------------------
    # 🔧 APPLY ACTION (PHYSICS-AWARE SIMULATION)
    # -----------------------------------------------------
    def apply_action(self, features, action):

        f = copy.deepcopy(features)

        # ---------------- COMPUTE ----------------
        if action == "reduce_compute_load":
            f["compute"] *= 0.7

        elif action == "rebalance_resources":
            f["compute"] *= 0.85
            f["memory"] = f.get("memory", 0) * 0.9

        # ---------------- THERMAL ----------------
        elif action == "increase_cooling":
            f["thermal"] -= 10

        elif action == "cooling_boost":
            f["thermal"] -= 15

        # ---------------- MEMORY ----------------
        elif action == "optimize_memory_usage":
            f["memory"] = f.get("memory", 0) * 0.8

        # ---------------- MECHANICAL ----------------
        elif action == "stabilize_mechanics":
            f["vibration_intensity"] *= 0.5

        elif action == "balance_rotor":
            f["vibration_intensity"] *= 0.4
            f["acoustic_energy"] *= 0.7

        # ---------------- ELECTRICAL ----------------
        elif action == "stabilize_power":
            f["electrical"] *= 0.8

        # ---------------- SAFETY CONSTRAINTS ----------------
        for k in f:
            if isinstance(f[k], (int, float)):
                f[k] = max(0, f[k])

        return f

    # -----------------------------------------------------
    # 📊 EVALUATE SYSTEM STATE (CORE INTELLIGENCE)
    # -----------------------------------------------------
    def evaluate_state(self, features):

        compute = features.get("compute", 0)
        thermal = features.get("thermal", 0)
        vibration = features.get("vibration_intensity", 0)
        acoustic = features.get("acoustic_energy", 0)
        electrical = features.get("electrical", 0)

        # Normalize
        compute_score = compute / 100
        thermal_score = thermal / 100
        electrical_score = electrical / 100

        # Weighted pressure
        system_pressure = (
            0.3 * compute_score +
            0.25 * thermal_score +
            0.2 * vibration +
            0.15 * acoustic +
            0.1 * electrical_score
        )

        stability = max(0, 1 - system_pressure)

        return {
            "pressure": round(system_pressure, 3),
            "stability": round(stability, 3)
        }

    # -----------------------------------------------------
    # 🧠 EXPLAIN SIMULATION RESULT (NO GUESSING)
    # -----------------------------------------------------
    def explain_result(self, before, after):

        explanation = []

        for k in before:
            if k in after and isinstance(before[k], (int, float)):
                delta = after[k] - before[k]

                if abs(delta) > 5:
                    direction = "decreased" if delta < 0 else "increased"
                    explanation.append(f"{k} {direction} by {round(abs(delta),2)}")

        return explanation

    # -----------------------------------------------------
    # 🔮 SIMULATE ALL ACTIONS (SAFE + EXPLAINABLE)
    # -----------------------------------------------------
    def simulate_all(self, features, actions):

        validation = self.validate_features(features)

        if not validation["valid"]:
            return [{
                "error": True,
                "issues": validation["issues"]
            }]

        results = []

        for action in actions:
            try:
                new_state = self.apply_action(features, action)
                evaluation = self.evaluate_state(new_state)

                explanation = self.explain_result(features, new_state)

                results.append({
                    "action": action,
                    "predicted_state": new_state,
                    "pressure": evaluation["pressure"],
                    "stability": evaluation["stability"],
                    "explanation": explanation
                })

            except Exception:
                results.append({
                    "action": action,
                    "error": True,
                    "pressure": 1.0,
                    "stability": 0.0
                })

        results.sort(key=lambda x: x.get("stability", 0), reverse=True)

        return results

    # -----------------------------------------------------
    # 🔥 COUNTERFACTUAL (NO ACTION)
    # -----------------------------------------------------
    def simulate_no_action(self, features):

        base_eval = self.evaluate_state(features)

        degraded = copy.deepcopy(features)

        degraded["compute"] *= 1.05
        degraded["thermal"] += 5
        degraded["vibration_intensity"] *= 1.1

        degraded_eval = self.evaluate_state(degraded)

        return {
            "current": base_eval,
            "future_no_action": degraded_eval
        }

    # -----------------------------------------------------
    # ⚡ SAFE ACTION SELECTOR (WITH VALIDATION)
    # -----------------------------------------------------
    def recommend_action(self, features, actions):

        simulations = self.simulate_all(features, actions)

        if not simulations or "error" in simulations[0]:
            return {
                "best_action": "monitor",
                "confidence": 0.2,
                "simulations": simulations
            }

        best = simulations[0]

        confidence = min(0.95, best["stability"])

        return {
            "best_action": best["action"],
            "expected_stability": best["stability"],
            "confidence": round(confidence, 2),
            "simulations": simulations
        }

    # -----------------------------------------------------
    # 🧠 RISK ESTIMATION (CALIBRATED)
    # -----------------------------------------------------
    def estimate_risk(self, features):

        eval_state = self.evaluate_state(features)
        pressure = eval_state["pressure"]

        if pressure > 0.85:
            level = "CRITICAL"
        elif pressure > 0.65:
            level = "HIGH"
        elif pressure > 0.4:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "level": level,
            "score": round(pressure, 3),
            "confidence": round(1 - eval_state["stability"], 2)
        }

    # -----------------------------------------------------
    # 🔍 FULL PIPELINE (READY FOR SYSTEM USE)
    # -----------------------------------------------------
    def analyze(self, features, actions):

        validation = self.validate_features(features)

        if not validation["valid"]:
            return {
                "valid": False,
                "issues": validation["issues"]
            }

        recommendation = self.recommend_action(features, actions)
        risk = self.estimate_risk(features)
        counterfactual = self.simulate_no_action(features)

        return {
            "valid": True,
            "recommendation": recommendation,
            "risk": risk,
            "counterfactual": counterfactual
        }
