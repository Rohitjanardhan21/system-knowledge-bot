import inspect

from backend.core.storage import db


def main():
    print("=== DATABASE INITIALIZATION FUNCTIONS ===")

    for name in dir(db):
        obj = getattr(db, name)

        if callable(obj) and (
            name.startswith("init")
            or name.startswith("get_db")
            or name.startswith("close")
            or "database" in name.lower()
        ):
            try:
                print(f"\n=== {name} ===")
                print(inspect.signature(obj))
                print(inspect.getsource(obj))
            except (TypeError, OSError):
                pass


if __name__ == "__main__":
    main()
