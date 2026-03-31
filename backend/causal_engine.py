# ---------------------------------------------------------
# 🧠 MULTI-MODAL CAUSAL ENGINE (PRODUCTION + SAFE)
# ---------------------------------------------------------

from typing import List, Dict, Any

# ---------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------
HIGH_CPU = 80
MODERATE_CPU = 40
HIGH_MEM = 75
HIGH_DISK = 85
HIGH_TEMP = 75
HIGH_VIBRATION = 0.7
HIGH_ELECTRICAL = 90


# ---------------------------------------------------------
# CONFIDENCE CALIBRATION (ANTI-HALLUCINATION)
# ---------------------------------------------------------
def calibrate_confidence(anomaly_score, evidence_count, data_points=50):
    base = 0.4

    if anomaly_score > 1.5:
        base += 0.2

    if evidence_count >= 2:
        base += 0.2

    if data_points < 20:
        base -= 0.3  # low data penalty

    return round(max(0.1, min(0.95, base)), 2)


# ---------------------------------------------------------
# SEVERITY
# ---------------------------------------------------------
def compute_severity(cpu, mem, disk, anomaly_score=0):
    base = (cpu * 0.4 + mem * 0.3 + disk * 0.2) / 100
    return round(min(1.0, base + anomaly_score * 0.2), 2)


# ---------------------------------------------------------
# ACTION MAP
# ---------------------------------------------------------
def map_action(cause_type):
    return {
        "cpu_overload": "reduce_compute_load",
        "moderate_cpu_load": "optimize_processes",
        "memory_pressure": "free_memory",
        "disk_io_bottleneck": "optimize_io",

        "thermal_overload": "increase_cooling",
        "mechanical_fault": "inspect_mechanics",
        "electrical_instability": "check_power",

        "background_load": "observe"
    }.get(cause_type, "observe")


# ---------------------------------------------------------
# RISK PROPAGATION
# ---------------------------------------------------------
def propagate_risk(base, length):
    return min(1.0, round(base + 0.1 * length, 2))


# ---------------------------------------------------------
# PROCESS FILTER
# ---------------------------------------------------------
def is_valid_process(p):
    name = (p.get("name") or "").lower()

    if not name:
        return False

    if any(x in name for x in ["idle", "system idle"]):
        return False

    if p.get("cpu", 0) < 1:
        return False

    return True


