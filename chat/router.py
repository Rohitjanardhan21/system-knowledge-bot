from intent.parser import parse_intent
from intent.gate import can_answer

def route_question(question, facts):
    intent = parse_intent(question)

    if intent.name == "UNKNOWN":
        return "I’m not sure what you’re asking. I can help with system health, performance, or capacity."

    if not can_answer(intent.value, facts):
        return "I don’t have sufficient data to answer that safely."

    return intent
