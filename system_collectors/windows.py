from system_collectors.base import SystemCollector
import psutil
import time
import platform


class WindowsCollector(SystemCollector):
    """
    Windows implementation of system facts collector.
    Uses psutil for consistency with Linux collector.
    """

    def cpu(self):
        return {
            "usage_percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count(logical=True)
        }

    def memory(self):
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "used": mem.used,
            "percent": mem.percent
        }

    def storage(self):
        disk = psutil.disk_usage("C:\\")
        return {
            "total": disk.total,
            "used": disk.used,
            "percent": disk.percent
        }

    def temperature(self):
        """
        Windows often does not expose CPU temps via psutil.
        Return None rather than guessing.
        """
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None

            for entries in temps.values():
                if entries:
                    return {"celsius": entries[0].current}
        except Exception:
            pass

        return None

    def metadata(self):
        return {
            "os": "windows",
            "platform": platform.platform(),
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ttl_seconds": 120
        }
