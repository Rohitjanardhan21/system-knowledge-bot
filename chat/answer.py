from explain.cpu import explain_cpu
from explain.memory import explain_memory
from explain.thermal import explain_thermal
from intent.intents import Intent
from bottleneck.detector import detect_bottleneck
from bottleneck.explainer import explain_bottleneck
from intent.intents import Intent
from suggest.engine import generate_suggestions
from suggest.phrasing import validate_suggestion

def maybe_add_suggestions(response: str, posture: str, bottleneck: str | None):
    suggestions = generate_suggestions(posture, bottleneck)

    if not suggestions:
        return response

    lines = [response, "", "Considerations:"]
    for s in suggestions:
        validate_suggestion(s.message)
        lines.append(f"- {s.message} (confidence {s.confidence:.2f})")

    return "\n".join(lines)

def answer_intent(intent, facts, posture):
    if intent == Intent.BOTTLENECK:
        result = detect_bottleneck(facts, posture)
        return explain_bottleneck(result)


def answer_intent(intent, facts, posture):
    if intent == Intent.CPU_STATUS:
        return explain_cpu(facts, posture)

    if intent == Intent.MEMORY_STATUS:
        return explain_memory(facts, posture)

    if intent == Intent.THERMAL_STATUS:
        return explain_thermal(facts, posture)

    return "I understand the question, but I don’t have a safe explanation for it yet."
