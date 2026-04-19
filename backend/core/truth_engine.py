# ---------------------------------------------------------
# 🧠 TRUTH ENGINE (ROBUST VALIDATION LAYER)
# ---------------------------------------------------------

from datetime import datetime


class TruthEngine:

    def __init__(self):
        self.validation_history = []

    # -----------------------------------------------------
    # 🔧 SAFE GET
    # -----------------------------------------------------
    def safe_get(self, d, key, default=0):
        try:
            return float(d.get(key, default))
        except:
            return default

    # -----------------------------------------------------
    # 🔍 SIGNAL CONSISTENCY
    # -----------------------------------------------------
    def validate_signal_consistency(self, raw, features):
        issues = []

        cpu_raw = self.safe_get(raw, "cpu")
        cpu_feat = self.safe_get(features, "compute") * 100  # normalize

        if abs(cpu_raw - cpu_feat) > 25:
            issues.append("CPU mismatch between raw and features")

        return issues

    # -----------------------------------------------------
    # 🔍 ANOMALY GROUNDING
    # -----------------------------------------------------
    def validate_anomaly(self, anomaly_score, features):
        issues = []

        compute = self.safe_get(features, "compute")
        thermal = self.safe_get(features, "thermal")
        vibration = self.safe_get(features, "vibration_intensity")

        if anomaly_score > 1.5:
            if compute < 0.4 and thermal < 0.4 and vibration < 0.3:
                issues.append("Anomaly lacks supporting signals")

        return issues

    # -----------------------------------------------------
    # 🔍 DECISION VALIDATION
    # -----------------------------------------------------
    def validate_decision(self, decision, features):
        issues = []

        action = decision.get("action", "")
        compute = self.safe_get(features, "compute")

        if action == "reduce_compute_load" and compute < 0.4:
            issues.append("CPU too low for compute reduction")

        return issues

    # -----------------------------------------------------
    # 🔍 CONFIDENCE VALIDATION
    # -----------------------------------------------------
    def validate_confidence(self, decision, data_points):
        issues = []

        confidence = decision.get("confidence", 0)

        if confidence > 0.9 and data_points < 20:
            issues.append("High confidence with low data")

        return issues

    # -----------------------------------------------------
    # 🔍 ACTION SAFETY
    # -----------------------------------------------------
    def validate_action_safety(self, decision, features):
        issues = []

        action = decision.get("action", "")
        compute = self.safe_get(features, "compute")

        if action == "immediate_stabilization" and compute < 0.6:
            issues.append("Unsafe stabilization without load")

        return issues

    # -----------------------------------------------------
    # 🔍 CAUSE VALIDATION (ROBUST)
    # -----------------------------------------------------
    def validate_cause(self, cause, features):
        issues = []

        if isinstance(cause, dict):
            cause = cause.get("type")

        thermal = self.safe_get(features, "thermal")
        vibration = self.safe_get(features, "vibration_intensity")

        if cause == "thermal_overload" and thermal < 0.6:
            issues.append("Thermal overload not supported")

        if cause == "mechanical_fault" and vibration < 0.4:
            issues.append("Mechanical fault not supported")

        return issues

    # -----------------------------------------------------
    # 🔥 MASTER VALIDATION
    # -----------------------------------------------------
    def validate(self, raw, features, decision, anomaly_score, cause, data_points=50):

        issues = []

        issues += self.validate_signal_consistency(raw, features)
        issues += self.validate_anomaly(anomaly_score, features)
        issues += self.validate_decision(decision, features)
        issues += self.validate_confidence(decision, data_points)
        issues += self.validate_action_safety(decision, features)
        issues += self.validate_cause(cause, features)

        valid = len(issues) == 0

        adjusted_conf = self.adjust_confidence(decision, issues)

        result = {
            "valid": valid,
            "issues": issues,
            "confidence_adjustment": adjusted_conf,
            "timestamp": datetime.utcnow().isoformat()
        }

        # 🔥 APPLY ADJUSTMENT DIRECTLY
        decision["confidence"] = adjusted_conf

        self.validation_history.append(result)
        self.validation_history = self.validation_history[-100:]

        return result

    # -----------------------------------------------------
    # 🔥 CONFIDENCE CORRECTION
    # -----------------------------------------------------
    def adjust_confidence(self, decision, issues):

        base_conf = decision.get("confidence", 0.5)

        if not issues:
            return base_conf

        penalty = min(0.5, 0.1 * len(issues))
        return max(0.1, base_conf - penalty)

    # -----------------------------------------------------
    # 📚 HISTORY
    # -----------------------------------------------------
    def get_validation_history(self):
        return self.validation_history[-10:]
