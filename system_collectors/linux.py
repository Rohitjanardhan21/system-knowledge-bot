from system_collectors.base import SystemCollector
import psutil
import time
import platform


class LinuxCollector(SystemCollector):

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
            "available": mem.available,
            "percent": mem.percent
        }

    def storage(self):
        volumes = []

        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)

                volumes.append({
                    "mount": partition.mountpoint,
                    "filesystem": partition.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent
                })
            except (PermissionError, OSError):
                continue

        return {
            "volumes": volumes
        }

    def temperature(self):
        try:
            temps = psutil.sensors_temperatures()

            if not temps:
                return None

            readings = []

            for sensor, entries in temps.items():
                for entry in entries:
                    readings.append({
                        "sensor": sensor,
                        "label": entry.label,
                        "celsius": entry.current
                    })

            return readings if readings else None

        except Exception:
            return None

    def processes(self):
        processes = []

        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                info = proc.info

                processes.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": info["cpu_percent"],
                    "memory_percent": info["memory_percent"],
                    "status": info["status"]
                })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(
            key=lambda p: (
                p["cpu_percent"] or 0,
                p["memory_percent"] or 0
            ),
            reverse=True
        )

        return processes[:50]

    def disk_io(self):
        counters = psutil.disk_io_counters()

        if counters is None:
            return {}

        return {
            "read_bytes": counters.read_bytes,
            "write_bytes": counters.write_bytes,
            "read_count": counters.read_count,
            "write_count": counters.write_count,
            "read_time_ms": counters.read_time,
            "write_time_ms": counters.write_time
        }

    def network(self):
        counters = psutil.net_io_counters()

        if counters is None:
            return {}

        return {
            "bytes_sent": counters.bytes_sent,
            "bytes_received": counters.bytes_recv,
            "packets_sent": counters.packets_sent,
            "packets_received": counters.packets_recv,
            "errors_in": counters.errin,
            "errors_out": counters.errout,
            "drops_in": counters.dropin,
            "drops_out": counters.dropout
        }

    def battery(self):
        battery = psutil.sensors_battery()

        if battery is None:
            return None

        return {
            "percent": battery.percent,
            "plugged": battery.power_plugged,
            "seconds_left": battery.secsleft
        }

    def uptime(self):
        boot_time = psutil.boot_time()
        now = time.time()

        return {
            "boot_time": time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.localtime(boot_time)
            ),
            "uptime_seconds": int(now - boot_time)
        }

    def events(self):
        """
        Native Linux event integration will be added separately.
        """
        return []

    def metadata(self):
        return {
            "os": "linux",
            "platform": platform.platform(),
            "hostname": platform.node(),
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ttl_seconds": 120
        }
