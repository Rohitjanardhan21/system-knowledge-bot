from enum import Enum


class EvidenceStatus(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


class ResponseMode(str, Enum):
    ANSWER = "answer"
    EXPLAIN = "explain"
    VISUAL = "visual"
    REFUSE = "refuse"
