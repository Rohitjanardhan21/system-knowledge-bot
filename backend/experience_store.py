import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path as FilePath
import re
import uuid

PATH = "system_facts/experiences.json"
MAX_EXPERIENCES = 500
EXPERIENCE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def store_experience(state, action, reward, before, after, verification=None):
    """Persist an experience without silently discarding existing history."""
    path = FilePath(PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    exp = {
        "experience_id": uuid.uuid4().hex,
        "state": state,
        "action": action,
        "reward": reward,
        "before": before,
        "after": after,
        "verification": verification,
        "time": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with path.open("r", encoding="utf-8") as source:
            data = json.load(source)
    except FileNotFoundError:
        data = []

    if not isinstance(data, list):
        raise ValueError(
            f"Experience history must be a JSON list: {path}"
        )

    data.append(exp)
    data = data[-MAX_EXPERIENCES:]

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temp_path = destination.name
            json.dump(data, destination, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())

        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    return exp["experience_id"]


def consume_verified_experience(experience_id, action):
    """Return one verified-success record only once for feedback learning."""
    if (
        not isinstance(experience_id, str)
        or EXPERIENCE_ID_PATTERN.fullmatch(experience_id) is None
        or not isinstance(action, str)
    ):
        return None

    path = FilePath(PATH)
    with path.open("r", encoding="utf-8") as source:
        data = json.load(source)

    if not isinstance(data, list):
        raise ValueError(f"Experience history must be a JSON list: {path}")

    record = next(
        (
            item for item in data
            if isinstance(item, dict)
            and item.get("experience_id") == experience_id
            and item.get("action") == action
        ),
        None,
    )
    if record is None:
        return None

    verification = record.get("verification")
    if (
        not isinstance(verification, dict)
        or verification.get("verified") is not True
        or verification.get("status") != "success"
    ):
        return None

    claims_dir = path.parent / f".{path.name}.feedback-claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    claim_path = claims_dir / experience_id

    try:
        with claim_path.open("x", encoding="utf-8") as claim:
            claim.write(action)
            claim.flush()
            os.fsync(claim.fileno())
    except FileExistsError:
        return None

    return verification
