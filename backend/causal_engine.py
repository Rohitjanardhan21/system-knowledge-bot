# ---------------------------------------------------------
# 🧠 PROCESS + CONTEXT + MULTI-CAUSE ENGINE (UPGRADED)
# ---------------------------------------------------------

HIGH_CPU = 80
MODERATE_CPU = 40
HIGH_MEM = 75
HIGH_DISK = 85


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def compute_severity(cpu, mem, disk):
    return round((cpu * 0.5 + mem * 0.3 + disk * 0.2) / 100, 2)


def map_action(cause_type):
    mapping = {
        "cpu_overload": "kill_high_cpu_process",
        "moderate_cpu_load": "optimize_processes",
        "memory_pressure": "free_memory_cache",
        "disk_io_bottleneck": "reduce_disk_io",
        "background_load": "observe"
    }
    return mapping.get(cause_type, "observe")


def propagate_risk(base, length):
    return min(1.0, round(base + 0.1 * length, 2))


# ---------------------------------------------------------
# 🔥 PROCESS INTELLIGENCE
# ---------------------------------------------------------
def classify_process(name):
    name = (name or "").lower()

    if "chrome" in name:
        return "browser activity"
    if "code" in name or "python" in name:
        return "development workload"
    if "game" in name or "steam" in name:
        return "gaming workload"
    if "docker" in name:
        return "container workload"

    return "system activity"


