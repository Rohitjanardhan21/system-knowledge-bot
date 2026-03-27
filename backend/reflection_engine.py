class ReflectionEngine:

    def evaluate_decision(self, action, reward):
        if reward > 0:
            return "good_decision"
        elif reward < 0:
            return "bad_decision"
        return "neutral"

    def adjust_strategy(self, agent, reward):
        if reward < 0:
            agent.epsilon = min(1.0, agent.epsilon + 0.1)
        else:
            agent.epsilon *= 0.98
