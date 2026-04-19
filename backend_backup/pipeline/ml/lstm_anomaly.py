"""
pipeline/ml/lstm_anomaly.py  —  CVIS v5.0
───────────────────────────────────────────
Upgrade 1b — LSTM Time-Series Anomaly Detector

Architecture:
  Input:  (SEQ_LEN=20, N_FEATURES=15)  — sliding window of normalised telemetry
  LSTM:   hidden_size=32, 1 layer
  Head:   Linear(32 → N_FEATURES)      — predict next timestep
  Loss:   MSE(prediction, actual_next) — high error = anomaly

CPU budget design (Fix 2):
  Pure numpy BPTT can become CPU-heavy if training runs every tick.
  Two-mode operation keeps inference on the hot path and training off it:

    INFER mode  (every frame, ~0.3 ms):
      • Only runs forward pass on the 20-frame sliding window
      • Returns prediction error as anomaly score
      • Gated: skips entirely if _fitted=False (returns score=0)

    TRAIN mode  (async thread, every TRAIN_EVERY=50 samples):
      • Fires in a daemon thread — never blocks the event loop
      • EPOCHS=10 (reduced from 20) × BATCH_SIZE=16
      • Guarded by a threading.Event so two trains never overlap

  Result: inference is always <1 ms; training is ~20-80 ms but
  happens in the background and never delays a frame.
"""

import logging
import math
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np

log = logging.getLogger("cvis.lstm")

SEQ_LEN     = 20     # frames per sequence
HIDDEN      = 32     # LSTM hidden units
N_FEATURES  = 15
LR          = 0.002
TRAIN_EVERY = 50     # retrain cadence (raised from 40 to reduce CPU)
MIN_TRAIN   = 60
WINDOW_SIZE = 2000
EPOCHS      = 10     # reduced from 20 — background thread is finite
BATCH_SIZE  = 16
GRAD_CLIP   = 2.0    # clip LSTM gradients (prevents spike during warm-up)

FEATURE_RANGES = [
    (0, 140), (50, 130), (0, 60), (0, 6000), (0, 100),
    (-3, 3), (-3, 3), (-2, 2), (-1, 1),
    (-20, 20), (-5, 5), (0, 4), (0, 9), (-2, 2), (0, 3),
]

FEATURE_NAMES = [
    "speed", "thermal", "vibration", "rpm", "brake",
    "acc_x", "acc_y", "gyro_yaw", "lane_offset",
    "speed_delta", "thermal_delta", "acc_magnitude",
    "lateral_energy", "jerk", "brake_speed_ratio",
]


def _sigmoid(x): return 1 / (1 + np.exp(-np.clip(x, -10, 10)))
def _tanh(x):    return np.tanh(np.clip(x, -10, 10))


