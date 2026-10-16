from system_collectors.base import SystemCollector
import psutil
import time
import platform
import subprocess
import json


class WindowsCollector(SystemCollector):

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

        return {"volumes": volumes}

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
        Collect recent Windows system/application events and normalize
        them into the OS-agnostic event schema.
        """

        query = """
<QueryList>
  <Query Id="0">
    <Select Path="System">
      *[System[
        (EventID=41) or
        (EventID=1001) or
        (EventID=6008) or
        (EventID=4101) or
        (EventID=17) or
        (EventID=18) or
        (EventID=19)
      ]]
    </Select>
  </Query>
  <Query Id="1">
    <Select Path="Application">
      *[System[
        (EventID=1000) or
        (EventID=1001)
      ]]
    </Select>
  </Query>
</QueryList>
""".strip()

        try:
            result = subprocess.run(
                [
                    "wevtutil",
                    "qe",
                    "System",
                    "/q:" + query.replace("\n", ""),
                    "/f:RenderedXml",
                    "/c:50",
                    "/rd:true"
                ],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode != 0:
                return []

            import xml.etree.ElementTree as ET

            events = []

            for block in result.stdout.split("</Event>"):
                if "<Event" not in block:
                    continue

                block += "</Event>"

                try:
                    root = ET.fromstring(block)

                    system = root.find(
                        "{http://schemas.microsoft.com/win/2004/08/events/event}System"
                    )

                    if system is None:
                        continue

                    def find_text(tag):
                        node = system.find(
                            "{http://schemas.microsoft.com/win/2004/08/events/event}"
                            + tag
                        )
                        return node.text if node is not None else None

                    event_id = find_text("EventID")
                    provider = system.find(
                        "{http://schemas.microsoft.com/win/2004/08/events/event}Provider"
                    )

                    provider_name = (
                        provider.attrib.get("Name")
                        if provider is not None
                        else None
                    )

                    time_node = system.find(
                        "{http://schemas.microsoft.com/win/2004/08/events/event}"
                        "TimeCreated"
                    )

                    timestamp = (
                        time_node.attrib.get("SystemTime")
                        if time_node is not None
                        else None
                    )

                    event_map = {
                        "41": ("unexpected_shutdown", "critical", "power"),
                        "1001": ("system_or_application_error", "error", "system"),
                        "6008": ("unexpected_shutdown", "critical", "power"),
                        "4101": ("display_driver_recovery", "warning", "display"),
                        "17": ("whea_hardware_error", "error", "hardware"),
                        "18": ("whea_hardware_error", "critical", "hardware"),
                        "19": ("whea_hardware_corrected", "warning", "hardware"),
                        "1000": ("application_crash", "error", "application")
                    }

                    event_type, severity, subsystem = event_map.get(
                        str(event_id),
                        ("system_event", "info", "system")
                    )

                    events.append({
                        "timestamp": timestamp,
                        "source": "windows_event_log",
                        "event_id": int(event_id) if event_id and event_id.isdigit() else event_id,
                        "provider": provider_name,
                        "event_type": event_type,
                        "severity": severity,
                        "subsystem": subsystem,
                        "message": None,
                        "raw_available": True
                    })

                except Exception:
                    continue

            return events[:50]

        except Exception:
            return []

    def metadata(self):
        return {
            "os": "windows",
            "platform": platform.platform(),
            "hostname": platform.node(),
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "ttl_seconds": 120
        }
