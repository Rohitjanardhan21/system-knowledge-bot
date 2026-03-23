def generate_recommendation(anomalies, root_cause):
    if anomalies and root_cause:
        return f"Consider stopping process '{root_cause['process']}' to reduce load."
    
    return "No action needed."