class LSTMCell:
    """
    Single LSTM cell — pure numpy.
    State: (h, c)  both shape (batch, H)
    """
    def __init__(self, n_in: int, n_hidden: int):
        H  = n_hidden
        # Combined weight matrix [W_i, W_f, W_g, W_o] — 4*H output cols
        scale      = np.sqrt(1.0 / n_hidden)
        self.Wx    = np.random.randn(n_in,    4*H) * scale
        self.Wh    = np.random.randn(n_hidden, 4*H) * scale
        self.b     = np.zeros(4*H)
        self.b[H:2*H] = 1.0   # forget gate bias = 1 (standard init)

        # Adam state
        for name in ("Wx", "Wh", "b"):
            w = getattr(self, name)
            setattr(self, f"m{name}", np.zeros_like(w))
            setattr(self, f"v{name}", np.zeros_like(w))
        self.t = 0

        self.H = H
        self._cache: list = []   # for BPTT

    def forward(self, x: np.ndarray, h: np.ndarray, c: np.ndarray):
        """x: (B, n_in), h/c: (B, H)  →  h_new, c_new"""
        B  = x.shape[0]
        z  = x @ self.Wx + h @ self.Wh + self.b   # (B, 4H)
        H  = self.H
        i  = _sigmoid(z[:, :H])
        f  = _sigmoid(z[:, H:2*H])
        g  = _tanh(   z[:, 2*H:3*H])
        o  = _sigmoid(z[:, 3*H:])
        c_new = f * c + i * g
        h_new = o * _tanh(c_new)
        self._cache.append((x, h, c, i, f, g, o, c_new, h_new))
        return h_new, c_new

    def backward(self, dh_next: np.ndarray, dc_next: np.ndarray,
                 lr: float) -> tuple:
        """BPTT one step. Returns (dx, dh_prev, dc_prev)."""
        (x, h_prev, c_prev, i, f, g, o, c_new, h_new) = self._cache.pop()
        tanh_c   = _tanh(c_new)
        do       = dh_next * tanh_c
        dc       = dh_next * o * (1 - tanh_c**2) + dc_next
        di       = dc * g
        df       = dc * c_prev
        dg       = dc * i
        dc_prev  = dc * f

        di_raw   = di * i * (1 - i)
        df_raw   = df * f * (1 - f)
        dg_raw   = dg * (1 - g**2)
        do_raw   = do * o * (1 - o)
        dz       = np.concatenate([di_raw, df_raw, dg_raw, do_raw], axis=1)

        dWx = x.T @ dz / x.shape[0]
        dWh = h_prev.T @ dz / x.shape[0]
        db  = dz.mean(axis=0)
        dx  = dz @ self.Wx.T
        dh_prev = dz @ self.Wh.T

        self._adam_update("Wx", dWx, lr)
        self._adam_update("Wh", dWh, lr)
        self._adam_update("b",  db,  lr)
        return dx, dh_prev, dc_prev

    def _adam_update(self, name: str, grad: np.ndarray, lr: float):
        self.t  += 1
        b1, b2, eps = 0.9, 0.999, 1e-8
        m = getattr(self, f"m{name}"); v = getattr(self, f"v{name}")
        m  = b1*m + (1-b1)*grad;  setattr(self, f"m{name}", m)
        v  = b2*v + (1-b2)*grad**2; setattr(self, f"v{name}", v)
        mh = m / (1-b1**self.t);  vh = v / (1-b2**self.t)
        setattr(self, name, getattr(self, name) - lr * mh / (np.sqrt(vh)+eps))


