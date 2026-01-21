from statistics import mean, stdev

def baseline_deviation(values, current):
    """
    Returns (status, deviation_score)
    status: 'normal', 'elevated', 'unusual'
    deviation_score: number of standard deviations
    """

    if len(values) < 5:
        return ("unknown", 0)

    avg = mean(values)
    sd = stdev(values)

    if sd == 0:
        return ("normal", 0)

    z = (current - avg) / sd

    if abs(z) < 1:
        return ("normal", z)
    elif abs(z) < 2:
        return ("elevated", z)
    else:
        return ("unusual", z)
