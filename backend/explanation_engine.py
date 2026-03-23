def generate_explanation(cpu, anomalies, root_cause):
    if anomalies and root_cause:
        return f"System under stress due to process '{root_cause['process']}' consuming high CPU."
    
    if cpu < 20:
        return "System is stable with low resource usage."

    return "System is operating normally."
