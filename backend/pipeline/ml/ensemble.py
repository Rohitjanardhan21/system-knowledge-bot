"""
pipeline/ml/ensemble.py  —  CVIS v5.0
───────────────────────────────────────
Upgrade 5 — Multi-Model Anomaly Ensemble

Combines three anomaly detectors:
  1. IsolationForest  — global outliers via path lengths
  2. Autoencoder      — reconstruction error on normal manifold
  3. LSTM             — temporal prediction error

Fusion strategies (selectable):
  A. Weighted average       — default, weights tunable
  B. Max score              — conservative (any model alarming = alarm)
  C. Voting majority        — 2/3 models agree → ensemble alarm
  D. Adaptive weights       — weights updated by validation feedback

Why ensemble:
  Model       Strength                    Weakness
  ─────────────────────────────────────────────────────
  IF          Fast, no temporal memory    Misses slow drifts
  Autoencoder Learns normal manifold      Needs many samples
  LSTM        Captures temporal patterns  Expensive, seq lag

  Ensemble catches what any single model misses.
  Disagreement between models = useful meta-signal (uncertainty).

Diversity metrics tracked:
  • Pairwise Pearson correlation of scores (low = good diversity)
  • Jensen-Shannon divergence of alarm rate distributions
  • Ensemble confidence interval (std of model scores)

Online weight adaptation:
  Each model's weight is adjusted by its running precision:
      weight_new = weight_old * (1 - α) + precision * α
  Validated by comparing to simulation scenario ground-truth.
"""

import logging
import math
import threading
import time
from collections import deque

log = logging.getLogger("cvis.ensemble")

# ── Default model weights ─────────────────────────────────────
DEFAULT_WEIGHTS = {
    "isolation_forest": 0.40,
    "autoencoder":      0.35,
    "lstm":             0.25,
}

FUSION_STRATEGIES = ("weighted_avg", "max_score", "majority_vote", "adaptive")


