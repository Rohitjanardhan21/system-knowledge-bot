from dataclasses import dataclass
from typing import Literal

Tone = Literal["neutral", "cautious"]

@dataclass
class Suggestion:
    message: str
    confidence: float
    tone: Tone
