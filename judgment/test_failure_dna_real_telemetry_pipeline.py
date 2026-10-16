import asyncio
import threading
import time

import psutil

from backend.main import (
    _build_feature_vector,
    _collector_stop,
    _last_metrics,
    _lock,
    app,
)
from backend.core.cognitive.failure_dna import get_dna_engine


async def run():
    print("=== REAL PRODUCTION TELEMETRY -> FAILUREDNA TEST ===")
    print()
    print("REAL-LIFE SCENARIO:")
    print("The CVIS backend starts normally.")
    print("Its real collector samples the machine.")
    print("FailureDNA receives the same telemetry used by production.")
    print("No synthetic telemetry is injected.")
    print()

    assert psutil is not None
    print("psutil: AVAILABLE")
    print("real host CPU sample:", psutil.cpu_percent(interval=0.5))
    print("real host memory:", psutil.virtual_memory().percent)
    print()

    dna = get_dna_engine()

    before_buffer = len(dna._metric_buffer)

    print("FailureDNA buffer before startup:", before_buffer)

    # Run the application's actual FastAPI lifespan.
    async with app.router.lifespan_context(app):
        print()
        print("Backend lifespan: STARTED")
        print("Waiting for real collector observations...")

        deadline = time.time() + 8.0

        while time.time() < deadline:
            with _lock:
                current = dict(_last_metrics)

            if current.get("collected_at") is not None:
                break

            await asyncio.sleep(0.25)

        with _lock:
            metrics = dict(_last_metrics)

        print()
        print("=== REAL COLLECTOR TELEMETRY ===")
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
                f"Missing/non-numeric real telemetry: {key}"
            )

        after_buffer = len(dna._metric_buffer)

        print()
        print("FailureDNA buffer after startup:", after_buffer)

        assert after_buffer > before_buffer, (
            "FailureDNA did not receive observations from the production collector."
        )

        print()
        print("=== FAILUREDNA PRODUCTION STATE ===")
        print("metric observations received:", after_buffer - before_buffer)
        print("active predictions:", len(dna.get_active_predictions()))

        print()
        print("PASS: real production telemetry reached FailureDNA.")
        print("No synthetic telemetry generated.")
        print("No telemetry values manually injected.")

    print()
    print("Backend lifespan: STOPPED")
    print("Collector shutdown completed.")

    _collector_stop.clear()


if __name__ == "__main__":
    asyncio.run(run())
