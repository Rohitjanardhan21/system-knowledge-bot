SEVERITY_ORDER = {
    "warning": 3,
    "attention": 2,
    "info": 1
}

def prioritize(issues):
    """
    issues = list of dicts:
    {
      'component': 'memory',
      'severity': 'warning',
      'reason': '...'
    }
    """
    return sorted(
        issues,
        key=lambda x: SEVERITY_ORDER[x["severity"]],
        reverse=True
    )
