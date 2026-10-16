from abc import ABC, abstractmethod


class SystemCollector(ABC):
    """OS-agnostic system telemetry interface."""

    @abstractmethod
    def cpu(self) -> dict:
        pass

    @abstractmethod
    def memory(self) -> dict:
        pass

    @abstractmethod
    def storage(self) -> dict:
        pass

    @abstractmethod
    def temperature(self) -> dict | None:
        pass

    @abstractmethod
    def processes(self) -> list:
        pass

    @abstractmethod
    def disk_io(self) -> dict:
        pass

    @abstractmethod
    def network(self) -> dict:
        pass

    @abstractmethod
    def battery(self) -> dict | None:
        pass

    @abstractmethod
    def uptime(self) -> dict:
        pass

    @abstractmethod
    def events(self) -> list:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass

    def collect_all(self) -> dict:
        metadata = self.metadata()

        return {
            "schema_version": "1.0",
            "device": {
                "os": metadata.get("os"),
                "platform": metadata.get("platform"),
                "hostname": metadata.get("hostname")
            },
            "timestamp": metadata.get("collected_at"),
            "freshness": {
                "ttl_seconds": metadata.get("ttl_seconds", 120),
                "valid": True
            },
            "cpu": self.cpu(),
            "memory": self.memory(),
            "storage": self.storage(),
            "temperature": self.temperature(),
            "processes": self.processes(),
            "disk_io": self.disk_io(),
            "network": self.network(),
            "battery": self.battery(),
            "uptime": self.uptime(),
            "events": self.events(),
            "metadata": metadata
        }
