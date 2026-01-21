from chat.trend_engine import compute_trend

def memory_trend(history):
    values = [h["memory"]["available_mb"] for h in history]
    return compute_trend(values)

def disk_trend(history):
    values = []
    for h in history:
        for fs in h["storage"]["filesystems"]:
            if fs["mount_point"] == "/":
                values.append(fs["used_gb"])
    return compute_trend(values)
