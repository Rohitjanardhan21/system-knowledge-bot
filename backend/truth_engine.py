# ---------------------------------------------------------
# 🧠 TRUTH ENGINE (ANTI-HALLUCINATION + VALIDATION LAYER)
# ---------------------------------------------------------

from datetime import datetime


class TruthEngine:

    def __init__(self):
        self.validation_history = []

    # -----------------------------------------------------
    # 🔍 RAW vs FEATURE CONSISTENCY
    # -----------------------------------------------------
    def validate_signal_consistency(self, raw, features):
        issues = []

        cpu_raw = raw.get("cpu", 0)
        cpu_feat = features.get("compute", 0)

        if abs(cpu_raw - cpu_feat) > 10:
            issues.append("CPU mismatch between raw and features")

        return issues

    # -----------------------------------------------------
    # 🔍 ANOMALY GROUNDING CHECK
    # -----------------------------------------------------
    def validate_anomaly(self, anomaly_score, features):
        issues = []

        if anomaly_score > 1.5:
            # ensure anomaly has signal support
            if (
                features.get("compute", 0) < 50 and
                features.get("thermal", 0) < 50 and
                features.get("vibration_intensity", 0) < 0.3
            ):
                issues.append("High anomaly score without supporting signals")

        return issues

    # -----------------------------------------------------
    # 🔍 DECISION VALIDATION
    # -----------------------------------------------------
    def validate_decision(self, decision, features):
        issues = []

        action = decision.get("action", "none")

        # Example: don't allow aggressive action on low load
        if action == "reduce_compute_load" and features.get("compute", 0) < 40:
            issues.append("Action 'reduce_compute_load' not justified by CPU level")

        return issues

    # -----------------------------------------------------
    # 🔍 CONFIDENCE VALIDATION
    # -----------------------------------------------------
    def validate_confidence(self, decision, data_points):
        issues = []

        confidence = decision.get("confidence", 0)

        if confidence > 0.9 and data_points < 20:
            issues.append("High confidence with insufficient data")

        return issues

    # -----------------------------------------------------
    # 🔍 ACTION SAFETY CHECK (CRITICAL)
    # -----------------------------------------------------
    def validate_action_safety(self, decision, features):
        issues = []

        action = decision.get("action", "")

        # Prevent risky actions without evidence
        if action == "immediate_stabilization" and features.get("compute", 0) < 60:
            issues.append("Unsafe critical action triggered without sufficient load")

        return issues

    # -----------------------------------------------------
    # 🔍 CAUSE VALIDATION
    # -----------------------------------------------------
    def validate_cause(self, cause, features):
        issues = []

        if cause == "thermal_overload" and features.get("thermal", 0) < 60:
            issues.append("Thermal overload inferred without high temperature")

        if cause == "mechanical_fault" and features.get("vibration_intensity", 0) < 0.4:
            issues.append("Mechanical fault inferred without vibration signal")

        return issues

    # -----------------------------------------------------
    # 🔥 MASTER VALIDATION PIPELINE
    # -----------------------------------------------------
    def validate(self, raw, features, decision, anomaly_score, cause, data_points=50):

        issues = []

        # Run all checks
        issues += self.validate_signal_consistency(raw, features)
        issues += self.validate_anomaly(anomaly_score, features)
        issues += self.validate_decision(decision, features)
        issues += self.validate_confidence(decision, data_points)
        issues += self.validate_action_safety(decision, features)
        issues += self.validate_cause(cause, features)

        valid = len(issues) == 0

        result = {
            "valid": valid,
            "issues": issues,
            "confidence_adjustment": self.adjust_confidence(decision, issues),
            "timestamp": datetime.utcnow().isoformat()
        }

        self.validation_history.append(result)

        # keep last 100
        self.validation_history = self.validation_history[-100:]

        return result

    # -----------------------------------------------------
    # 🔥 AUTO CONFIDENCE CORRECTION
    # -----------------------------------------------------
    def adjust_confidence(self, decision, issues):

        base_conf = decision.get("confidence", 0.5)

        if not issues:
            return base_conf

        penalty = min(0.5, 0.1 * len(issues))

        return max(0.1, base_conf - penalty)

    # -----------------------------------------------------
    # 📚 HISTORY ACCESS
    # -----------------------------------------------------
    def get_validation_history(self):
        return self.validation_history[-10:]
