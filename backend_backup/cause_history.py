from collections import defaultdict

history = defaultdict(int)

def record(cause):
    if cause:
        history[cause] += 1

def get_top_causes():
    return sorted(history.items(), key=lambda x: x[1], reverse=True)
