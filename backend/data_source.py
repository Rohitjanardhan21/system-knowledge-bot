"""
🧠 DATA SOURCE ABSTRACTION LAYER

Purpose:
- Make system OS-agnostic
- Make system domain-agnostic
- Standardize all incoming data into a unified schema

Principles:
- No assumptions about source
- No hardcoded system logic
- Pluggable architecture
- Safe + transparent data flow
"""

from abc import ABC, abstractmethod
import time
import platform
import psutil


# ---------------------------------------------------------
# 📦 STANDARD DATA FORMAT
# ---------------------------------------------------------

def create_standard_payload(node_name: str, metrics: dict):
    """
    All data sources MUST return this format.
    """
    return {
        "node": node_name,
        "timestamp": time.time(),
        "metrics": {
            "cpu": metrics.get("cpu", 0),
            "memory": metrics.get("memory", 0),
            "disk": metrics.get("disk", 0),
            "processes": metrics.get("processes", [])
        },
        "meta": {
            "os": platform.system(),
            "source": metrics.get("source", "unknown")
        }
    }


# ---------------------------------------------------------
# 🧠 BASE CLASS
# ---------------------------------------------------------

class DataSource(ABC):
    """
    Base class for ALL data sources.
    """

    @abstractmethod
    def collect(self) -> dict:
        """
        Must return standardized payload.
        """
        pass


# ---------------------------------------------------------
# 💻 SYSTEM DATA SOURCE
# ---------------------------------------------------------

class SystemDataSource(DataSource):
    """
    Collects:
    - CPU
    - Memory
    - Disk
    - Processes

    Works on:
    - Linux
    - Windows
    - Mac
    """

    def __init__(self, node_name="local-system"):
        self.node_name = node_name

    def collect(self):

        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent

        processes = []

        # Prime process CPU counters first. psutil.cpu_percent() for
        # individual processes needs two observations to calculate
        # interval CPU utilization.
        proc_list = []
        for proc in psutil.process_iter(
            ["pid", "name", "memory_percent", "status"]
        ):
            try:
                if proc.info.get("status") in ("zombie", "dead"):
                    continue
                proc.cpu_percent(interval=None)
                proc_list.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Give psutil a measurement window.
        time.sleep(0.5)

        for proc in proc_list:
            try:
                info = proc.info
                name = info.get("name") or "unknown"
                cpu = proc.cpu_percent(interval=None)

                processes.append({
                    "pid": info["pid"],
                    "name": name,
                    "cpu": round(cpu, 2),
                    "memory": round(info.get("memory_percent") or 0.0, 2),
                    "category": self.categorize_process(name),
                    "application": self.identify_application(name)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        metrics = {
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "processes": processes,
            "source": "system"
        }

        return create_standard_payload(self.node_name, metrics)

    def identify_application(self, name):
        """
        Map a process executable name to a human-readable application.
        This is intentionally separate from the broader process category.
        """
        if not name:
            return "Unknown"

        name = name.lower()

        application_map = {
            "chrome": "Chrome",
            "chromium": "Chromium",
            "firefox": "Firefox",
            "msedge": "Microsoft Edge",
            "edge": "Microsoft Edge",
            "brave": "Brave",
            "opera": "Opera",
            "code": "VS Code",
            "code-insiders": "VS Code",
            "python": "Python",
            "python3": "Python",
            "java": "Java",
            "node": "Node.js",
            "nodejs": "Node.js",
            "docker": "Docker",
            "dockerd": "Docker",
            "redis-server": "Redis",
            "postgres": "PostgreSQL",
            "mysqld": "MySQL",
            "nginx": "Nginx",
        }

        for executable, application in application_map.items():
            if name == executable or name.startswith(executable + "."):
                return application

        # Common Linux executable naming patterns.
        if "firefox" in name:
            return "Firefox"

        if "chrome" in name:
            return "Chrome"

        if "chromium" in name:
            return "Chromium"

        if "python" in name:
            return "Python"

        if "java" in name:
            return "Java"

        if "node" in name:
            return "Node.js"

        if "docker" in name:
            return "Docker"

        return name

    def categorize_process(self, name):
        if not name:
            return "system"

        name = name.lower()

        if any(x in name for x in (
            "chrome",
            "chromium",
            "firefox",
            "msedge",
            "edge",
            "brave",
            "opera"
        )):
            return "browser"

        if any(x in name for x in ("python", "java", "node")):
            return "runtime"

        if "docker" in name:
            return "container"

        return "system"


# ---------------------------------------------------------
# ☁️ MOCK CLOUD DATA SOURCE
# ---------------------------------------------------------

class CloudDataSource(DataSource):
    """
    Example:
    Replace with AWS / Azure / GCP APIs.
    """

    def __init__(self, node_name="cloud-node"):
        self.node_name = node_name

    def collect(self):

        metrics = {
            "cpu": 65,
            "memory": 70,
            "disk": 50,
            "processes": [],
            "source": "cloud"
        }

        return create_standard_payload(self.node_name, metrics)


# ---------------------------------------------------------
# 🌐 GENERIC SENSOR / IOT SOURCE
# ---------------------------------------------------------

class SensorDataSource(DataSource):
    """
    Example:
    IoT / hardware / external sensors.
    """

    def __init__(self, node_name="sensor-node"):
        self.node_name = node_name

    def collect(self):

        metrics = {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "processes": [],
            "source": "sensor"
        }

        return create_standard_payload(self.node_name, metrics)


# ---------------------------------------------------------
# 🧠 DEFAULT SOURCE
# ---------------------------------------------------------

default_source = SystemDataSource()


def get_data_source():
    """
    Return the default system data source.
    """
    return default_source
