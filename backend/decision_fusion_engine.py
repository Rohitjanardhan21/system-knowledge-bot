# backend/decision_fusion_engine.py

def fuse_decision(policy_action, rule_action, prediction, risk):
    """
    Combine multiple intelligence sources into final action
    """

    # 🚨 HARD SAFETY OVERRIDE
    if risk == "CRITICAL":
        return rule_action

    # 🔮 Predictive override
    if prediction and prediction.get("cpu", 0) > 90:
        return "preemptive_cpu_control"

    # 🧠 Default to learned behavior
    return policy_action