# ---------------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------------
class CausalEngine:

    # -----------------------------------------------------
    # 🔍 TOP CONTRIBUTORS
    # -----------------------------------------------------
    def get_top_contributors(self, processes, metric="cpu", top_n=3):

        if not processes:
            return []

        try:
            sorted_p = sorted(
                processes,
                key=lambda x: x.get(metric, 0),
                reverse=True
            )
            return sorted_p[:top_n]
        except Exception:
            return []

    # -----------------------------------------------------
    # 🔗 IMPACT CHAIN
    # -----------------------------------------------------
    def build_chain(self, cause, process_names=None):

        chain = []

        if process_names:
            chain.extend(process_names)

        if cause in ["cpu_overload", "moderate_cpu_load"]:
            chain += ["cpu", "latency"]

        elif cause == "memory_pressure":
            chain += ["memory", "cpu", "latency"]

        elif cause == "disk_io_bottleneck":
            chain += ["disk", "cpu"]

        else:
            chain += ["system"]

        return chain

    # -----------------------------------------------------
    # 🧠 DETECT
    # -----------------------------------------------------
    def detect(
        self,
        flat_metrics,
        temporal,
        learned_graph=None,
        processes=None,
        context="general",
        duration=0
    ):

        cpu = flat_metrics.get("cpu_pct", 0)
        mem = flat_metrics.get("mem_pct", 0)
        disk = flat_metrics.get("disk_pct", 0)

        processes = processes or []
        causes = []

        # -------------------------------------------------
        # 🔥 CONTEXT AWARENESS
        # -------------------------------------------------
        if context == "gaming":
            return {
                "primary_cause": {
                    "type": "expected_high_usage",
                    "confidence": 0.9,
                    "reason": "Gaming workload detected",
                    "contributors": [],
                    "severity": compute_severity(cpu, mem, disk),
                    "recommended_action": "do_nothing"
                },
                "root_causes": [],
                "system_risk": 0.3
            }

        if context == "critical":
            return {
                "primary_cause": {
                    "type": "protected_workload",
                    "confidence": 0.95,
                    "reason": "Critical process running",
                    "contributors": [],
                    "severity": compute_severity(cpu, mem, disk),
                    "recommended_action": "observe"
                },
                "root_causes": [],
                "system_risk": 0.4
            }

        # -------------------------------------------------
        # 🔥 CPU (HIGH)
        # -------------------------------------------------
        if cpu > HIGH_CPU:

            top = self.get_top_contributors(processes, "cpu")

            contributors = []
            for p in top:
                name = p.get("name")
                cpu_val = p.get("cpu", 0)

                contributors.append({
                    "name": name,
                    "cpu": cpu_val,
                    "impact": round(cpu_val / max(cpu, 1), 2),
                    "behavior": classify_process(name)
                })

            if contributors:
                top_proc = contributors[0]
                reason = f"{top_proc['name']} using {top_proc['cpu']}% CPU ({top_proc['behavior']})"
            else:
                reason = "CPU usage above threshold"

            causes.append({
                "type": "cpu_overload",
                "confidence": 0.9,
                "reason": reason,
                "contributors": contributors
            })

        # -------------------------------------------------
        # 🔥 CPU (MODERATE) ⭐ FIX
        # -------------------------------------------------
        elif cpu > MODERATE_CPU:

            top = self.get_top_contributors(processes, "cpu")

            contributors = []
            for p in top:
                name = p.get("name")

                contributors.append({
                    "name": name,
                    "cpu": p.get("cpu", 0),
                    "behavior": classify_process(name)
                })

            if contributors:
                reason = f"{contributors[0]['name']} contributing to CPU load"
            else:
                reason = "Moderate system load"

            causes.append({
                "type": "moderate_cpu_load",
                "confidence": 0.6,
                "reason": reason,
                "contributors": contributors
            })

        # -------------------------------------------------
        # 🔥 MEMORY
        # -------------------------------------------------
        if mem > HIGH_MEM:

            top = self.get_top_contributors(processes, "memory")

            contributors = [
                {
                    "name": p.get("name"),
                    "memory": p.get("memory", 0)
                }
                for p in top
            ]

            causes.append({
                "type": "memory_pressure",
                "confidence": 0.85,
                "reason": "High memory usage",
                "contributors": contributors
            })

        # -------------------------------------------------
        # 🔥 DISK
        # -------------------------------------------------
        if disk > HIGH_DISK:
            causes.append({
                "type": "disk_io_bottleneck",
                "confidence": 0.75,
                "reason": "Disk usage high",
                "contributors": []
            })

        # -------------------------------------------------
        # ⏳ DURATION BOOST
        # -------------------------------------------------
        if duration > 60:
            for c in causes:
                c["confidence"] = min(1.0, c["confidence"] + 0.05)
                c["reason"] += " (persistent issue)"

        # -------------------------------------------------
        # 🔥 FALLBACK (FIXED)
        # -------------------------------------------------
        if not causes:

            top = self.get_top_contributors(processes, "cpu")

            if top:
                p = top[0]
                causes = [{
                    "type": "background_load",
                    "confidence": 0.5,
                    "reason": f"{p.get('name')} contributing to system load",
                    "contributors": [{
                        "name": p.get("name"),
                        "cpu": p.get("cpu", 0),
                        "behavior": classify_process(p.get("name"))
                    }]
                }]
            else:
                causes = [{
                    "type": "background_load",
                    "confidence": 0.4,
                    "reason": "Load distributed across processes",
                    "contributors": []
                }]

        # -------------------------------------------------
        # 🔥 ENRICH
        # -------------------------------------------------
        severity = compute_severity(cpu, mem, disk)

        enriched = []

        for c in causes:

            process_names = [p["name"] for p in c.get("contributors", [])]

            chain = self.build_chain(c["type"], process_names)

            enriched.append({
                **c,
                "severity": severity,
                "impact_chain": chain,
                "propagated_risk": propagate_risk(severity, len(chain)),
                "recommended_action": map_action(c["type"])
            })

        enriched.sort(key=lambda x: x["confidence"], reverse=True)

        return {
            "primary_cause": enriched[0],
            "root_causes": enriched,
            "all_causes": enriched,
            "system_risk": max(c["propagated_risk"] for c in enriched)
        }


# ---------------------------------------------------------
# 🔄 BACKWARD COMPATIBILITY
# ---------------------------------------------------------
def detect_causal_relationship(flat_metrics, temporal):
    engine = CausalEngine()
    return engine.detect(flat_metrics, temporal)
