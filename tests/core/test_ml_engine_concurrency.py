import threading

import numpy as np

from backend.core.ml.ml_engine import MLEngine


FEAT = np.array([0.3, 0.4, 0.2, 0.1, 0.05], dtype=np.float32)


def test_score_and_ingest_can_run_concurrently():
    """
    Stress the current shared MLEngine from two threads.

    This is intentionally a baseline test: it does not assume a lock exists.
    It checks whether concurrent ingest/training and scoring produce exceptions
    or obviously invalid metrics.
    """
    engine = MLEngine()

    # Build enough history for LSTM sequences and periodic training.
    for _ in range(40):
        engine.ingest(FEAT)

    errors = []
    barrier = threading.Barrier(3)

    def trainer():
        try:
            barrier.wait()
            for _ in range(50):
                engine.ingest(FEAT)
        except Exception as exc:
            errors.append(("ingest", repr(exc)))

    def scorer():
        try:
            barrier.wait()
            for _ in range(100):
                metrics = engine.score(FEAT)
                assert 0.0 <= metrics.ensemble_score <= 1.0
                assert 0.0 <= metrics.if_score <= 1.0
                assert 0.0 <= metrics.vae_score <= 1.0
                assert 0.0 <= metrics.lstm_score <= 1.0
        except Exception as exc:
            errors.append(("score", repr(exc)))

    t1 = threading.Thread(target=trainer, name="test-ml-trainer")
    t2 = threading.Thread(target=scorer, name="test-ml-scorer")

    t1.start()
    t2.start()
    barrier.wait()

    t1.join()
    t2.join()

    assert not errors, f"Concurrent ML engine errors: {errors}"


def test_score_and_load_state_dict_can_run_concurrently():
    """
    Stress scoring while the live model parameters are repeatedly replaced.
    Baseline test: production code is intentionally unchanged.
    """
    engine = MLEngine()

    for _ in range(40):
        engine.ingest(FEAT)

    state = engine.state_dict()
    errors = []
    barrier = threading.Barrier(3)

    def scorer():
        try:
            barrier.wait()
            for _ in range(100):
                metrics = engine.score(FEAT)
                assert 0.0 <= metrics.ensemble_score <= 1.0
        except Exception as exc:
            errors.append(("score", repr(exc)))

    def loader():
        try:
            barrier.wait()
            for _ in range(50):
                engine.load_state_dict(state)
        except Exception as exc:
            errors.append(("load", repr(exc)))

    t1 = threading.Thread(target=scorer, name="test-ml-scorer")
    t2 = threading.Thread(target=loader, name="test-ml-loader")

    t1.start()
    t2.start()
    barrier.wait()

    t1.join()
    t2.join()

    assert not errors, f"Concurrent load/score errors: {errors}"


def test_state_dict_and_ingest_can_run_concurrently():
    """
    Stress model serialization while ingest/training is occurring.
    Baseline test: production code is intentionally unchanged.
    """
    engine = MLEngine()

    for _ in range(40):
        engine.ingest(FEAT)

    errors = []
    barrier = threading.Barrier(3)

    def trainer():
        try:
            barrier.wait()
            for _ in range(50):
                engine.ingest(FEAT)
        except Exception as exc:
            errors.append(("ingest", repr(exc)))

    def saver():
        try:
            barrier.wait()
            for _ in range(50):
                state = engine.state_dict()
                assert "lstm" in state
                assert "vae" in state
                assert "metrics" in state
        except Exception as exc:
            errors.append(("state_dict", repr(exc)))

    t1 = threading.Thread(target=trainer, name="test-ml-trainer")
    t2 = threading.Thread(target=saver, name="test-ml-saver")

    t1.start()
    t2.start()
    barrier.wait()

    t1.join()
    t2.join()

    assert not errors, f"Concurrent save/training errors: {errors}"
