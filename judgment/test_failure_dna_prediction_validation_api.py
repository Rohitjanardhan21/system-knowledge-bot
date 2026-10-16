import inspect

from backend.core.cognitive.failure_dna import FailureDNAEngine


def main():
    print("=== FAILUREDNA resolve_prediction API DIAGNOSTIC ===")

    engine = FailureDNAEngine()

    print("\n1. ACTUAL METHOD SIGNATURE:")
    signature = inspect.signature(engine.resolve_prediction)

    print("resolve_prediction:", signature)

    print("\n2. PARAMETERS:")

    for name, parameter in signature.parameters.items():
        print(
            "name =", name,
            "| kind =", parameter.kind,
            "| default =", parameter.default,
            "| annotation =", parameter.annotation,
        )

    print("\n3. ACTIVE PREDICTION API:")
    print("get_active_predictions:", inspect.signature(
        engine.get_active_predictions
    ))

    print("\n4. PREDICTION CLASS:")
    from backend.core.cognitive.failure_dna import ActivePrediction

    print("ActivePrediction:", inspect.signature(ActivePrediction))

    print("\n5. ENGINE METHODS RELATED TO VALIDATION:")

    validation_methods = [
        name for name in dir(engine)
        if any(
            keyword in name.lower()
            for keyword in (
                "resolve",
                "acknowledge",
                "prediction",
                "outcome",
            )
        )
    ]

    for name in sorted(validation_methods):
        attribute = getattr(engine, name)

        if callable(attribute):
            try:
                print(name, "->", inspect.signature(attribute))
            except (TypeError, ValueError):
                print(name, "-> callable")

    print("\nRESULT: DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
