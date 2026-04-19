"""
🧠 DATA SOURCE ABSTRACTION LAYER

Purpose:

* Make system OS-agnostic
* Make system domain-agnostic
* Standardize all incoming data into a unified schema

Principles:

* No assumptions about source
* No hardcoded system logic
* Pluggable architecture
* Safe + transparent data flow
  """

from abc import ABC, abstractmethod
import time
import platform
import psutil

# ---------------------------------------------------------

# 📦 STANDARD DATA FORMAT (IMPORTANT)

# ---------------------------------------------------------

def create_standard_payload(node_name: str, metrics: dict):
"""
All data sources MUST return this format
"""

```
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
```

# ---------------------------------------------------------

# 🧠 BASE CLASS (ABSTRACT)

# ---------------------------------------------------------

class DataSource(ABC):
"""
Base class for ALL data sources
"""

```
@abstractmethod
def collect(self) -> dict:
    """
    Must return standardized payload
    """
    pass
```

# ---------------------------------------------------------

# 💻 SYSTEM DATA SOURCE (DEFAULT)

# ---------------------------------------------------------

class SystemDataSource(DataSource):
"""
Collects:
- CPU
- Memory
- Disk
- Processes

```
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
    disk = psutil.disk_usage('/').percent

    processes = []

    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            processes.append({
                "pid": p.info['pid'],
                "name": p.info['name'],
                "cpu": p.info['cpu_percent'],
                "memory": round(p.info['memory_percent'], 2),
                "category": self.categorize_process(p.info['name'])
            })
        except:
            continue

    metrics = {
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "processes": processes,
        "source": "system"
    }

    return create_standard_payload(self.node_name, metrics)

def categorize_process(self, name):
    if not name:
        return "system"

    name = name.lower()

    if "chrome" in name or "firefox" in name:
        return "browser"
    if "python" in name:
        return "runtime"
    if "docker" in name:
        return "container"
    return "system"
```

# ---------------------------------------------------------

# ☁️ MOCK CLOUD DATA SOURCE (EXAMPLE)

# ---------------------------------------------------------

class CloudDataSource(DataSource):
"""
Example:
Replace with AWS / Azure / GCP APIs
"""

```
def __init__(self, node_name="cloud-node"):
    self.node_name = node_name

def collect(self):

    # Simulated cloud metrics
    metrics = {
        "cpu": 65,
        "memory": 70,
        "disk": 50,
        "processes": [],
        "source": "cloud"
    }

    return create_standard_payload(self.node_name, metrics)
```

# ---------------------------------------------------------

# 🌐 GENERIC SENSOR / IOT SOURCE

# ---------------------------------------------------------

class SensorDataSource(DataSource):
"""
Example:
IoT / hardware / external sensors
"""

```
def __init__(self, node_name="sensor-node"):
    self.node_name = node_name

def collect(self):

    metrics = {
        "cpu": 10,  # or repurpose as load
        "memory": 20,
        "disk": 5,
        "processes": [],
        "source": "sensor"
    }

    return create_standard_payload(self.node_name, metrics)
```

# ---------------------------------------------------------

# 🧠 DATA SOURCE FACTORY (IMPORTANT)

# ---------------------------------------------------------

class DataSourceFactory:
"""
Dynamically choose data source
"""

```
@staticmethod
def get_source(source_type="system") -> DataSource:

    if source_type == "system":
        return SystemDataSource()

    if source_type == "cloud":
        return CloudDataSource()

    if source_type == "sensor":
        return SensorDataSource()

    raise ValueError(f"Unknown data source: {source_type}")
```

# ---------------------------------------------------------

# 🔄 SAFE COLLECT WRAPPER

# ---------------------------------------------------------

def safe_collect(source: DataSource):
"""
Ensures:
- No crash
- Always returns valid structure
"""

```
try:
    data = source.collect()

    if not data or "metrics" not in data:
        raise ValueError("Invalid data format")

    return data

except Exception as e:
    return {
        "node": "unknown",
        "timestamp": time.time(),
        "metrics": {
            "cpu": 0,
            "memory": 0,
            "disk": 0,
            "processes": []
        },
        "meta": {
            "error": str(e),
            "source": "fallback"
        }
    }
```
