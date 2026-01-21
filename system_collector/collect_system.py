import subprocess
import json
import os
import hashlib
from datetime import datetime
from posture.write_history import write_posture_history

FACTS_DIR = "system_facts"
HISTORY_DIR = os.path.join(FACTS_DIR, "history")

os.makedirs(HISTORY_DIR, exist_ok=True)

def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()

def collect_identity():
    lscpu = run(["lscpu"])
    model, cores = "", ""

    for line in lscpu.splitlines():
        if "Model name:" in line:
            model = line.split(":", 1)[1].strip()
        if line.startswith("CPU(s):"):
            cores = line.split(":", 1)[1].strip()

    disks = run(["lsblk", "-ndo", "MODEL,SERIAL"]).replace("\n", "|")
    raw = model + cores + disks
    machine_id = hashlib.sha256(raw.encode()).hexdigest()

    return {
        "machine_id": machine_id,
        "cpu_fingerprint": f"{model}-{cores}",
        "disk_fingerprint": disks
    }

def collect_cpu():
    out = run(["lscpu"])
    cpu = {}
    for line in out.splitlines():
        if "Model name:" in line:
            cpu["model"] = line.split(":", 1)[1].strip()
        if "Architecture:" in line:
            cpu["architecture"] = line.split(":", 1)[1].strip()
        if line.startswith("CPU(s):"):
            cpu["logical_cores"] = int(line.split(":", 1)[1].strip())
    return cpu

def collect_memory():
    out = run(["free", "-m"])
    p = out.splitlines()[1].split()
    return {
        "total_mb": int(p[1]),
        "used_mb": int(p[2]),
        "available_mb": int(p[6])
    }

def collect_storage():
    blk = json.loads(run(["lsblk", "-b", "-o", "NAME,TYPE,SIZE,MODEL", "-J"]))
    devices = []
    for d in blk["blockdevices"]:
        if d["type"] == "disk":
            devices.append({
                "name": d["name"],
                "size_gb": int(d["size"]) // (1024**3),
                "model": d.get("model", "unknown")
            })

    df = run(["df", "-B1", "--output=source,size,used,avail,target"])
    filesystems = []
    for line in df.splitlines()[1:]:
        p = line.split()
        if p[0].startswith("/"):
            filesystems.append({
                "source": p[0],
                "size_gb": int(p[1]) // (1024**3),
                "used_gb": int(p[2]) // (1024**3),
                "available_gb": int(p[3]) // (1024**3),
                "mount_point": p[4]
            })

    return {"devices": devices, "filesystems": filesystems}

def collect_disk_health():
    return {
        "status": "unknown",
        "reason": "SMART data not available (VM or permissions)"
    }

def collect_battery():
    return {
        "status": "not_applicable",
        "reason": "No battery detected (virtual machine)"
    }

def main():
    ts = datetime.utcnow()
    facts = {
        "metadata": {
            "collected_at": ts.isoformat(),
            "ttl_seconds": 300,
            "collector": "collect_system.py"
        },
        "identity": collect_identity(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "storage": collect_storage(),
        "disk_health": collect_disk_health(),
        "battery": collect_battery()
    }

    with open(os.path.join(FACTS_DIR, "current.json"), "w") as f:
        json.dump(facts, f, indent=2)

    with open(os.path.join(HISTORY_DIR, ts.strftime("%Y-%m-%dT%H-%M-%S.json")), "w") as f:
        json.dump(facts, f, indent=2)

    print("System facts collected.")
    
    write_posture_history(facts)

if __name__ == "__main__":
    main()
