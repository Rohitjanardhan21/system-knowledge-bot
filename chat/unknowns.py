def report_unknowns(facts):
    unknowns = []

    if facts["disk_health"]["status"] == "unknown":
        unknowns.append("Disk SMART health is unavailable.")

    if facts["battery"]["status"] == "not_applicable":
        unknowns.append("Battery health is not applicable on this system.")

    return unknowns
