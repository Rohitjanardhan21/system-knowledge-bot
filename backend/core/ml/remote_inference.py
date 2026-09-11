"""
CVIS — Remote Device Inference

Inference-only scoring for remote devices.

The neural models are shared from the existing MLEngine, while temporal
history and EMA state remain isolated per device.
"""

import time
from collections import deque
from typing import Dict

import numpy as np

from backend.core.ml.ml_engine import FEAT_DIM, SEQ_LEN, TORCH_OK, SK_OK


class RemoteDeviceState:
    """Runtime inference state belonging to exactly one remote device."""

    def __init__(self):
        self.feature_history = deque(maxlen=SEQ_LEN)
        self.if_ema = 0.0
        self.vae_ema = 0.0
        self.lstm_ema = 0.0

        self.samples = 0
        self.last_seen = 0.0

        self.if_score = 0.0
        self.vae_score = 0.0
        self.lstm_score = 0.0
        self.ensemble_score = 0.0


class RemoteInferenceManager:
    """
    Scores remote devices using the currently loaded global model.

    Important:
    - Does NOT call MLEngine.ingest()
    - Does NOT call MLEngine.score()
    - Does NOT train the shared models
    - Maintains sequence history and EMA independently per device
    """

    def __init__(self, engine):
        self.engine = engine
        self.devices: Dict[str, RemoteDeviceState] = {}

    def _state(self, device_id: str) -> RemoteDeviceState:
        if device_id not in self.devices:
            self.devices[device_id] = RemoteDeviceState()
        return self.devices[device_id]

    @staticmethod
    def build_feature_vector(metrics: dict) -> np.ndarray:
        """
        Preserve the existing CVIS 5-feature schema:

        [cpu/100, memory/100, disk/100, network/100, anomaly]
        """

        cpu = float(metrics.get("cpu_percent", 0.0))
        mem = float(metrics.get("memory", metrics.get("memory_percent", 0.0)))
        disk = float(metrics.get("disk_percent", 0.0))
        net = float(metrics.get("network_percent", 0.0))
        ano = float(metrics.get("anomaly_score", 0.0))

        values = np.array(
            [
                np.clip(cpu / 100.0, 0.0, 1.0),
                np.clip(mem / 100.0, 0.0, 1.0),
                np.clip(disk / 100.0, 0.0, 1.0),
                np.clip(net / 100.0, 0.0, 1.0),
                np.clip(ano, 0.0, 1.0),
            ],
            dtype=np.float32,
        )

        if values.shape != (FEAT_DIM,):
            raise ValueError(
                f"Remote feature vector has shape {values.shape}, "
                f"expected {(FEAT_DIM,)}"
            )

        return values

    def score(self, device_id: str, metrics: dict) -> dict:
        state = self._state(device_id)
        feat = self.build_feature_vector(metrics)

        state.feature_history.append(feat.copy())
        state.samples += 1
        state.last_seen = time.time()

        # --------------------------------------------------
        # Isolation Forest
        # --------------------------------------------------
        if SK_OK and getattr(self.engine, "_if_fitted", False):
            arr = self.engine.if_scaler.transform(
                feat.reshape(1, -1)
            )
            raw = float(self.engine.if_model.score_samples(arr)[0])
            if_raw = max(0.0, min(1.0, (-raw - 0.1) * 2.0))
        else:
            if_raw = max(
                0.0,
                min(
                    1.0,
                    feat[0] * 0.4
                    + feat[1] * 0.3
                    + feat[4] * 0.3,
                ),
            )

        # --------------------------------------------------
        # VAE
        # --------------------------------------------------
        vae_raw = float(self.engine.vae_net.anomaly_score(feat))

        # --------------------------------------------------
        # LSTM
        #
        # Use ONLY this device's sequence history.
        # --------------------------------------------------
        lstm_raw = 0.0

        if (
            TORCH_OK
            and len(state.feature_history) >= SEQ_LEN
        ):
            import torch
            import torch.nn.functional as F

            self.engine.lstm_net.eval()

            seq = torch.tensor(
                np.stack(state.feature_history),
                dtype=torch.float32,
            ).unsqueeze(0)

            with torch.no_grad():
                pred, _ = self.engine.lstm_net(seq)

            target = torch.tensor(
                feat,
                dtype=torch.float32,
            )

            err = float(
                F.mse_loss(pred.squeeze(), target)
            )

            lstm_raw = min(1.0, err * 10.0)

        elif len(state.feature_history) >= 2:
            # Not enough temporal context for a meaningful LSTM score.
            lstm_raw = 0.0

        # --------------------------------------------------
        # Per-device EMA
        # --------------------------------------------------
        alpha = 0.3

        state.if_ema = float(
            alpha * if_raw + (1.0 - alpha) * state.if_ema
        )
        state.vae_ema = float(
            alpha * vae_raw + (1.0 - alpha) * state.vae_ema
        )
        state.lstm_ema = float(
            alpha * lstm_raw + (1.0 - alpha) * state.lstm_ema
        )

        ensemble = (
            state.if_ema * 0.40
            + state.vae_ema * 0.35
            + state.lstm_ema * 0.25
        )

        state.if_score = round(state.if_ema, 4)
        state.vae_score = round(state.vae_ema, 4)
        state.lstm_score = round(state.lstm_ema, 4)
        state.ensemble_score = round(ensemble, 4)

        return {
            "if_score": state.if_score,
            "vae_score": state.vae_score,
            "lstm_score": state.lstm_score,
            "ensemble_score": state.ensemble_score,
            "samples": state.samples,
            "sequence_ready": len(state.feature_history) >= SEQ_LEN,
            "model_fitted": bool(
                getattr(self.engine.metrics, "model_fitted", False)
            ),
        }

    def get_state(self, device_id: str) -> dict:
        state = self.devices.get(device_id)

        if state is None:
            return {
                "samples": 0,
                "sequence_ready": False,
                "if_score": 0.0,
                "vae_score": 0.0,
                "lstm_score": 0.0,
                "ensemble_score": 0.0,
            }

        return {
            "samples": state.samples,
            "sequence_ready": len(state.feature_history) >= SEQ_LEN,
            "if_score": state.if_score,
            "vae_score": state.vae_score,
            "lstm_score": state.lstm_score,
            "ensemble_score": state.ensemble_score,
        }

    def remove(self, device_id: str):
        self.devices.pop(device_id, None)
