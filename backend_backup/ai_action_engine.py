"""
AI Action Engine
----------------

Transforms AI/system insights into SAFE, structured, human-reviewable actions.

Principles:

* Never execute directly
* Always return structured proposals
* Include risk + confidence
* Require human approval before execution
  """

import re
import uuid
from typing import Dict, Any, Optional

# ---------------------------------------------------------

# 🔧 ACTION SCHEMA

# ---------------------------------------------------------

def build_action(
action_type: str,
target: str,
reason: str,
confidence: float,
risk: str = "medium",
metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:

```
return {
    "id": str(uuid.uuid4()),
    "type": action_type,
    "target": target,
    "reason": reason,
    "confidence": round(confidence, 2),
    "risk": risk,
    "status": "proposed",  # proposed → approved → executed / rejected
    "requires_approval": True,
    "metadata": metadata or {}
}
```

# ---------------------------------------------------------

# 🧠 RULE-BASED EXTRACTION (SAFE FALLBACK)

# ---------------------------------------------------------

def extract_from_metrics(system_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
"""
Extract actions purely from structured system data (no AI hallucination).
"""

```
root = system_data.get("root_cause", {})
cpu = system_data.get("cpu", 0)
memory = system_data.get("memory", 0)
anomalies = system_data.get("anomalies", [])

if not root:
    return None

process = root.get("process", "unknown")
process_cpu = root.get("cpu", 0)

# 🔥 HIGH CPU PROCESS
if process_cpu > 70:
    return build_action(
        action_type="terminate_process",
        target=process,
        reason=f"{process} consuming {process_cpu}% CPU",
        confidence=0.85,
        risk="high"
    )

# 🔥 MEMORY PRESSURE
if memory > 85:
    return build_action(
        action_type="free_memory",
        target="system",
        reason=f"Memory usage at {memory}%",
        confidence=0.75,
        risk="medium"
    )

# 🔥 ANOMALY RESPONSE
if anomalies:
    return build_action(
        action_type="investigate_anomaly",
        target=anomalies[0]["metric"],
        reason="Statistical anomaly detected",
        confidence=0.8,
        risk="medium"
    )

return None
```

# ---------------------------------------------------------

# 🤖 LLM OUTPUT PARSER (STRICT + SAFE)

# ---------------------------------------------------------

def extract_from_llm(ai_text: str) -> Optional[Dict[str, Any]]:
"""
Parse structured intent from LLM output.

```
IMPORTANT:
- Only extracts if pattern is clear
- Otherwise returns None (no guessing)
"""

if not ai_text:
    return None

text = ai_text.lower()

# --------------------------------------------------
# TERMINATE PROCESS
# --------------------------------------------------
match = re.search(r"(kill|terminate|stop)\s+(\w+)", text)
if match:
    process = match.group(2)

    return build_action(
        action_type="terminate_process",
        target=process,
        reason="Suggested by AI analysis",
        confidence=0.7,
        risk="high"
    )

# --------------------------------------------------
# RESTART SERVICE
# --------------------------------------------------
match = re.search(r"restart\s+(\w+)", text)
if match:
    service = match.group(1)

    return build_action(
        action_type="restart_service",
        target=service,
        reason="AI suggested restart",
        confidence=0.65,
        risk="medium"
    )

# --------------------------------------------------
# SCALE RESOURCE
# --------------------------------------------------
if "scale" in text or "increase resources" in text:
    return build_action(
        action_type="scale_resources",
        target="system",
        reason="AI suggested scaling resources",
        confidence=0.6,
        risk="medium"
    )

return None
```

# ---------------------------------------------------------

# 🧠 MAIN ENGINE

# ---------------------------------------------------------

def generate_action(
system_data: Dict[str, Any],
ai_response: Optional[str] = None
) -> Optional[Dict[str, Any]]:
"""
Master decision engine.

```
Priority:
1. Deterministic system signals (trusted)
2. AI suggestions (validated)
"""

# --------------------------------------------------
# 1. SYSTEM-BASED ACTION (MOST TRUSTED)
# --------------------------------------------------
action = extract_from_metrics(system_data)
if action:
    return action

# --------------------------------------------------
# 2. AI-BASED ACTION (SECONDARY)
# --------------------------------------------------
if ai_response:
    action = extract_from_llm(ai_response)
    if action:
        return action

return None
```

# ---------------------------------------------------------

# 🔍 VALIDATION LAYER

# ---------------------------------------------------------

def validate_action(action: Dict[str, Any]) -> Dict[str, Any]:
"""
Enforces safety constraints.
"""

```
if not action:
    return {}

# Block dangerous actions
dangerous = ["shutdown_system", "format_disk"]

if action["type"] in dangerous:
    action["blocked"] = True
    action["reason_blocked"] = "Dangerous action not allowed"
    return action

# Ensure approval required
action["requires_approval"] = True

return action
```

# ---------------------------------------------------------

# 🔄 FULL PIPELINE

# ---------------------------------------------------------

def propose_action(
system_data: Dict[str, Any],
ai_response: Optional[str] = None
) -> Optional[Dict[str, Any]]:
"""
Public interface used by system_routes / ai_routes
"""

```
action = generate_action(system_data, ai_response)

if not action:
    return None

action = validate_action(action)

return action
```
