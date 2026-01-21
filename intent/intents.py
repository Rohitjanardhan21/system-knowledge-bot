from enum import Enum

class Intent(Enum):
    SYSTEM_HEALTH = "system_health"
    CPU_STATUS = "cpu_status"
    MEMORY_STATUS = "memory_status"
    GPU_STATUS = "gpu_status"
    THERMAL_STATUS = "thermal_status"
    BOTTLENECK = "bottleneck"
    CAPABILITY = "capability"
    SUGGESTIONS = "suggestions"
    EXPLAIN_SILENCE = "explain_silence"
    EXPLAIN_SYSTEM = "explain_system"
    UNKNOWN = "unknown"
