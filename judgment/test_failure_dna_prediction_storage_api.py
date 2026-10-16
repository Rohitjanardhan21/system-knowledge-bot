import inspect

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA PREDICTION STORAGE / REGISTRATION DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n1. ENGINE INSTANCE ATTRIBUTES:")

    for name, value in sorted(vars(engine).items()):
        if name.startswith("_"):
            print(
                name,
                "->",
                type(value).__name__,
                "|",
                repr(value)[:500],
            )

    print("\n2. PREDICTION-RELATED ATTRIBUTES:")

    for name in sorted(vars(engine)):
        if "predict" in name.lower():
            value = getattr(engine, name)
            print(
                name,
                "->",
                type(value).__name__,
                "|",
                repr(value)[:500],
            )

    print("\n3. PREDICTION-RELATED METHODS:")

    for name in sorted(dir(engine)):
        if any(
            keyword in name.lower()
            for keyword in (
                "predict",
                "register",
                "active",
                "resolve",
                "acknowledge",
            )
        ):
            attribute = getattr(engine, name)

            if callable(attribute):
                try:
                    print(
                        name,
                        "->",
                        inspect.signature(attribute),
                    )
                except (TypeError, ValueError):
                    print(name, "-> callable")
            else:
                print(
                    name,
                    "-> ATTRIBUTE",
                    type(attribute).__name__,
                    repr(attribute)[:500],
                )

    print("\n4. CURRENT ACTIVE PREDICTIONS:")

    active = engine.get_active_predictions()

    print("type:", type(active).__name__)
    print("count:", len(active))

    for prediction in active:
        print(
            "prediction_id:",
            getattr(prediction, "prediction_id", None),
            "| pattern_id:",
            getattr(prediction, "pattern_id", None),
            "| resolved:",
            getattr(prediction, "resolved", None),
        )

    print("\n5. SOURCE LOCATION:")

    print(
        "FailureDNAEngine source:",
        inspect.getsourcefile(FailureDNAEngine),
    )

    print("\nRESULT: DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
