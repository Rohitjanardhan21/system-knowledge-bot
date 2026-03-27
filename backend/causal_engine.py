# ---------------------------------------------------------
# 🧠 PROCESS-AWARE CAUSAL ENGINE
# ---------------------------------------------------------

HIGH_CPU = 80
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
        "memory_pressure": "free_memory_cache",
        "disk_io_bottleneck": "reduce_disk_io",
        "latency_spike": "scale_resources",
        "unknown": "observe"
    }
    return mapping.get(cause_type, "observe")


def propagate_risk(base, length):
    return min(1.0, round(base + 0.1 * length, 2))


# ---------------------------------------------------------
# CORE ENGINE
# ---------------------------------------------------------
class CausalEngine:

    # -----------------------------------------------------
    # 🔍 FIND TOP PROCESS
    # -----------------------------------------------------
    def get_top_process(self, processes, metric="cpu"):

        if not processes:
            return None

        try:
            sorted_p = sorted(processes, key=lambda x: x.get(metric, 0), reverse=True)
            return sorted_p[0]
        except:
            return None

    # -----------------------------------------------------
    # 🔗 IMPACT CHAIN
    # -----------------------------------------------------
    def build_chain(self, cause, process_name=None):

        chain = []

        if process_name:
            chain.append(process_name)

        if cause == "cpu_overload":
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
    def detect(self, flat_metrics, temporal, learned_graph=None, processes=None):

        cpu = flat_metrics.get("cpu_pct", 0)
        mem = flat_metrics.get("mem_pct", 0)
        disk = flat_metrics.get("disk_pct", 0)

        processes = processes or []

        causes = []

        # -------------------------------------------------
        # 🔥 PROCESS-AWARE CPU
        # -------------------------------------------------
        if cpu > HIGH_CPU:

            top_proc = self.get_top_process(processes, "cpu")

            causes.append({
                "type": "cpu_overload",
                "confidence": 0.9,
                "reason": "CPU usage above threshold",
                "caused_by": top_proc.get("name") if top_proc else None,
                "process_cpu": top_proc.get("cpu") if top_proc else None
            })

        # -------------------------------------------------
        # 🔥 MEMORY
        # -------------------------------------------------
        if mem > HIGH_MEM:

            top_proc = self.get_top_process(processes, "memory")

            causes.append({
                "type": "memory_pressure",
                "confidence": 0.85,
                "reason": "High memory usage",
                "caused_by": top_proc.get("name") if top_proc else None,
                "process_memory": top_proc.get("memory") if top_proc else None
            })

        # -------------------------------------------------
        # 🔥 DISK
        # -------------------------------------------------
        if disk > HIGH_DISK:
            causes.append({
                "type": "disk_io_bottleneck",
                "confidence": 0.75,
                "reason": "Disk usage high"
            })

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------
        if not causes:
            causes = [{
                "type": "unknown",
                "confidence": 0.4,
                "reason": "No clear pattern"
            }]

        # -------------------------------------------------
        # 🔥 ENRICH
        # -------------------------------------------------
        severity = compute_severity(cpu, mem, disk)

        enriched = []

        for c in causes:

            process_name = c.get("caused_by")

            chain = self.build_chain(c["type"], process_name)

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
# 🔄 BACKWARD COMPATIBILITY (CRITICAL FIX)
# ---------------------------------------------------------
def detect_causal_relationship(flat_metrics, temporal):
    """
    Legacy wrapper for older modules.
    Keeps system stable after upgrading to CausalEngine.
    """
    engine = CausalEngine()
    return engine.detect(flat_metrics, temporal)
