from system_collectors.base import SystemCollector
import psutil
import time

class LinuxCollector(SystemCollector):

    def cpu(self):
        return {
            "usage_percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count()
        }

    def memory(self):
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "used": mem.used,
            "percent": mem.percent
        }

    def storage(self):
        disk = psutil.disk_usage("/")
        return {
            "total": disk.total,
            "used": disk.used,
            "percent": disk.percent
        }

    def temperature(self):
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for entries in temps.values():
            if entries:
                return {"celsius": entries[0].current}
        return None

    def metadata(self):
        return {
            "os": "linux",
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ttl_seconds": 120
        }
