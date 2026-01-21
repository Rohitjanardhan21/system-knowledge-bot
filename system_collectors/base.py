from abc import ABC, abstractmethod

class SystemCollector(ABC):
    """
    OS-agnostic system facts interface.
    """

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
    def metadata(self) -> dict:
        pass

    def collect_all(self) -> dict:
        """
        Standardized output for the agent.
        """
        return {
            "cpu": self.cpu(),
            "memory": self.memory(),
            "storage": self.storage(),
            "temperature": self.temperature(),
            "metadata": self.metadata()
        }
