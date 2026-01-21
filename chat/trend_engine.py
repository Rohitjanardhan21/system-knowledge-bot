from statistics import mean

def compute_trend(values):
    """
    Returns: (direction, confidence)
    direction: 'up', 'down', 'stable'
    confidence: 'weak', 'moderate', 'strong'
    """

    if len(values) < 3:
        return ("stable", "weak")

    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    avg_delta = mean(deltas)

    if abs(avg_delta) < 50:
        return ("stable", "weak")

    direction = "up" if avg_delta > 0 else "down"

    magnitude = abs(avg_delta)
    if magnitude < 200:
        confidence = "weak"
    elif magnitude < 500:
        confidence = "moderate"
    else:
        confidence = "strong"

    return (direction, confidence)
