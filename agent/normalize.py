"""
Question normalization layer for the System Knowledge Agent.

Purpose:
- Accept any natural language question
- Remove conversational noise
- Standardize terminology
- Preserve meaning
- Prepare input for intent & domain resolution

IMPORTANT INVARIANTS:
- Normalization NEVER adds information
- Normalization NEVER infers intent
- Normalization NEVER changes authority
"""

import re
from dataclasses import dataclass
from typing import List


# --------------------------------------------------
# Conversational filler phrases (safe to remove)
# --------------------------------------------------
FILLER_PHRASES = [
    "can you",
    "could you",
    "would you",
    "please",
    "hey",
    "hi",
    "hello",
    "tell me",
    "i want to know",
    "do you think",
    "is it possible",
]


# --------------------------------------------------
# Filler words (do not change meaning in this domain)
# --------------------------------------------------
FILLER_WORDS = {
    "the", "a", "an",
    "is", "are", "was", "were",
    "to", "for", "of",
    "on", "in", "at",
    "my", "me", "you", "your",
    "this", "that"
}


# --------------------------------------------------
# Synonym → canonical term mapping
# (INTENTIONALLY SMALL & CONTROLLED)
# --------------------------------------------------
SYNONYMS = {
    "cpu": ["processor", "cores", "compute"],
    "memory": ["ram"],
    "disk": ["storage", "drive"],
    "temperature": ["temp", "heat", "thermal"],
    "slow": ["lag", "sluggish"],
    "healthy": ["ok", "okay", "fine", "normal"],
    "show": ["display", "visualize", "view"],
}


# --------------------------------------------------
# Normalized output object
# --------------------------------------------------
@dataclass
class NormalizedQuestion:
    raw: str
    normalized_text: str
    tokens: List[str]


# --------------------------------------------------
# Core normalization function
# --------------------------------------------------
def normalize_question(text: str) -> NormalizedQuestion:
    """
    Normalize a user question into a controlled representation.

    Args:
        text (str): Raw user input

    Returns:
        NormalizedQuestion:
            - raw: original text
            - normalized_text: canonical string
            - tokens: canonical token list
    """

    raw = text

    # --- lowercase ---
    q = text.lower()

    # --- remove filler phrases ---
    for phrase in FILLER_PHRASES:
        q = q.replace(phrase, " ")

    # --- remove punctuation ---
    q = re.sub(r"[^\w\s]", " ", q)

    # --- collapse whitespace ---
    q = re.sub(r"\s+", " ", q).strip()

    # --- tokenize ---
    tokens = q.split()

    # --- remove filler words ---
    tokens = [t for t in tokens if t not in FILLER_WORDS]

    # --- canonicalize synonyms ---
    canonical_tokens = []
    for token in tokens:
        replaced = False
        for canonical, variants in SYNONYMS.items():
            if token == canonical or token in variants:
                canonical_tokens.append(canonical)
                replaced = True
                break
        if not replaced:
            canonical_tokens.append(token)

    normalized_text = " ".join(canonical_tokens)

    return NormalizedQuestion(
        raw=raw,
        normalized_text=normalized_text,
        tokens=canonical_tokens
    )


# --------------------------------------------------
# Manual test hook (safe to keep)
# --------------------------------------------------
if __name__ == "__main__":
    examples = [
        "Hey, is my CPU crying?",
        "Can you show me memory usage?",
        "Why is my system so slow today?",
        "Is everything OK?",
        "Please visualize the thermal state"
    ]

    for q in examples:
        nq = normalize_question(q)
        print(f"\nRAW: {nq.raw}")
        print(f"NORMALIZED: {nq.normalized_text}")
        print(f"TOKENS: {nq.tokens}")
