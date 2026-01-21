FORBIDDEN_WORDS = [
    "should",
    "must",
    "fix",
    "kill",
    "restart",
    "increase",
    "decrease",
    "optimize",
    "upgrade"
]

def validate_suggestion(text: str):
    lowered = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in lowered:
            raise ValueError(f"Unsafe suggestion wording detected: '{word}'")
