"""
CVIS v9 — ML Engine
Real PyTorch: 2-layer LSTM with BPTT + β-VAE (5→16→8→4→8→16→5)
Fallback: numpy implementations when PyTorch absent
sklearn Isolation Forest (100 estimators)
"""
import logging
import numpy as np
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger("cvis.ml")

# ─────────────────────────────────────────────────────────
#  PyTorch optional import
# ─────────────────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.optim import Adam
    from torch.optim.lr_scheduler import ReduceLROnPlateau
    TORCH_OK = True
    log.info("PyTorch %s available", torch.__version__)
except ImportError:
    TORCH_OK = False
    log.warning("PyTorch not found — using numpy fallback models")

try:
    from sklearn.ensemble import IsolationForest as _IF
    from sklearn.preprocessing import RobustScaler
    SK_OK = True
except ImportError:
    SK_OK = False

# ─────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────
SEQ_LEN      = 20     # LSTM sequence length
FEAT_DIM     = 5      # [cpu/100, mem/100, disk/100, net/100, ano]
LATENT_DIM   = 4      # VAE latent space
LSTM_HIDDEN  = 64
LSTM_LAYERS  = 2
LSTM_DROPOUT = 0.2
VAE_BETA     = 0.5    # β-VAE weight on KL term
REPLAY_SIZE  = 512    # experience replay buffer
BATCH_SIZE   = 32
GRAD_CLIP    = 1.0    # gradient clipping
LR           = 1e-3

# ─────────────────────────────────────────────────────────
#  PYTORCH MODELS
# ─────────────────────────────────────────────────────────
if TORCH_OK:

    class MultivariateLSTMNet(nn.Module):
        """
        2-layer LSTM with LayerNorm + 2-layer FC head.
        Input : (batch, seq_len, FEAT_DIM)
        Output: (batch, FEAT_DIM)  — predicts next timestep
        """
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(
                FEAT_DIM, LSTM_HIDDEN, LSTM_LAYERS,
                batch_first=True,
                dropout=LSTM_DROPOUT if LSTM_LAYERS > 1 else 0.0,
            )
            self.ln   = nn.LayerNorm(LSTM_HIDDEN)
            self.head = nn.Sequential(
                nn.Linear(LSTM_HIDDEN, 32),
                nn.GELU(),
                nn.Dropout(0.1),
                nn.Linear(32, FEAT_DIM),
            )

        def forward(self, x, hidden=None):
            out, hidden = self.lstm(x, hidden)
            out = self.ln(out[:, -1, :])   # last timestep
            return self.head(out), hidden

    class VariationalAutoencoderNet(nn.Module):
        """
        β-VAE: 5 → 16 → 8 → μ,σ(4) → reparameterise → 8 → 16 → 5
        Anomaly score = reconstruction_error + β × KL_divergence
        """
        def __init__(self):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(FEAT_DIM, 16), nn.BatchNorm1d(16), nn.LeakyReLU(0.2),
                nn.Linear(16, 8),        nn.BatchNorm1d(8),  nn.LeakyReLU(0.2),
            )
            self.fc_mu     = nn.Linear(8, LATENT_DIM)
            self.fc_logvar = nn.Linear(8, LATENT_DIM)
            self.decoder = nn.Sequential(
                nn.Linear(LATENT_DIM, 8),  nn.BatchNorm1d(8),  nn.LeakyReLU(0.2),
                nn.Linear(8, 16),          nn.BatchNorm1d(16), nn.LeakyReLU(0.2),
                nn.Linear(16, FEAT_DIM),   nn.Sigmoid(),
            )

        def encode(self, x):
            h = self.encoder(x)
            return self.fc_mu(h), self.fc_logvar(h)

        def reparameterise(self, mu, logvar):
            if self.training:
                std = torch.exp(0.5 * logvar).clamp(max=5.0)
                return mu + std * torch.randn_like(std)
            return mu

        def decode(self, z):
            return self.decoder(z)

        def forward(self, x):
            mu, logvar = self.encode(x)
            z = self.reparameterise(mu, logvar)
            return self.decode(z), mu, logvar

        def loss(self, x, recon, mu, logvar):
            recon_l = F.mse_loss(recon, x, reduction="sum") / x.size(0)
            kl_l    = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).sum(dim=1).mean()
            total   = recon_l + VAE_BETA * kl_l
            return total, recon_l.item(), kl_l.item()

        @torch.no_grad()
        def anomaly_score(self, x_np: np.ndarray) -> float:
            self.eval()
            x = torch.tensor(x_np, dtype=torch.float32).unsqueeze(0)
            recon, mu, logvar = self(x)
            err  = F.mse_loss(recon, x, reduction="sum").item()
            kl   = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).sum().item()
            return float(min(1.0, (err + VAE_BETA * max(0, kl)) / 5.0))

        @torch.no_grad()
        def latent(self, x_np: np.ndarray):
            self.eval()
            x = torch.tensor(x_np, dtype=torch.float32).unsqueeze(0)
            mu, logvar = self.encode(x)
            return mu.squeeze().tolist(), logvar.squeeze().tolist()

        @torch.no_grad()
        def feature_errors(self, x_np: np.ndarray):
            self.eval()
            x = torch.tensor(x_np, dtype=torch.float32).unsqueeze(0)
            recon, _, _ = self(x)
            return (recon - x).abs().squeeze().tolist()

