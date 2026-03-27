bad_actions = {}

def penalize(action):
    bad_actions[action] = bad_actions.get(action, 0) + 1

def is_blocked(action):
    return bad_actions.get(action, 0) > 5
