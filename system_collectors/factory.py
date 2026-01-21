import platform

from system_collectors.linux import LinuxCollector
from system_collectors.windows import WindowsCollector


def get_collector():
    system = platform.system().lower()

    if system == "linux":
        return LinuxCollector()

    if system == "windows":
        return WindowsCollector()

    # macOS later
    # if system == "darwin":
    #     return MacCollector()

    raise RuntimeError(f"Unsupported OS: {system}")