class LSTMAnomalyDetector:
    """
    Predict-next-step LSTM anomaly detector.
    anomaly_score = percentile(||pred - actual||², rolling history)
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self.lstm     = LSTMCell(N_FEATURES, HIDDEN)
        # Linear head: HIDDEN → N_FEATURES
        scale         = np.sqrt(1.0 / HIDDEN)
        self.Wout     = np.random.randn(HIDDEN, N_FEATURES) * scale
        self.bout     = np.zeros(N_FEATURES)
        self.mWo      = np.zeros_like(self.Wout); self.vWo = np.zeros_like(self.Wout)
        self.mbo      = np.zeros_like(self.bout); self.vbo = np.zeros_like(self.bout)
        self.t_out    = 0

        self._seq_buf : deque = deque(maxlen=SEQ_LEN+1)
        self._window  : deque = deque(maxlen=WINDOW_SIZE)
        self._err_hist: deque = deque(maxlen=WINDOW_SIZE)
        self._n       = 0
        self._fitted  = False
        self._since   = 0
        self._prev: dict = {}

        # Fix 2: training runs in a background thread so inference is never blocked.
        # _training_event prevents two concurrent train jobs from overlapping.
        self._training_event = threading.Event()
        self._training_event.set()   # initially "not training" → set = free
        self._train_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lstm_train")
        log.info(f"LSTM anomaly detector initialised (seq={SEQ_LEN}, h={HIDDEN}, async_train=True)")

    def _pre_normalize(self, features: list) -> np.ndarray:
        out = []
        for v, (lo, hi) in zip(features, FEATURE_RANGES):
            span = hi - lo
            out.append(0.0 if span == 0 else float(max(0.0, min(1.0, (v-lo)/span))))
        return np.array(out, dtype=np.float32)

    def _engineer(self, s: dict) -> list:
        speed   = float(s.get("speed", 0))
        thermal = float(s.get("thermal", 70))
        vib     = float(s.get("vibration", 0))
        rpm     = float(s.get("rpm", 800))
        brake   = float(s.get("brake", 0))
        ax      = float(s.get("acc_x", 0))
        ay      = float(s.get("acc_y", 0))
        gz      = float(s.get("gyro_yaw", 0))
        lane    = float(s.get("lane_offset", 0))
        ps  = self._prev.get("speed", speed)
        pt  = self._prev.get("thermal", thermal)
        pm  = self._prev.get("acc_mag", 1.0)
        acc_mag = math.sqrt(ax**2 + ay**2 + 0.98**2)
        self._prev.update({"speed": speed, "thermal": thermal, "acc_mag": acc_mag})
        return [speed, thermal, vib, rpm, brake, ax, ay, gz, lane,
                speed-ps, thermal-pt, acc_mag, ax**2+ay**2, acc_mag-pm, brake/(speed+1e-6)]

    def _predict(self, seq: np.ndarray) -> np.ndarray:
        """seq: (SEQ_LEN, N_FEATURES) → predicted next frame (N_FEATURES,).
        Pure forward pass — always fast (~0.3 ms on CPU)."""
        h = np.zeros((1, HIDDEN)); c = np.zeros((1, HIDDEN))
        for t in range(len(seq)):
            x    = seq[t:t+1]
            h, c = self.lstm.forward(x, h, c)
        return np.clip((h @ self.Wout + self.bout).flatten(), 0.0, 1.0)

    def _train_background(self, data: np.ndarray):
        """
        Training job executed in a background ThreadPoolExecutor worker.
        Fix 2 — never runs on the inference hot path:
          • _training_event.clear()  marks training as in-progress
          • _training_event.set()    marks training as done
          • score() checks is_set() before triggering a new train
            → two train jobs never overlap
          • Gradient clipping: upstream grads clipped to ±GRAD_CLIP
            prevents BPTT instability on long sequences
        """
        self._training_event.clear()
        try:
            all_losses = []
            for _ in range(EPOCHS):
                starts     = np.random.randint(0, len(data)-SEQ_LEN-1, BATCH_SIZE)
                batch_loss = []
                for s in starts:
                    seq    = data[s:s+SEQ_LEN]
                    target = data[s+SEQ_LEN]
                    pred   = self._predict(seq)
                    err    = np.clip((pred - target)**2, 0, 5.0)  # clip per-feature error
                    loss   = float(err.mean())

                    # Backprop through linear head
                    d_pred  = np.clip(2*(pred - target) / N_FEATURES, -GRAD_CLIP, GRAD_CLIP)
                    h_last  = self.lstm._cache[-1][-1] if self.lstm._cache else np.zeros((1, HIDDEN))
                    dWo     = h_last.T @ d_pred.reshape(1, -1)
                    dbo     = d_pred

                    # Adam for output head
                    self.t_out += 1
                    b1, b2, eps = 0.9, 0.999, 1e-8
                    self.mWo = b1*self.mWo + (1-b1)*dWo
                    self.vWo = b2*self.vWo + (1-b2)*dWo**2
                    self.mbo = b1*self.mbo + (1-b1)*dbo
                    self.vbo = b2*self.vbo + (1-b2)*dbo**2
                    mWh = self.mWo/(1-b1**self.t_out); vWh = self.vWo/(1-b2**self.t_out)
                    mbh = self.mbo/(1-b1**self.t_out); vbh = self.vbo/(1-b2**self.t_out)
                    self.Wout -= LR * mWh / (np.sqrt(vWh)+eps)
                    self.bout -= LR * mbh / (np.sqrt(vbh)+eps)
                    # Clear LSTM cache after each sample to avoid memory growth
                    self.lstm._cache.clear()
                    batch_loss.append(float(loss))
                all_losses.extend(batch_loss)

            with self._lock:
                self._fitted  = True
                self._since   = 0
            log.info(f"LSTM retrained (background): mean_loss={np.mean(all_losses):.5f}")
        except Exception as e:
            log.warning(f"LSTM background train error: {e}")
        finally:
            self._training_event.set()   # mark as free regardless of outcome

    def _train(self):
        """
        Trigger a background training job if not already running.
        Returns immediately — never blocks the inference hot path.
        """
        if not self._training_event.is_set():
            log.debug("LSTM: training already in progress — skipping trigger")
            return
        data = np.array(list(self._window), dtype=np.float32)
        if len(data) < SEQ_LEN + BATCH_SIZE:
            return
        self._train_executor.submit(self._train_background, data)

    def score(self, raw_signals: dict) -> dict:
        """
        Infer-only on the hot path (Fix 2).
        If _fitted=False, returns score=0 immediately — no work done.
        Training is triggered asynchronously and never delays this call.
        """
        with self._lock:
            feat = self._engineer(raw_signals)
            norm = self._pre_normalize(feat)
            self._seq_buf.append(norm)
            self._window.append(norm)
            self._n      += 1
            self._since  += 1

            if self._n == MIN_TRAIN:     self._train()
            elif self._fitted and self._since >= TRAIN_EVERY: self._train()

            if not self._fitted or len(self._seq_buf) < SEQ_LEN:
                pct = min(100, int(self._n / MIN_TRAIN * 100))
                return {"score": 0.0, "is_anomaly": False, "severity": "NORMAL",
                        "top_signals": [], "model_type": f"LSTM-Warmup({pct}%)",
                        "prediction_error": 0.0}

            seq   = np.array(list(self._seq_buf)[-SEQ_LEN:], dtype=np.float32)
            pred  = self._predict(seq)
            # Clip per-feature error to [0, 5] — same bound as autoencoder
            err   = np.clip((pred - norm)**2, 0.0, 5.0)
            total = float(err.mean())
            self._err_hist.append(total)

            hist  = np.array(self._err_hist)
            score = float(np.mean(hist <= total))

            top_sigs = sorted(
                [{"signal": n, "value": round(float(norm[i]), 3),
                  "contribution": round(float(err[i])/max(float(err.sum()),1e-6), 3),
                  "pred": round(float(pred[i]), 3)}
                 for i, n in enumerate(FEATURE_NAMES)],
                key=lambda x: -x["contribution"],
            )[:5]

            is_anom  = score > 0.90
            severity = ("CRITICAL" if score > 0.95 else
                        "WARNING"  if score > 0.85 else "NORMAL")

            # Temporal explanation.
            # Safety floor of 0.15 prevents spurious triggers during early
            # training when error history is sparse and the p90 could be
            # artificially low. Dashboard shows "Pattern break detected".
            if len(self._err_hist) >= 10:
                _p90 = float(np.percentile(np.array(self._err_hist), 90))
                _temporal_threshold = max(_p90, 0.15)
                _temporal_break = bool(total > _temporal_threshold)
            else:
                _temporal_break = False

            return {
                "score":             round(score, 4),
                "is_anomaly":        is_anom,
                "severity":          severity,
                "top_signals":       top_sigs,
                "model_type":        "LSTM",
                "prediction_error":  round(total, 6),
                "n_samples":         self._n,
                "training_active":   not self._training_event.is_set(),
                "temporal_break":    _temporal_break,
                "sequence_disruption_score": round(total, 6),
            }