# ─────────────────────────────────────────────────────────
#  NUMPY FALLBACK MODELS
# ─────────────────────────────────────────────────────────
class _NumpyLSTMFallback:
    """Minimal numpy LSTM — single-cell, EMA-based prediction."""
    def __init__(self):
        self.steps = 0; self.loss_hist = deque(maxlen=50)
        self.last_err = 1.0; self.h = np.zeros(FEAT_DIM)

    def train_step(self, seq, target):
        pred = seq[-1] * 0.7 + seq[-2] * 0.3 if len(seq) >= 2 else seq[-1]
        err = np.mean((pred - target) ** 2)
        self.last_err = float(np.sqrt(err)); self.loss_hist.append(self.last_err)
        self.steps += 1; return self.last_err

    def predict(self, seq):
        if len(seq) < 2: return seq[-1]
        return seq[-1] * 0.6 + seq[-2] * 0.25 + seq[-3] * 0.15 if len(seq) >= 3 else seq[-1]

    def anomaly_score(self, seq, target):
        return float(min(1.0, self.last_err * 4))

    def state_dict(self): return {"steps": self.steps}

class _NumpyVAEFallback:
    """MSE autoencoder via numpy SGD — 5→3→5."""
    def __init__(self):
        self.steps = 0; self.last_recon_loss = 1.0; self.last_kl_loss = 0.0
        self.W1 = np.random.randn(FEAT_DIM, 3) * 0.1
        self.W2 = np.random.randn(3, FEAT_DIM) * 0.1
        self.feat_errors = np.zeros(FEAT_DIM)

    def _sig(self, x): return 1 / (1 + np.exp(-np.clip(x, -20, 20)))

    def train_step(self, x, lr=0.015):
        h  = self._sig(x @ self.W1)
        xh = self._sig(h @ self.W2)
        d2 = 2 * (xh - x) / FEAT_DIM * xh * (1 - xh)
        self.W2 -= lr * h.reshape(-1, 1) @ d2.reshape(1, -1)
        d1 = (d2 @ self.W2.T) * h * (1 - h)
        self.W1 -= lr * x.reshape(-1, 1) @ d1.reshape(1, -1)
        self.feat_errors = np.abs(xh - x)
        loss = float(np.mean((xh - x) ** 2))
        self.last_recon_loss = loss; self.steps += 1; return loss, 0.0

    def anomaly_score(self, x):
        h  = self._sig(x @ self.W1)
        xh = self._sig(h @ self.W2)
        return float(min(1.0, np.mean((xh - x) ** 2) * 20))

    def latent(self, x): return [0.0]*LATENT_DIM, [0.0]*LATENT_DIM

    def feature_errors(self, x):
        h  = self._sig(x @ self.W1)
        xh = self._sig(h @ self.W2)
        return (np.abs(xh - x)).tolist()

    def state_dict(self): return {"W1": self.W1.tolist(), "W2": self.W2.tolist()}

# ─────────────────────────────────────────────────────────
#  TRAINING STATE
# ─────────────────────────────────────────────────────────
@dataclass
class TrainingMetrics:
    steps_lstm: int = 0
    steps_vae:  int = 0
    steps_if:   int = 0
    lstm_loss:  float = 1.0
    vae_recon_loss: float = 1.0
    vae_kl_loss:    float = 0.0
    if_score:   float = 0.0
    lstm_score: float = 0.0
    vae_score:  float = 0.0
    ensemble_score: float = 0.0
    model_fitted: bool = False
    backend: str = "torch" if TORCH_OK else "numpy"
    latent_mu:    list = field(default_factory=lambda: [0.0]*LATENT_DIM)
    latent_logvar: list = field(default_factory=lambda: [0.0]*LATENT_DIM)
    feat_errors:  list = field(default_factory=lambda: [0.0]*FEAT_DIM)
    lstm_loss_hist: list = field(default_factory=list)
    vae_loss_hist:  list = field(default_factory=list)
    lstm_trend: str = "→"