# ---------------------------------------------------------
# 🧠 CAUSAL ENGINE
# ---------------------------------------------------------
class CausalEngine:

    # -----------------------------------------------------
    # TOP CONTRIBUTORS
    # -----------------------------------------------------
    def get_top_contributors(self, processes, metric="cpu", top_n=5):
        valid = [p for p in processes if is_valid_process(p)]

        if not valid:
            return []

        valid.sort(key=lambda x: x.get(metric, 0), reverse=True)
        return valid[:top_n]

    # -----------------------------------------------------
    # IMPACT CHAIN
    # -----------------------------------------------------
    def build_chain(self, cause_type, process=None):

        base = []
        if process:
            base.append(f"Process: {process}")

        mapping = {
            "cpu_overload": ["CPU usage ↑", "Scheduler pressure ↑", "Latency ↑"],
            "thermal_overload": ["Heat ↑", "Efficiency ↓", "Hardware stress ↑"],
            "mechanical_fault": ["Vibration ↑", "Wear ↑", "Failure risk ↑"],
            "electrical_instability": ["Voltage fluctuation", "Instability ↑"],
            "moderate_cpu_load": ["Load ↑", "Performance impact ↑"],
            "background_load": ["Normal variation"]
        }

        return base + mapping.get(cause_type, ["System impact ↑"])

    # -----------------------------------------------------
    # 🔍 BUILD EVIDENCE (ANTI-HALLUCINATION CORE)
    # -----------------------------------------------------
    def build_evidence(self, cpu, mem, disk, temp, vibration, electrical, anomaly_score):
        evidence = []

        if cpu > HIGH_CPU:
            evidence.append("High CPU usage")

        if mem > HIGH_MEM:
            evidence.append("High memory usage")

        if disk > HIGH_DISK:
            evidence.append("High disk usage")

        if temp > HIGH_TEMP:
            evidence.append("Elevated temperature")

        if vibration > HIGH_VIBRATION:
            evidence.append("Abnormal vibration detected")

        if electrical > HIGH_ELECTRICAL:
            evidence.append("Electrical instability")

        if anomaly_score > 1.5:
            evidence.append("High anomaly score")

        return evidence

    # -----------------------------------------------------
    # 🔥 MAIN DETECTION
    # -----------------------------------------------------
    def detect(
        self,
        flat_metrics: Dict[str, Any],
        temporal: Dict[str, Any],
        learned_graph=None,
        processes: List[Dict] = None,
        context="general",
        duration=0,
        multimodal=None
    ):

        processes = processes or []
        multimodal = multimodal or {}

        cpu = flat_metrics.get("cpu_pct", 0)
        mem = flat_metrics.get("mem_pct", 0)
        disk = flat_metrics.get("disk_pct", 0)

        anomaly_score = multimodal.get("anomaly_score", 0)
        features = multimodal.get("features", {})

        temp = features.get("thermal", 0)
        vibration = features.get("vibration_intensity", 0)
        electrical = features.get("electrical", 0)

        contributors = self.get_top_contributors(processes)

        # -------------------------------------------------
        # CAUSE DETECTION (STRICT ORDER)
        # -------------------------------------------------
        if vibration > HIGH_VIBRATION and anomaly_score > 1:
            cause_type = "mechanical_fault"

        elif temp > HIGH_TEMP and cpu > MODERATE_CPU:
            cause_type = "thermal_overload"

        elif electrical > HIGH_ELECTRICAL:
            cause_type = "electrical_instability"

        elif cpu > HIGH_CPU:
            cause_type = "cpu_overload"

        elif cpu > MODERATE_CPU:
            cause_type = "moderate_cpu_load"

        else:
            cause_type = "background_load"

        # -------------------------------------------------
        # PROCESS CONTEXT
        # -------------------------------------------------
        process_name = None
        process_cpu = 0

        if contributors:
            top = contributors[0]
            process_name = top.get("name")
            process_cpu = top.get("cpu", 0)

        # -------------------------------------------------
        # EVIDENCE
        # -------------------------------------------------
        evidence = self.build_evidence(
            cpu, mem, disk, temp, vibration, electrical, anomaly_score
        )

        # -------------------------------------------------
        # CONFIDENCE (CALIBRATED)
        # -------------------------------------------------
        confidence = calibrate_confidence(
            anomaly_score,
            len(evidence),
            data_points=temporal.get("samples", 50)
        )

        # -------------------------------------------------
        # SEVERITY
        # -------------------------------------------------
        severity = compute_severity(cpu, mem, disk, anomaly_score)

        # -------------------------------------------------
        # IMPACT
        # -------------------------------------------------
        chain = self.build_chain(cause_type, process_name)

        # -------------------------------------------------
        # PRIMARY CAUSE (SAFE STRUCTURE)
        # -------------------------------------------------
        primary = {
            "type": cause_type,
            "process": process_name,
            "cpu": process_cpu,

            "confidence": confidence,
            "severity": severity,

            # 🔥 NO FREE TEXT GUESSING
            "evidence": evidence,

            "contributors": contributors,
            "impact_chain": chain,
            "propagated_risk": propagate_risk(severity, len(chain)),
            "recommended_action": map_action(cause_type),

            "signals": {
                "thermal": temp,
                "vibration": vibration,
                "electrical": electrical,
                "anomaly": anomaly_score
            }
        }

        return {
            "primary_cause": primary,
            "root_causes": [primary],
            "system_risk": primary["propagated_risk"]
        }
