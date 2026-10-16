import inspect
import sqlite3
from pathlib import Path

from backend.core.storage import db


def main():
    print("=== PREDICTION SCHEMA INITIALIZATION DIAGNOSTIC ===")

    print("\n=== DB MODULE ===")
    print(db.__file__)

    print("\n=== DB FUNCTIONS ===")
    for name in dir(db):
        if any(x in name.lower() for x in ("init", "schema", "migrat", "create", "database")):
            obj = getattr(db, name)
            if callable(obj):
                print(name, inspect.signature(obj))

    print("\n=== SOURCE REFERENCES TO acknowledged ===")
    source = inspect.getsource(db)
    for i, line in enumerate(source.splitlines(), 1):
        if "acknowledged" in line.lower() or "predictions" in line.lower():
            print(f"{i}: {line}")

    db_path = Path("data") / "cvis.db"
    print("\n=== DATABASE ===")
    print(db_path.resolve())

    conn = sqlite3.connect(db_path)
    try:
        print("\n=== PREDICTIONS CREATE SQL ===")
        row = conn.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE type='table' AND name='predictions'
        """).fetchone()

        print(row[0] if row else "predictions table not found")

        print("\n=== INDEXES ===")
        rows = conn.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type='index' AND tbl_name='predictions'
        """).fetchall()

        for r in rows:
            print(r)

    finally:
        conn.close()

    print("\n=== RESULT ===")
    print("Schema initialization/migration source inspection complete.")


if __name__ == "__main__":
    main()
