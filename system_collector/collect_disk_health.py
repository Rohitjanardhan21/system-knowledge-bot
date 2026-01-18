import subprocess

def run(cmd):
    return subprocess.check_output(cmd, text=True)

def collect_disk_health():
    try:
        output = run(["smartctl", "-H", "/dev/sda"])
        if "PASSED" in output:
            return {"status": "healthy"}
        else:
            return {"status": "warning"}
    except Exception:
        return {"status": "unknown", "reason": "SMART data not accessible"}
