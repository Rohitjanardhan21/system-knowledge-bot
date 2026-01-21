from chat.baseline_engine import baseline_deviation

def memory_baseline(history):
    values = [h["memory"]["available_mb"] for h in history[:-1]]
    current = history[-1]["memory"]["available_mb"]
    return baseline_deviation(values, current)

def disk_baseline(history):
    values = []
    for h in history[:-1]:
        for fs in h["storage"]["filesystems"]:
            if fs["mount_point"] == "/":
                values.append(fs["used_gb"])

    current = None
    for fs in history[-1]["storage"]["filesystems"]:
        if fs["mount_point"] == "/":
            current = fs["used_gb"]

    return baseline_deviation(values, current)
