import inspect

from backend.core.storage import db


def main():
    print("=== DATABASE INITIALIZATION SOURCE ===")

    source = inspect.getsource(db)

    lines = source.splitlines()

    for start, end in [
        (90, 165),
        (520, 650),
    ]:
        print(f"\n=== LINES {start}-{end} ===")
        for i in range(start, min(end, len(lines)) + 1):
            print(f"{i}: {lines[i - 1]}")

    print("\n=== RESULT ===")
    print("Initialization and prediction persistence source captured.")


if __name__ == "__main__":
    main()
