"""
pipeline/ml/autoencoder.py  —  CVIS v5.0
──────────────────────────────────────────
Upgrade 1a — Autoencoder Anomaly Detector

Architecture:
  Encoder: 15 → 8 → 4 → 2  (bottleneck)
  Decoder:  2 → 4 → 8 → 15  (reconstruction)

  anomaly_score = MSE(input, reconstruction)

Why autoencoder over IsolationForest:
  • Learns the *manifold* of normal operation, not just path lengths
  • Reconstruction error is interpretable (which features deviate most)
  • Naturally handles temporal correlations if input includes lag features
  • Scales better to high-dimensional fused sensor vectors

Training:
  • Online mini-batch SGD — updates every TRAIN_EVERY samples
  • EarlyStopping on reconstruction loss variance (stable baseline)
  • Normalisation: same FEATURE_RANGES pre-norm as IsolationForest
    so both models receive identical input distributions

Inference:
  • Pure numpy — no torch dependency required at runtime
  • Weights stored as plain np.ndarray — serialisable with np.save
  • Falls back to random-init reconstruction until MIN_TRAIN_SAMPLES
"""

import logging
import threading
import time
from collections import deque

import numpy as np

log = logging.getLogger("cvis.autoencoder")

# ── Configuration ─────────────────────────────────────────────
MIN_TRAIN_SAMPLES = 100    # samples before first training pass
TRAIN_EVERY       = 50     # retrain every N new samples
WINDOW_SIZE       = 3000   # rolling training window
LEARNING_RATE     = 0.003
EPOCHS_PER_TRAIN  = 30
BATCH_SIZE        = 32

# Same domain ranges as IsolationForest for consistent pre-normalisation
FEATURE_RANGES = [
    (0, 140), (50, 130), (0, 60), (0, 6000), (0, 100),
    (-3, 3), (-3, 3), (-2, 2), (-1, 1),
    (-20, 20), (-5, 5), (0, 4), (0, 9), (-2, 2), (0, 3),
]
N_FEATURES = len(FEATURE_RANGES)


def _relu(x):    return np.maximum(0, x)
def _sigmoid(x): return 1 / (1 + np.exp(-np.clip(x, -50, 50)))


class DenseLayer:
    """Single fully-connected layer with Xavier initialisation."""
    def __init__(self, n_in: int, n_out: int, activation="relu"):
        scale          = np.sqrt(2.0 / n_in)
        self.W         = np.random.randn(n_in, n_out) * scale
        self.b         = np.zeros(n_out)
        self.activation = activation
        # Adam optimiser state
        self.mW = np.zeros_like(self.W);  self.vW = np.zeros_like(self.W)
        self.mb = np.zeros_like(self.b);  self.vb = np.zeros_like(self.b)
        self.t  = 0
        # Forward cache
        self._z = None;  self._a_prev = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        self._a_prev = x
        self._z      = x @ self.W + self.b
        if self.activation == "relu":    return _relu(self._z)
        if self.activation == "sigmoid": return _sigmoid(self._z)
        return self._z   # linear

    def backward(self, d_out: np.ndarray, lr: float) -> np.ndarray:
        if self.activation == "relu":
            d_out = d_out * (self._z > 0)
        elif self.activation == "sigmoid":
            s     = _sigmoid(self._z)
            d_out = d_out * s * (1 - s)

        dW = self._a_prev.T @ d_out / len(d_out)
        db = d_out.mean(axis=0)

        # ── Gradient clipping (Fix 1) ──────────────────────────
        # Prevents exploding gradients when reconstruction error is large
        # (e.g. during warm-up or after a sudden sensor spike).
        # Clip norm of weight gradient to MAX_GRAD_NORM before Adam step.
        MAX_GRAD_NORM = 1.0
        dW_norm = np.linalg.norm(dW)
        if dW_norm > MAX_GRAD_NORM:
            dW = dW * (MAX_GRAD_NORM / dW_norm)

        # Adam update
        self.t  += 1
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        self.mW  = beta1*self.mW + (1-beta1)*dW
        self.vW  = beta2*self.vW + (1-beta2)*dW**2
        self.mb  = beta1*self.mb + (1-beta1)*db
        self.vb  = beta2*self.vb + (1-beta2)*db**2
        mW_hat   = self.mW / (1-beta1**self.t)
        vW_hat   = self.vW / (1-beta2**self.t)
        mb_hat   = self.mb / (1-beta1**self.t)
        vb_hat   = self.vb / (1-beta2**self.t)
        self.W  -= lr * mW_hat / (np.sqrt(vW_hat) + eps)
        self.b  -= lr * mb_hat / (np.sqrt(vb_hat) + eps)

        # Clip upstream gradient before passing back (stops error explosion
        # propagating through deep layers when input features spike)
        d_upstream = d_out @ self.W.T
        return np.clip(d_upstream, -5.0, 5.0)


