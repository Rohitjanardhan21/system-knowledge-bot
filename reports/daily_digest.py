from pathlib import Path
import json
from datetime import datetime, date
from typing import Optional

# ---- Paths ----
STATE_HISTORY = Path("system_state/history")
REPORT_DIR = Path("system_reports/daily")

REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ---- Core Logic ----
def generate_daily_digest(target_date: Optional[date] = None) -> Optional[Path]:
    """
    Generate a daily system narrative based on recorded system state.

    Returns:
        Path to report file if generated
        None if no data exists for the day
    """
    if target_date is None:
        target_date = date.today()

    records = []

    # Collect all state snapshots for the given date
    for file in sorted(STATE_HISTORY.glob(f"{target_date.isoformat()}*.json")):
        try:
            with open(file) as f:
                records.append(json.load(f))
        except Exception:
            # Corrupt state files are ignored, not fatal
            continue

    # If no data exists, do nothing (silence is correct)
    if not records:
        return None

    posture_counts = {}
    notable_events = []

    for record in records:
        posture = record.get("posture", {}).get("posture", "unknown")
        posture_counts[posture] = posture_counts.get(posture, 0) + 1

        for judgment in record.get("judgments", []):
            if judgment.get("urgency") in ("act-now", "act-soon"):
                notable_events.append(judgment)

    dominant_posture = max(posture_counts, key=posture_counts.get)

    report_path = REPORT_DIR / f"{target_date.isoformat()}.md"

    with open(report_path, "w") as f:
        f.write("# System Knowledge Bot — Daily Summary\n\n")
        f.write(f"Date: {target_date.isoformat()}\n\n")

        # ---- Posture ----
        f.write("## Overall System Posture\n")
        f.write(f"**{dominant_posture.replace('-', ' ').title()}**\n\n")

        # ---- Observations ----
        f.write("## Notable Observations\n")
        if not notable_events:
            f.write("- No conditions required attention.\n")
        else:
            for j in notable_events:
                f.write(
                    f"- {j.get('state', 'unknown').title()} condition "
                    f"(confidence {j.get('confidence', 0):.2f})\n"
                )

        # ---- Interpretation ----
        f.write("\n## Interpretation\n")
        if dominant_posture in ("idle-capable", "work-stable"):
            f.write(
                "The system operated within expected parameters. "
                "No action was required.\n"
            )
        elif dominant_posture == "performance-sensitive":
            f.write(
                "The system experienced elevated load during the day, "
                "but remained stable under expected usage.\n"
            )
        else:
            f.write(
                "The system encountered sustained pressure. "
                "Review may be warranted depending on workload.\n"
            )

    return report_path


# ---- Entry Point ----
if __name__ == "__main__":
    report = generate_daily_digest()

    if report is None:
        print("No system state records found for today. No report generated.")
    else:
        print(f"Daily system digest generated: {report}")
