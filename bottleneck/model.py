from dataclasses import dataclass
from typing import Literal, List

Resource = Literal["cpu", "memory", "disk", "thermal", "unknown"]

@dataclass
class BottleneckResult:
    primary: Resource
    secondary: List[Resource]
    confidence: float
    evidence: List[str]
