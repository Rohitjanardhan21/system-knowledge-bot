from collections import defaultdict

action_stats = defaultdict(list)

def record(action, reward):
    action_stats[action].append(reward)

def get_best_action():
    avg = {
        a: sum(v)/len(v)
        for a, v in action_stats.items()
        if v
    }
    return max(avg, key=avg.get) if avg else None
