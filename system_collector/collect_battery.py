import subprocess

def run(cmd):
    return subprocess.check_output(cmd, text=True)

def collect_battery():
    try:
        output = run(["upower", "-i", "$(upower -e | grep BAT)"])
        design = None
        current = None

        for line in output.splitlines():
            if "energy-full-design" in line:
                design = float(line.split(":")[1].strip().split()[0])
            if "energy-full:" in line:
                current = float(line.split(":")[1].strip().split()[0])

        if design and current:
            health_pct = (current / design) * 100
            return {"health_pct": round(health_pct, 1)}
    except Exception:
        pass

    return {"status": "not_applicable"}
