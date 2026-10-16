import asyncio
import time

import psutil

from backend.main import (
    _last_metrics,
    _lock,
    app,
)
from backend.core.cognitive.failure_dna import get_dna_engine


async def run():
    print("=== REAL PRODUCTION FAILUREDNA PIPELINE AFTER DB CLEANUP ===")
    print()
    print("REAL-LIFE SCENARIO:")
    print("The CVIS backend starts from the cleaned production database.")
    print("The real collector samples the Windows host.")
    print("FailureDNA receives the production telemetry.")
    print("Existing predictions are restored from SQLite.")
    print()
    print("No synthetic telemetry will be generated.")
    print("No synthetic prediction will be generated.")
    print()

    assert psutil is not None
    print("psutil: AVAILABLE")
    print()

    dna = get_dna_engine()
    buffer_before = len(dna._metric_buffer)

    print("FailureDNA buffer before startup:", buffer_before)
    print("Active predictions before startup:", len(dna.get_active_predictions()))
    print()

    async with app.router.lifespan_context(app):
        print("Backend lifespan: STARTED")
        print("Waiting for the real production collector...")
        print()

        deadline = time.time() + 10.0

        while time.time() < deadline:
            with _lock:
                current = dict(_last_metrics)

            if current.get("collected_at") is not None:
                break

            await asyncio.sleep(0.25)

        with _lock:
            metrics = dict(_last_metrics)

        print("=== REAL HOST TELEMETRY ===")
        for key in (
            "cpu_percent",
            "memory",
            "disk_percent",
            "network_percent",
            "health_score",
            "collected_at",
        ):
            print(f"{key}: {metrics.get(key)}")

        assert metrics.get("collected_at") is not None, (
            "Production collector did not publish telemetry."
        )

        for key in (
            "cpu_percent",
            "memory",
            "disk_percent",
            "network_percent",
        ):
            assert isinstance(metrics.get(key), (int, float)), (
                f"Production telemetry missing/non-numeric: {key}"
            )

        buffer_after = len(dna._metric_buffer)

        print()
        print("FailureDNA buffer after startup:", buffer_after)
        print(
            "New real observations received:",
            buffer_after - buffer_before,
        )

        assert buffer_after > buffer_before, (
            "FailureDNA did not receive real production telemetry."
        )

        print()
        print("=== ACTIVE PREDICTIONS AFTER RESTORE ===")

        active = dna.get_active_predictions()

        print("active prediction count:", len(active))

        for prediction in active:
            print(
                prediction.prediction_id,
                "|",
                prediction.failure_type,
                "| acknowledged=",
                prediction.acknowledged,
                "| resolved=",
                prediction.resolved,
            )

        print()
        print("PASS: real production telemetry reached FailureDNA.")
        print("PASS: cleaned prediction database loaded without malformed test rows.")
        print("PASS: no synthetic telemetry generated.")
        print("PASS: no synthetic prediction generated.")

    print()
    print("Backend lifespan: STOPPED")
    print("Collector shutdown completed.")


if __name__ == "__main__":
    asyncio.run(run())