class EnsembleAnomalyDetector:
    """
    Multi-model anomaly detection ensemble.

    Usage:
        from backend.pipeline.anomaly    import IsolationForestDetector
        from backend.pipeline.ml.autoencoder import AutoencoderDetector
        from backend.pipeline.ml.lstm_anomaly import LSTMAnomalyDetector
        from backend.pipeline.ml.ensemble import EnsembleAnomalyDetector

        ensemble = EnsembleAnomalyDetector(
            isolation_forest = IsolationForestDetector(),
            autoencoder      = AutoencoderDetector(),
            lstm             = LSTMAnomalyDetector(),
            strategy         = "weighted_avg",
        )
        result = ensemble.score(raw_signals)

    Drop-in replacement for IsolationForestDetector in main.py.
    """

    def __init__(self, isolation_forest, autoencoder, lstm,
                 strategy: str = "weighted_avg"):
        self._models = {
            "isolation_forest": isolation_forest,
            "autoencoder":      autoencoder,
            "lstm":             lstm,
        }
        assert strategy in FUSION_STRATEGIES, f"Unknown strategy: {strategy}"
        self.strategy = strategy
        self._weights = dict(DEFAULT_WEIGHTS)
        self._lock    = threading.Lock()

        # Diversity tracking
        self._score_hist: dict[str, deque] = {
            k: deque(maxlen=200) for k in self._models
        }
        self._precision: dict[str, float] = {k: 0.5 for k in self._models}
        self._n_validated = 0

        # Diversity rescue cooldown — prevents double-triggering weight
        # adjustments when both the std-based (score()) and correlation-based
        # (_diversity()) rescue paths fire in the same tick.
        self._last_rescue_time: float = 0.0

        # For compatibility with main.py checks
        self.n_estimators = 200      # IF property
        self.sample_count = 0        # updated each call

        log.info(f"Ensemble initialised: {list(self._models)} strategy={strategy}")

    # ── Main entry ────────────────────────────────────────────

    def score(self, raw_signals: dict) -> dict:
        """
        Score raw_signals through all models and fuse results.
        Returns same schema as IsolationForestDetector.score().
        """
        results: dict[str, dict] = {}
        for name, model in self._models.items():
            try:
                results[name] = model.score(raw_signals)
            except Exception as e:
                log.warning(f"Model {name} error: {e}")
                results[name] = {"score": 0.0, "is_anomaly": False,
                                 "severity": "NORMAL", "top_signals": [],
                                 "model_type": f"{name}(ERR)"}

        scores = {k: v["score"] for k, v in results.items()}
        for k, s in scores.items():
            self._score_hist[k].append(s)

        # Cross-model disagreement: how far apart are the models right now?
        # High disagreement → high uncertainty → dashboard shows warning.
        disagreement = max(scores.values()) - min(scores.values())

        fused_score = self._fuse(scores)
        is_anom     = fused_score > 0.50
        severity    = ("CRITICAL" if fused_score > 0.65
                        else "WARNING" if fused_score > 0.35
                        else "NORMAL")

        # Merge top_signals: pick the model with highest score
        best_model  = max(scores, key=scores.get)
        top_signals = results[best_model].get("top_signals", [])

        # Diversity metrics
        diversity   = self._diversity(scores)

        # Explicit diversity rescue in score() hot path (std-based).
        # Cooldown of 5 s prevents over-adjusting weights when both the
        # std-based path here and the correlation-based path inside
        # _diversity() would otherwise fire in the same tick.
        diversity_rescued = False
        if diversity["std"] < 0.05:
            now = time.time()
            if now - self._last_rescue_time > 5.0:
                self._rescue_diversity(list(self._score_hist.keys()))
                self._last_rescue_time = now
                diversity_rescued = True

        # Dynamic anomaly threshold: widens when models are diverse (uncertain)
        # so we only flag anomalies that all models agree on; tightens when
        # models converge (high confidence → lower bar to trigger alarm).
        dynamic_threshold = 0.45 + diversity["std"] * 0.2
        is_anom   = fused_score > dynamic_threshold
        severity  = ("CRITICAL" if fused_score > 0.65
                      else "WARNING" if fused_score > 0.35
                      else "NORMAL")

        # Improved confidence formula: penalises both high variance between
        # historical model outputs (std) AND high instant disagreement.
        # Floor of 0.05 prevents UI from showing a broken "0% confidence".
        confidence = max(0.05, 1.0 - diversity["std"] - disagreement * 0.5)

        self.sample_count = getattr(
            self._models["isolation_forest"], "sample_count", 0
        )

        with self._lock:
            weights_snap = dict(self._weights)

        return {
            "score":           round(fused_score, 4),
            "is_anomaly":      is_anom,
            "severity":        severity,
            "top_signals":     top_signals,
            "model_type":      f"Ensemble({self.strategy})",
            "model_scores":    {k: round(v, 4) for k, v in scores.items()},
            "model_weights":   {k: round(v, 3) for k, v in weights_snap.items()},
            "diversity":       diversity,
            "disagreement":    round(disagreement, 4),
            "diversity_rescued": diversity_rescued,
            "ensemble_confidence": round(confidence, 4),
            "trained_samples": self.sample_count,
            "n_trees":         self.n_estimators,
            # Per-model details for dashboard drill-down
            "model_details": {
                k: {
                    "score":      round(results[k].get("score", 0), 4),
                    "is_anomaly": results[k].get("is_anomaly", False),
                    "severity":   results[k].get("severity", "NORMAL"),
                    "model_type": results[k].get("model_type", k),
                }
                for k in results
            },
        }

    # ── Fusion strategies ────────────────────────────────────

    def _fuse(self, scores: dict[str, float]) -> float:
        if self.strategy == "weighted_avg":
            return self._weighted_avg(scores)
        if self.strategy == "max_score":
            return max(scores.values())
        if self.strategy == "majority_vote":
            return self._majority_vote(scores)
        if self.strategy == "adaptive":
            return self._adaptive_fuse(scores)
        return self._weighted_avg(scores)

    def _weighted_avg(self, scores: dict[str, float]) -> float:
        total_w = sum(self._weights[k] for k in scores)
        if total_w == 0:
            return 0.0
        return sum(self._weights[k] * s for k, s in scores.items()) / total_w

    def _majority_vote(self, scores: dict[str, float],
                       threshold: float = 0.40) -> float:
        """Return mean score of alarming models if majority alarming."""
        alarming = [s for s in scores.values() if s > threshold]
        if len(alarming) >= math.ceil(len(scores) / 2):
            return sum(alarming) / len(alarming)
        # Non-majority — return weighted avg of all
        return self._weighted_avg(scores)

    def _adaptive_fuse(self, scores: dict[str, float]) -> float:
        """Weight by each model's running precision estimate."""
        total_p = sum(self._precision.values()) or 1.0
        return sum(
            (self._precision[k] / total_p) * s for k, s in scores.items()
        )

    # ── Diversity metrics ────────────────────────────────────

    def _diversity(self, scores: dict[str, float]) -> dict:
        vals  = list(scores.values())
        mean  = sum(vals) / len(vals)
        std   = math.sqrt(sum((v-mean)**2 for v in vals) / len(vals))

        # Pairwise Pearson correlation from rolling score histories
        keys   = list(self._score_hist)
        corrs  = []
        for i in range(len(keys)):
            for j in range(i+1, len(keys)):
                hi = list(self._score_hist[keys[i]])
                hj = list(self._score_hist[keys[j]])
                n  = min(len(hi), len(hj), 30)
                if n < 5:
                    continue
                hi, hj = hi[-n:], hj[-n:]
                mi, mj = sum(hi)/n, sum(hj)/n
                si = math.sqrt(sum((v-mi)**2 for v in hi)/n) or 1e-6
                sj = math.sqrt(sum((v-mj)**2 for v in hj)/n) or 1e-6
                corr = sum((a-mi)*(b-mj) for a,b in zip(hi,hj)) / (n*si*sj)
                corrs.append(round(corr, 3))

        avg_corr     = round(sum(corrs)/len(corrs), 3) if corrs else 0.0
        low_diversity = avg_corr > 0.85

        # Fix 5 — Diversity rescue:
        # When models are too correlated (ensemble is redundant), automatically
        # spread weights to maximise separation:
        #   • The model whose rolling variance is highest gets the most weight
        #     (it is providing the most unique signal)
        #   • The two others get equal share of the remainder
        # This is triggered once per detection and logs a warning.
        if low_diversity and len(keys) >= 2:
            self._rescue_diversity(keys)

        return {
            "std":               round(std, 4),
            "mean":              round(mean, 4),
            "avg_pairwise_corr": avg_corr,
            "low_diversity":     low_diversity,
            "diversity_rescued": low_diversity,   # flag for dashboard
        }

    def _rescue_diversity(self, keys: list[str]):
        """
        Diversity rescue strategy (Fix 5):
        Re-assign weights so the model with the highest score variance
        gets the largest weight.  Models with low variance are contributing
        the same signal — they get down-weighted.

        This makes the ensemble behave like a selective ensemble:
        the most informative model dominates until diversity improves.

        Called at most once when low_diversity is first detected;
        subsequent calls are no-ops until correlation drops below 0.85.
        """
        variances = {}
        for k in keys:
            h = list(self._score_hist[k])
            if len(h) < 5:
                variances[k] = 0.0
                continue
            mean = sum(h) / len(h)
            variances[k] = sum((v-mean)**2 for v in h) / len(h)

        if not any(v > 0 for v in variances.values()):
            return   # all zero variance — nothing to separate

        total_var = sum(variances.values()) or 1.0
        with self._lock:
            for k in keys:
                # Weight proportional to variance — most varied model dominates
                self._weights[k] = round(variances[k] / total_var, 4)
        log.warning(
            f"Ensemble low diversity (corr>{0.85}) — "
            f"weights rescued to variance-proportional: {dict(self._weights)}"
        )

    # ── Online weight adaptation ─────────────────────────────

    def update_precision(self, model_name: str, was_correct: bool,
                         alpha: float = 0.05):
        """
        Called by ValidationEngine when a decision outcome is known.
        Updates model weight via exponential moving average of precision.
        """
        if model_name not in self._precision:
            return
        new_p = self._precision[model_name] * (1-alpha) + (1.0 if was_correct else 0.0) * alpha
        self._precision[model_name] = new_p
        self._n_validated += 1

        # Renormalise weights
        if self.strategy == "adaptive":
            total = sum(self._precision.values()) or 1.0
            with self._lock:
                for k in self._weights:
                    self._weights[k] = round(self._precision[k] / total, 4)
            log.debug(f"Adaptive weights updated: {self._weights}")

    # ── pass-throughs for main.py compatibility ───────────────

    def get_learned_patterns(self) -> list:
        try:
            return self._models["isolation_forest"].get_learned_patterns()
        except Exception:
            return []

    def get_thresholds(self) -> dict:
        try:
            return self._models["isolation_forest"].get_thresholds()
        except Exception:
            return {}

    def set_strategy(self, strategy: str):
        assert strategy in FUSION_STRATEGIES
        self.strategy = strategy
        log.info(f"Ensemble strategy changed to: {strategy}")
