def build_evidence_stack(facts, baseline, posture, bottleneck, suggestions):
    stack = []

    # Layer 1 — Observation
    stack.append({
        "layer": "Observation",
        "content": [
            f"CPU usage: {facts.get('cpu', {}).get('usage_percent', 'unknown')}%",
            f"Memory usage: {facts.get('memory', {}).get('used_mb', 'unknown')} MB",
            f"Temperature: {facts.get('temperature', 'unknown')}"
        ]
    })

    # Layer 2 — Baseline
    stack.append({
        "layer": "Baseline comparison",
        "content": [
            "Values compared against system-specific historical baseline",
            "No generic thresholds applied"
        ]
    })

    # Layer 3 — Deviation
    stack.append({
        "layer": "Deviation assessment",
        "content": [
            f"System posture resolved as: {posture}",
            "Deviation significance evaluated conservatively"
        ]
    })

    # Layer 4 — Impact
    stack.append({
        "layer": "Impact interpretation",
        "content": [
            f"Primary bottleneck: {bottleneck.upper() if bottleneck else 'None identified'}",
            "Impact assessed relative to current workload"
        ]
    })

    # Layer 5 — Decision
    stack.append({
        "layer": "Decision",
        "content": [
            "Output surfaced only if confidence threshold met",
            "Silence chosen where appropriate"
        ]
    })

    # Layer 6 — Suggestions
    if suggestions:
        stack.append({
            "layer": "Considerations",
            "content": [s.message for s in suggestions]
        })

    return stack
