import platform
import psutil
import subprocess


def get_gpu_info():
    try:
        result = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
        ).decode()

        gpus = []
        for line in result.strip().split("\n"):
            name, mem = line.split(", ")
            gpus.append({
                "name": name,
                "memory": mem
            })

        return gpus
    except Exception:
        return []


def profile_system():
    return {
        "os": platform.system(),
        "cpu": {
            "cores": psutil.cpu_count(logical=True)
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / 1e9, 2)
        },
        "disk": {
            "total_gb": round(psutil.disk_usage('/').total / 1e9, 2)
        },
        "gpu": get_gpu_info()
    }