class Autoencoder:
    """
    Shallow autoencoder: 15→8→4→2→4→8→15
    Pure numpy, no torch required.
    """
    def __init__(self):
        self.encoder = [
            DenseLayer(N_FEATURES, 8,  "relu"),
            DenseLayer(8,          4,  "relu"),
            DenseLayer(4,          2,  "linear"),   # bottleneck
        ]
        self.decoder = [
            DenseLayer(2,  4,          "relu"),
            DenseLayer(4,  8,          "relu"),
            DenseLayer(8,  N_FEATURES, "sigmoid"),  # output in [0,1]
        ]
        self.layers = self.encoder + self.decoder

    def forward(self, x: np.ndarray) -> np.ndarray:
        out = x
        for layer in self.layers:
            out = layer.forward(out)
        return out

    def reconstruct(self, x: np.ndarray) -> np.ndarray:
        return self.forward(x)

    def train_batch(self, X: np.ndarray, lr: float) -> float:
        """
        One forward+backward pass. Returns mean MSE loss.

        Gradient clipping (Fix: prevents exploding gradients):
          The raw MSE gradient 2*(recon-X) can spike to large values
          during warm-up when weights are random.  Clipping to [-GRAD_CLIP,
          +GRAD_CLIP] before backprop keeps all weight updates bounded and
          ensures stable convergence regardless of input scale.
        """
        GRAD_CLIP = 5.0
        recon     = self.forward(X)
        loss      = np.mean((X - recon) ** 2)
        d_loss    = 2 * (recon - X) / X.shape[0]
        # Clip gradient before it enters backprop
        d_loss    = np.clip(d_loss, -GRAD_CLIP, GRAD_CLIP)
        for layer in reversed(self.layers):
            d_loss = layer.backward(d_loss, lr)
            # Clip at each layer to prevent gradient explosion through deep stack
            d_loss = np.clip(d_loss, -GRAD_CLIP, GRAD_CLIP)
        return float(loss)

    def mse(self, x: np.ndarray) -> float:
        """
        Per-sample reconstruction MSE (1-D input → scalar).
        Error clipped to [0, 5] so outlier inputs don't produce scores >> 1.
        """
        x_2d  = x.reshape(1, -1)
        recon = self.forward(x_2d)
        err   = np.clip((x_2d - recon) ** 2, 0.0, 5.0)
        return float(np.mean(err))

    def feature_errors(self, x: np.ndarray) -> np.ndarray:
        """
        Per-feature squared reconstruction error, clipped to [0, 5].
        Clipping prevents a single saturated feature from dominating
        the contribution breakdown shown in the dashboard top_signals panel.
        """
        x_2d  = x.reshape(1, -1)
        recon = self.forward(x_2d)
        return np.clip(((x_2d - recon) ** 2).flatten(), 0.0, 5.0)


