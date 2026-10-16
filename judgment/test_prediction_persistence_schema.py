from __future__ import annotations

import inspect
import sqlite3

from backend.core.cognitive.failure_dna import FailureDNAEngine
from backend.core.storage import db


def main():
    print("=== PREDICTION PERSISTENCE SCHEMA DIAGNOSTIC ===")

    print("\n=== DB MODULE LOCATION ===")
    print(db.__file__)

    print("\n=== save_prediction SIGNATURE ===")
    print(inspect.signature(db.save_prediction))

    print("\n=== save_prediction SOURCE ===")
    print(inspect.getsource(db.save_prediction))

    db_path = "data/cvis.db"

    print("\n=== DATABASE SCHEMA ===")

    connection = sqlite3.connect(db_path)

    try:
        cursor = connection.execute(
            "PRAGMA table_info(predictions)"
        )

        columns = cursor.fetchall()

        if not columns:
            print("predictions table does NOT exist")
        else:
            for column in columns:
                print(column)

    finally:
        connection.close()

    print("\n=== FAILURE-DNA ACTIVE PREDICTIONS ===")

    engine = FailureDNAEngine()

    predictions = getattr(
        engine,
        "_active_predictions",
        {},
    )

    print("Active prediction count:", len(predictions))

    for prediction_id, prediction in predictions.items():
        print(
            prediction_id,
            "| type=", getattr(prediction, "failure_type", None),
            "| confidence=", getattr(prediction, "confidence", None),
            "| resolved=", getattr(prediction, "resolved", None),
        )


if __name__ == "__main__":
    main()
