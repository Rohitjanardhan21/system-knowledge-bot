import sqlite3
from pathlib import Path


def main():
    print("=== PREDICTIONS SCHEMA MIGRATION REGRESSION ===")

    test_db = Path("state") / "prediction_schema_migration_test.db"
    test_db.parent.mkdir(parents=True, exist_ok=True)

    if test_db.exists():
        test_db.unlink()

    conn = sqlite3.connect(test_db)

    try:
        print("\n=== 1. CREATE LEGACY SCHEMA ===")

        conn.execute("""
            CREATE TABLE predictions (
                prediction_id       TEXT PRIMARY KEY,
                device_id           TEXT,
                failure_type        TEXT NOT NULL,
                created_at          REAL NOT NULL,
                expected_at         REAL,
                confidence          REAL,
                risk_score          REAL,
                lead_time_seconds   REAL,
                status              TEXT NOT NULL DEFAULT 'active',
                evidence            TEXT,
                model_version       TEXT
            )
        """)

        conn.execute("""
            INSERT INTO predictions (
                prediction_id,
                device_id,
                failure_type,
                created_at,
                expected_at,
                confidence,
                risk_score,
                lead_time_seconds,
                status,
                evidence,
                model_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "legacy_prediction_001",
            "test-device",
            "CRASH",
            1000.0,
            1100.0,
            0.85,
            0.80,
            100.0,
            "active",
            '{"source":"legacy"}',
            "test-v1",
        ))

        conn.commit()

        print("Legacy row inserted.")

        print("\n=== 2. VERIFY COLUMN IS MISSING ===")

        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(predictions)")
        ]

        print(columns)

        assert "acknowledged" not in columns
        print("PASS: acknowledged initially absent.")

        print("\n=== 3. APPLY PROPOSED MIGRATION ===")

        conn.execute("""
            ALTER TABLE predictions
            ADD COLUMN acknowledged INTEGER NOT NULL DEFAULT 0
        """)

        conn.commit()

        print("Migration applied.")

        print("\n=== 4. VERIFY COLUMN ===")

        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(predictions)")
        ]

        print(columns)

        assert "acknowledged" in columns
        print("PASS: acknowledged column exists.")

        print("\n=== 5. VERIFY EXISTING DATA ===")

        row = conn.execute("""
            SELECT
                prediction_id,
                device_id,
                failure_type,
                confidence,
                status,
                model_version,
                acknowledged
            FROM predictions
            WHERE prediction_id = ?
        """, ("legacy_prediction_001",)).fetchone()

        print(row)

        assert row is not None
        assert row[0] == "legacy_prediction_001"
        assert row[1] == "test-device"
        assert row[2] == "CRASH"
        assert row[3] == 0.85
        assert row[4] == "active"
        assert row[5] == "test-v1"
        assert row[6] == 0

        print("PASS: existing prediction preserved.")

        print("\n=== 6. VERIFY save_prediction SHAPE ===")

        conn.execute("""
            INSERT OR REPLACE INTO predictions (
                prediction_id,
                device_id,
                failure_type,
                created_at,
                expected_at,
                confidence,
                risk_score,
                lead_time_seconds,
                status,
                evidence,
                model_version,
                acknowledged
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "new_prediction_002",
            "test-device",
            "CRASH",
            2000.0,
            2100.0,
            0.99,
            0.95,
            60.0,
            "active",
            '{"source":"new"}',
            "test-v2",
            1,
        ))

        conn.commit()

        row = conn.execute("""
            SELECT prediction_id, acknowledged
            FROM predictions
            WHERE prediction_id = ?
        """, ("new_prediction_002",)).fetchone()

        print(row)

        assert row == ("new_prediction_002", 1)

        print("PASS: save_prediction SQL shape works after migration.")

        print("\n=== FINAL RESULT ===")
        print("PASS: proposed prediction-schema migration is structurally safe.")

    finally:
        conn.close()

        if test_db.exists():
            test_db.unlink()


if __name__ == "__main__":
    main()