class AutoencoderDetector:
    """
    Online-learning autoencoder anomaly detector.

    Runs alongside IsolationForest in the ensemble.
    Score = percentile rank of reconstruction MSE in the training window.
    """

    FEATURE_NAMES = [
        "speed", "thermal", "vibration", "rpm", "brake",
        "acc_x", "acc_y", "gyro_yaw", "lane_offset",
        "speed_delta", "thermal_delta", "acc_magnitude",
        "lateral_energy", "jerk", "brake_speed_ratio",
    ]

    def __init__(self):
        self._lock      = threading.Lock()
        self._model     = Autoencoder()
        self._window    = deque(maxlen=WINDOW_SIZE)
        self._mse_hist  = deque(maxlen=WINDOW_SIZE)   # rolling MSE for percentile
        self._fitted    = False
        self._n_samples = 0
        self._since_fit = 0
        self._prev: dict = {}
        self._train_losses: list = []
        log.info("AutoencoderDetector initialised (15→8→4→2→4→8→15)")

    def _pre_normalize(self, features: list[float]) -> np.ndarray:
        out = []
        for v, (lo, hi) in zip(features, FEATURE_RANGES):
            span = hi - lo
            out.append(0.0 if span == 0 else float(max(0.0, min(1.0, (v-lo)/span))))
        return np.array(out, dtype=np.float32)

    def _engineer(self, s: dict) -> list[float]:
        import math
        speed   = float(s.get("speed", 0))
        thermal = float(s.get("thermal", 70))
        vib     = float(s.get("vibration", 0))
        rpm     = float(s.get("rpm", 800))
        brake   = float(s.get("brake", 0))
        ax      = float(s.get("acc_x", 0))
        ay      = float(s.get("acc_y", 0))
        gz      = float(s.get("gyro_yaw", 0))
        lane    = float(s.get("lane_offset", 0))
        ps, pt, pm = (self._prev.get(k, v) for k, v in
                      [("speed", speed), ("thermal", thermal), ("acc_mag", 1.0)])
        acc_mag = math.sqrt(ax**2 + ay**2 + 0.98**2)
        self._prev.update({"speed": speed, "thermal": thermal, "acc_mag": acc_mag})
        return [speed, thermal, vib, rpm, brake, ax, ay, gz, lane,
                speed-ps, thermal-pt, acc_mag, ax**2+ay**2, acc_mag-pm, brake/(speed+1e-6)]

    def _train(self):
        data = np.array(list(self._window), dtype=np.float32)
        if len(data) < BATCH_SIZE:
            return
        losses = []
        idx = np.arange(len(data))
        for _ in range(EPOCHS_PER_TRAIN):
            np.random.shuffle(idx)
            for start in range(0, len(idx)-BATCH_SIZE, BATCH_SIZE):
                batch = data[idx[start:start+BATCH_SIZE]]
                loss  = self._model.train_batch(batch, LEARNING_RATE)
                losses.append(loss)
        self._fitted    = True
        self._since_fit = 0
        self._train_losses.append(float(np.mean(losses)))
        if len(self._train_losses) > 50: self._train_losses.pop(0)
        log.info(f"Autoencoder retrained: loss={np.mean(losses):.5f}")

    def score(self, raw_signals: dict) -> dict:
        with self._lock:
            feat  = self._engineer(raw_signals)
            norm  = self._pre_normalize(feat)
            self._window.append(norm)
            self._n_samples  += 1
            self._since_fit  += 1

            if self._n_samples == MIN_TRAIN_SAMPLES:
                self._train()
            elif self._fitted and self._since_fit >= TRAIN_EVERY:
                self._train()

            if not self._fitted:
                warmup = min(100, int(self._n_samples / MIN_TRAIN_SAMPLES * 100))
                return {"score": 0.0, "is_anomaly": False, "severity": "NORMAL",
                        "top_signals": [], "model_type": f"AE-Warmup({warmup}%)",
                        "reconstruction_mse": 0.0}

            mse   = self._model.mse(norm)
            self._mse_hist.append(mse)

            # Percentile rank = fraction of historical MSEs below current
            hist  = np.array(self._mse_hist)
            score = float(np.mean(hist <= mse))   # [0,1], 1 = most anomalous

            feat_err  = self._model.feature_errors(norm)
            top_sigs  = sorted(
                [{"signal": n, "value": round(float(norm[i]), 3),
                  "contribution": round(float(feat_err[i])/max(float(feat_err.sum()),1e-6), 3),
                  "recon_err": round(float(feat_err[i]), 5)}
                 for i, n in enumerate(self.FEATURE_NAMES)],
                key=lambda x: -x["contribution"],
            )[:5]

            is_anom  = score > 0.90   # top 10% of reconstruction errors
            severity = ("CRITICAL" if score > 0.95 else
                        "WARNING"  if score > 0.85 else "NORMAL")

            return {
                "score":             round(score, 4),
                "is_anomaly":        is_anom,
                "severity":          severity,
                "top_signals":       top_sigs,
                "model_type":        "Autoencoder",
                "reconstruction_mse": round(mse, 6),
                "n_samples":         self._n_samples,
                "train_loss":        round(self._train_losses[-1], 6) if self._train_losses else None,
                # Confidence: how far the current MSE is from the worst observed.
                # Errors are clipped to [0, 5] so max_error = 5.0.
                # High confidence (→1) = reconstruction is close to normal;
                # Low confidence (→0) = reconstruction is near the clipped ceiling.
                "confidence":        round(1.0 - min(mse / 5.0, 1.0), 4),
            }