# ─────────────────────────────────────────────────────────
#  MAIN ML ENGINE
# ─────────────────────────────────────────────────────────
class MLEngine:
    def __init__(self):
        # Build models
        if TORCH_OK:
            self.lstm_net = MultivariateLSTMNet()
            self.vae_net  = VariationalAutoencoderNet()
            self.lstm_opt = Adam(self.lstm_net.parameters(), lr=LR)
            self.vae_opt  = Adam(self.vae_net.parameters(),  lr=LR)
            self.lstm_sched = ReduceLROnPlateau(self.lstm_opt, patience=20, factor=0.5)
            self.vae_sched  = ReduceLROnPlateau(self.vae_opt,  patience=20, factor=0.5)
        else:
            self.lstm_net = _NumpyLSTMFallback()
            self.vae_net  = _NumpyVAEFallback()

        # sklearn IF
        if SK_OK:
            self.if_model  = _IF(n_estimators=100, contamination=0.08, random_state=42)
            self.if_scaler = RobustScaler()
            self._if_fitted = False
        else:
            self._if_fitted = False

        # Replay buffers
        self.feature_buf: deque = deque(maxlen=REPLAY_SIZE)   # raw np arrays
        self.seq_buf:     deque = deque(maxlen=REPLAY_SIZE)   # (seq, target) pairs
        self.metrics = TrainingMetrics()

        # EMA smoothing
        self._lstm_ema = 0.0
        self._vae_ema  = 0.0
        self._if_ema   = 0.0
        self._tick     = 0

    # ── ingest + train ────────────────────────────────────
    def ingest(self, feat: np.ndarray):
        """Called every tick with a normalised [0,1] feature vector."""
        self.feature_buf.append(feat.copy())
        self._tick += 1

        # Build LSTM sequence pair when buffer has enough history
        if len(self.feature_buf) > SEQ_LEN:
            seq    = np.stack(list(self.feature_buf)[-SEQ_LEN-1:-1])  # (SEQ_LEN, FEAT_DIM)
            target = self.feature_buf[-1]
            self.seq_buf.append((seq, target))

        # Train every 5 ticks
        if self._tick % 5 == 0 and len(self.seq_buf) >= BATCH_SIZE:
            self._train_lstm_batch()
            self._train_vae_batch()

        # Retrain IF every 20 ticks when enough data
        if self._tick % 20 == 0 and len(self.feature_buf) >= 60 and SK_OK:
            self._fit_isolation_forest()

    def _train_lstm_batch(self):
        idx   = np.random.choice(len(self.seq_buf), BATCH_SIZE, replace=True)
        pairs = [self.seq_buf[i] for i in idx]

        if TORCH_OK:
            self.lstm_net.train()
            seqs    = torch.tensor(np.stack([p[0] for p in pairs]), dtype=torch.float32)
            targets = torch.tensor(np.stack([p[1] for p in pairs]), dtype=torch.float32)
            preds, _ = self.lstm_net(seqs)
            loss = F.mse_loss(preds, targets)
            self.lstm_opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.lstm_net.parameters(), GRAD_CLIP)
            self.lstm_opt.step()
            self.lstm_sched.step(loss)
            l = loss.item()
        else:
            seqs    = [p[0] for p in pairs]
            targets = [p[1] for p in pairs]
            l = float(np.mean([self.lstm_net.train_step(s, t) for s, t in zip(seqs, targets)]))

        self.metrics.steps_lstm += BATCH_SIZE
        self.metrics.lstm_loss = l
        self.metrics.lstm_loss_hist.append(round(l, 5))
        if len(self.metrics.lstm_loss_hist) > 60:
            self.metrics.lstm_loss_hist.pop(0)
        # trend
        h = self.metrics.lstm_loss_hist
        if len(h) >= 6:
            d = h[-1] - h[-6]
            self.metrics.lstm_trend = "↓ improving" if d < -0.002 else "↑ degrading" if d > 0.002 else "→ stable"

    def _train_vae_batch(self):
        data = list(self.feature_buf)
        idx  = np.random.choice(len(data), min(BATCH_SIZE, len(data)), replace=True)
        batch = np.stack([data[i] for i in idx])

        if TORCH_OK:
            self.vae_net.train()
            x = torch.tensor(batch, dtype=torch.float32)
            recon, mu, logvar = self.vae_net(x)
            loss, rl, kl = self.vae_net.loss(x, recon, mu, logvar)
            self.vae_opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.vae_net.parameters(), GRAD_CLIP)
            self.vae_opt.step()
            self.vae_sched.step(loss)
            self.metrics.vae_recon_loss = rl
            self.metrics.vae_kl_loss    = kl
            l = loss.item()
        else:
            losses = [self.vae_net.train_step(x) for x in batch]
            self.metrics.vae_recon_loss = float(np.mean([lv[0] for lv in losses]))
            self.metrics.vae_kl_loss    = 0.0
            l = self.metrics.vae_recon_loss

        self.metrics.steps_vae += len(idx)
        self.metrics.vae_loss_hist.append(round(l, 5))
        if len(self.metrics.vae_loss_hist) > 60:
            self.metrics.vae_loss_hist.pop(0)

    def _fit_isolation_forest(self):
        data = np.stack(list(self.feature_buf))
        self.if_scaler.fit(data)
        self.if_model.fit(self.if_scaler.transform(data))
        self._if_fitted = True
        self.metrics.model_fitted = True
        self.metrics.steps_if = len(self.feature_buf)

    # ── score (inference) ─────────────────────────────────
    def score(self, feat: np.ndarray) -> TrainingMetrics:
        """Compute all anomaly scores and update metrics."""
        # IF score
        if SK_OK and self._if_fitted:
            arr = self.if_scaler.transform(feat.reshape(1, -1))
            raw = float(self.if_model.score_samples(arr)[0])
            if_raw = max(0.0, min(1.0, (-raw - 0.1) * 2.0))
        else:
            if_raw = max(0.0, min(1.0, feat[0] * 0.4 + feat[1] * 0.3 + feat[4] * 0.3))

        # VAE score
        if TORCH_OK and self.metrics.steps_vae > 30:
            vae_raw = self.vae_net.anomaly_score(feat)
            self.metrics.latent_mu, self.metrics.latent_logvar = self.vae_net.latent(feat)
            self.metrics.feat_errors = self.vae_net.feature_errors(feat)
        else:
            vae_raw = self.vae_net.anomaly_score(feat)
            self.metrics.latent_mu, self.metrics.latent_logvar = self.vae_net.latent(feat)
            self.metrics.feat_errors = self.vae_net.feature_errors(feat)

        # LSTM score
        if TORCH_OK and self.metrics.steps_lstm > 20 and len(self.feature_buf) >= SEQ_LEN:
            self.lstm_net.eval()
            seq = torch.tensor(
                np.stack(list(self.feature_buf)[-SEQ_LEN:]),
                dtype=torch.float32
            ).unsqueeze(0)
            with torch.no_grad():
                pred, _ = self.lstm_net(seq)
            err = float(F.mse_loss(pred.squeeze(), torch.tensor(feat, dtype=torch.float32)))
            lstm_raw = min(1.0, err * 10)
        elif len(self.feature_buf) >= 2:
            lstm_raw = 0.0
        else:
            lstm_raw = 0.0

        # EMA smoothing — explicit float() cast ensures numpy scalars from
        # feature vector arithmetic don't propagate as numpy types.
        a = 0.3
        self._if_ema   = float(a * float(if_raw)   + (1 - a) * self._if_ema)
        self._vae_ema  = float(a * float(vae_raw)  + (1 - a) * self._vae_ema)
        self._lstm_ema = float(a * float(lstm_raw) + (1 - a) * self._lstm_ema)

        ens = self._if_ema * 0.40 + self._vae_ema * 0.35 + self._lstm_ema * 0.25

        self.metrics.if_score       = round(float(self._if_ema),   4)
        self.metrics.lstm_score     = round(float(self._lstm_ema), 4)
        self.metrics.vae_score      = round(float(self._vae_ema),  4)
        self.metrics.ensemble_score = round(float(ens),            4)
        return self.metrics

    # ── state dict (for versioning) ───────────────────────
    def state_dict(self) -> dict:
        if TORCH_OK:
            return {
                "lstm": {k: v.cpu().numpy().tolist() for k, v in self.lstm_net.state_dict().items()},
                "vae":  {k: v.cpu().numpy().tolist() for k, v in self.vae_net.state_dict().items()},
                "metrics": asdict(self.metrics),
            }
        return {"lstm": self.lstm_net.state_dict(), "vae": self.vae_net.state_dict(), "metrics": asdict(self.metrics)}

    def load_state_dict(self, state: dict):
        if TORCH_OK and "lstm" in state:
            self.lstm_net.load_state_dict(
                {k: torch.tensor(np.array(v)) for k, v in state["lstm"].items()}
            )
            self.vae_net.load_state_dict(
                {k: torch.tensor(np.array(v)) for k, v in state["vae"].items()}
            )
        if "metrics" in state:
            for k, v in state["metrics"].items():
                if hasattr(self.metrics, k):
                    setattr(self.metrics, k, v)


# singleton
_engine: Optional[MLEngine] = None

def get_engine() -> MLEngine:
    global _engine
    if _engine is None:
        _engine = MLEngine()
    return _engine
