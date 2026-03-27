# backend/explanation_engine.py

def generate_explanation(state, action, reward, policy_value):
    quality = "effective" if reward > 0 else "ineffective"

    return {
        "summary": f"System in state {state}, selected {action}",
        "reasoning": f"Policy value {policy_value:.2f}, past outcome {quality}",
        "confidence": min(max(policy_value, 0), 1)
    }
