"""
pipeline/decision.py  —  CVIS v5.0  (final)
────────────────────────────────────────────
Layer 1 — Probabilistic Decision Engine

Replaces rule-based if/else with multi-factor weighted scoring:

  composite = Σ(wᵢ × sigmoid(kᵢ × (xᵢ − θᵢ))) / Σwᵢ

  Where for each risk factor i:
    wᵢ = importance weight
    kᵢ = sigmoid steepness (sensitivity around threshold)
    θᵢ = activation centre (normalised [0,1])

Action mapping:
  composite → sorted threshold table → action label

Bayesian confidence:
  confidence = 1 − (anomaly_uncertainty + boundary_uncertainty
                     + signal_disagreement)

Fix 4 — Hysteresis:
  Without hysteresis the system flickers at decision boundaries.
  For example, composite oscillating between 0.54 and 0.56 around
  the 0.55 STEER_CORRECT threshold causes repeated label changes.

  Solution: if |new_composite - prev_composite| < HYSTERESIS_BAND
  AND the action hasn't changed for fewer than MIN_HOLD_FRAMES,
  hold the previous decision unchanged.

  Implementation:
    self._prev_composite  — last accepted composite score
    self._prev_action     — last accepted action
    self._hold_frames     — frames since last action change
    HYSTERESIS_BAND = 0.05  — dead-band width around last score
    MIN_HOLD_FRAMES = 3     — minimum frames before allowing change

  This means: a new action is only accepted if EITHER:
    (a) the score has moved by more than 0.05 from the last
        accepted score (large enough to be a real change), OR
    (b) we have already held the current action for at least
        3 consecutive frames AND the new score differs by ≥0.05
        from the current accepted score.
"""

import logging
import math
import time
from typing import Any

log = logging.getLogger("cvis.decision")


def _sigmoid(x: float, k: float = 6.0, offset: float = 0.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * (x - offset)))


# ── Action catalogue ──────────────────────────────────────────
ACTIONS = {
    "AUTO_BRAKE":    {"label":"AUTO BRAKE",    "color":"#ff1e40","urgency":"CRITICAL","icon":"⚡"},
    "STEER_CORRECT": {"label":"STEER CORRECT", "color":"#ff9500","urgency":"HIGH",    "icon":"↔"},
    "REDUCE_SPEED":  {"label":"REDUCE SPEED",  "color":"#ff9500","urgency":"HIGH",    "icon":"⬇"},
    "ALERT_DRIVER":  {"label":"ALERT DRIVER",  "color":"#e8a800","urgency":"MEDIUM",  "icon":"⚠"},
    "INCREASE_DIST": {"label":"INCREASE DIST", "color":"#e8a800","urgency":"MEDIUM",  "icon":"↕"},
    "LANE_KEEP":     {"label":"LANE KEEP",     "color":"#00c8ff","urgency":"LOW",     "icon":"◈"},
    "MAINTAIN":      {"label":"MAINTAIN",      "color":"#00e87a","urgency":"NOMINAL", "icon":"✓"},
}

# ── Risk factors: (weight, sigmoid_k, activation_centre_θ) ───
# anomaly weight raised from 0.05 → 0.10 to fully leverage the ML ensemble
RISK_FACTORS: dict[str, tuple[float, float, float]] = {
    "hazard":         (0.30, 10.0, 0.55),
    "ttc":            (0.25, 12.0, 0.60),
    "lane_offset":    (0.12,  8.0, 0.40),
    "speed_excess":   (0.10,  6.0, 0.50),
    "following_dist": (0.08,  8.0, 0.55),
    "fatigue":        (0.07,  6.0, 0.50),
    "anomaly":        (0.10,  6.0, 0.45),   # doubled — ML stack now has full weight
    "brake_hard":     (0.02,  8.0, 0.60),
    "vibration":      (0.01,  5.0, 0.55),
}
TOTAL_WEIGHT = sum(w for w, _, _ in RISK_FACTORS.values())

# ── Action thresholds (composite → action) ────────────────────
ACTION_THRESHOLDS = [
    (0.82, "AUTO_BRAKE"),
    (0.68, "REDUCE_SPEED"),
    (0.55, "STEER_CORRECT"),
    (0.42, "INCREASE_DIST"),
    (0.30, "ALERT_DRIVER"),
    (0.18, "LANE_KEEP"),
    (0.00, "MAINTAIN"),
]

# ── Fix 4 hysteresis parameters ───────────────────────────────
HYSTERESIS_BAND  = 0.05   # dead-band: ignore changes smaller than this
MIN_HOLD_FRAMES  = 3      # hold current action at least this many frames


class ProbabilisticDecisionEngine:
    """
    Multi-factor scoring-based autonomous decision engine.

    All risk signals are evaluated simultaneously via weighted sigmoid
    activation, producing a single composite score that maps to an
    action via a threshold table.

    Ensemble intelligence integration:
      • uncertainty  (model disagreement) → widens composite upward
      • model_confidence                 → smooths composite
      • trend        (memory slope)      → scales composite by momentum

    Hysteresis (Fix 4) prevents flickering at action boundaries.
    Confidence-aware guard: avoids aggressive actions when model
    confidence is low (< 0.4).
    """

    def __init__(self):
        self._history: list[dict] = []
        self._start_time = time.time()

        # Fix 4: hysteresis state
        self._prev_composite:  float = 0.0
        self._prev_action:     str   = "MAINTAIN"
        self._hold_frames:     int   = 0

    # ── Main entry ────────────────────────────────────────────

    def decide(self, inp: dict) -> dict:
        """
        Compute a decision for the current sensor+vision snapshot.

        inp keys (all optional — safe defaults applied):
          hazard, objects, lane_offset, speed, speed_limit,
          following_dist, driver_fatigue_level, anomaly_score,
          brake_pressure, vibration, failsafe_mode,
          uncertainty, model_confidence, trend
        """
        fs_mode = inp.get("failsafe_mode", "NORMAL")
        if fs_mode == "EMERGENCY":
            return self._emergency_response(inp)

        # 1. Extract & normalise risk factors
        factors          = self._extract_factors(inp)

        # 2. Compute weighted sigmoid composite score
        component_scores = self._score_components(factors)
        composite        = sum(component_scores.values()) / TOTAL_WEIGHT

        # 3. Apply failsafe penalty
        if fs_mode == "SAFE_MODE":
            composite = min(1.0, composite + 0.12)

        # 4. Ensemble intelligence scaling
        #    a. Uncertainty penalty: high model disagreement → push composite
        #       upward so the system is more cautious when models don't agree.
        #    b. Confidence smoothing: high model confidence allows the score
        #       to relax slightly (models agree it's safe → trust them).
        #    c. Trend amplification: a rising anomaly trend from memory
        #       multiplies composite by momentum — sustained signals escalate.
        uncertainty  = float(inp.get("uncertainty",      0.0))
        model_conf   = float(inp.get("model_confidence", 1.0))
        trend        = float(inp.get("trend",            0.0))

        composite = composite * (1.0 + uncertainty * 0.3)
        composite = composite * (1.0 - (model_conf - 0.5) * 0.2)
        composite = composite * (1.0 + max(0.0, trend) * 0.5)

        # 5. TTC anticipation boost: imminent collision raises composite
        #    directly so AUTO_BRAKE triggers faster than the factor table alone.
        ttc = self._compute_ttc(inp)
        if ttc is not None and ttc < 3.0:
            composite += 0.15

        composite = min(1.0, composite)

        # 6. Map to action
        raw_action = self._map_action(composite)

        # 7. Confidence-aware guard: under high uncertainty (model_conf < 0.4),
        #    suppress aggressive actions beyond ALERT_DRIVER to avoid acting
        #    on noise. CRITICAL upgrades (AUTO_BRAKE) always pass through.
        if model_conf < 0.4 and ACTIONS[raw_action]["urgency"] not in ("CRITICAL", "NOMINAL"):
            raw_action = "ALERT_DRIVER"
            log.debug(f"Confidence-aware guard: action downgraded to ALERT_DRIVER (conf={model_conf:.2f})")

        # ── Fix 4: Hysteresis gate ────────────────────────────
        action, composite = self._apply_hysteresis(raw_action, composite)

        # 8. Bayesian confidence
        confidence = self._bayesian_confidence(component_scores, composite,
                                               inp.get("anomaly_score", 0))

        # 9. Reasoning chain + advisories
        chain, advisories = self._build_reasoning(
            action, factors, component_scores, composite,
            confidence, ttc, fs_mode, inp,
        )

        result = {
            "action":           action,
            "composite_score":  round(composite, 4),
            "confidence":       round(confidence, 4),
            "ttc":              ttc,
            "urgency":          ACTIONS[action]["urgency"],
            "color":            ACTIONS[action]["color"],
            "icon":             ACTIONS[action]["icon"],
            "label":            ACTIONS[action]["label"],
            "reasoning_chain":  chain,
            "advisories":       advisories,
            "component_scores": {k: round(v, 4) for k, v in component_scores.items()},
            "hysteresis_held":  action == self._prev_action and self._hold_frames > 1,
            "timestamp":        time.strftime("%H:%M:%S", time.localtime()),
        }

        self._history.append({"ts": time.time(), "action": action, "score": composite})
        if len(self._history) > 200:
            self._history = self._history[-200:]

        return result

    # ── Fix 4: Hysteresis ─────────────────────────────────────

    def _apply_hysteresis(self, raw_action: str, composite: float) -> tuple[str, float]:
        """
        Dead-band hysteresis to prevent decision flickering.

        Accept the new action only if the composite score has moved
        more than HYSTERESIS_BAND from the last accepted score.
        Otherwise hold the previous action and score unchanged.

        Exception: EMERGENCY / CRITICAL upgrades always pass through
        immediately (safety guarantee — never suppress braking).
        """
        is_critical_upgrade = (
            ACTIONS[raw_action]["urgency"] == "CRITICAL" and
            ACTIONS[self._prev_action]["urgency"] != "CRITICAL"
        )

        score_delta = abs(composite - self._prev_composite)
        change_allowed = (
            is_critical_upgrade
            or score_delta >= HYSTERESIS_BAND
            or self._hold_frames >= MIN_HOLD_FRAMES
        )

        if change_allowed and raw_action != self._prev_action:
            self._prev_composite = composite
            self._prev_action    = raw_action
            self._hold_frames    = 1
            return raw_action, composite
        elif change_allowed and raw_action == self._prev_action:
            self._prev_composite = composite
            self._hold_frames   += 1
            return raw_action, composite
        else:
            # Hold previous — score hasn't moved enough
            self._hold_frames += 1
            return self._prev_action, self._prev_composite

    # ── Factor extraction ─────────────────────────────────────

    def _extract_factors(self, inp: dict) -> dict[str, float]:
        speed       = float(inp.get("speed",          0))
        speed_limit = float(inp.get("speed_limit",   70) or 70)
        hazard      = float(inp.get("hazard",          0))
        lane_off    = abs(float(inp.get("lane_offset", 0)))
        fol_dist    = float(inp.get("following_dist", 3.0) or 3.0)
        fatigue     = float(inp.get("fatigue_level",   0) or
                            inp.get("driver_fatigue_level", 0))
        anomaly     = float(inp.get("anomaly_score",   0))
        brake       = float(inp.get("brake_pressure",  0))
        vibration   = float(inp.get("vibration",       0))

        ttc_val  = self._compute_ttc(inp)
        ttc_norm = (1 - min(ttc_val, 8) / 8) if ttc_val is not None else 0.0

        return {
            "hazard":         hazard,
            "ttc":            ttc_norm,
            "lane_offset":    min(lane_off, 1.0),
            "speed_excess":   max(0, speed / speed_limit - 1),
            "following_dist": max(0, 1 - fol_dist / 5),
            "fatigue":        min(fatigue, 1.0),
            "anomaly":        anomaly,
            "brake_hard":     min(brake / 100, 1.0),
            "vibration":      min(vibration / 60, 1.0),
        }

    # ── Weighted sigmoid scoring ──────────────────────────────

    def _score_components(self, factors: dict[str, float]) -> dict[str, float]:
        return {
            key: w * _sigmoid(factors.get(key, 0), k, theta)
            for key, (w, k, theta) in RISK_FACTORS.items()
        }

    def _map_action(self, composite: float) -> str:
        for threshold, action in ACTION_THRESHOLDS:
            if composite >= threshold:
                return action
        return "MAINTAIN"

    # ── Bayesian confidence ───────────────────────────────────

    def _bayesian_confidence(
        self,
        component_scores: dict[str, float],
        composite: float,
        anomaly: float,
    ) -> float:
        anom_unc     = anomaly * 0.25
        min_dist     = min(abs(composite - t) for t, _ in ACTION_THRESHOLDS)
        boundary_unc = max(0, 0.15 - min_dist * 0.5)
        norm_scores  = [v / w for key, (w, _, _) in RISK_FACTORS.items()
                        if (v := component_scores.get(key, 0)) > 0]
        if norm_scores:
            mean_s      = sum(norm_scores) / len(norm_scores)
            variance    = sum((s - mean_s)**2 for s in norm_scores) / len(norm_scores)
            disagree_unc = min(0.2, math.sqrt(variance) * 0.4)
        else:
            disagree_unc = 0.0
        uncertainty = anom_unc + boundary_unc + disagree_unc
        return max(0.40, min(0.99, 1.0 - uncertainty))

    # ── TTC ───────────────────────────────────────────────────

    def _compute_ttc(self, inp: dict) -> float | None:
        objects = inp.get("objects", [])
        speed   = float(inp.get("speed", 0))
        if not objects:
            return None
        closest = min(objects, key=lambda o: o.get("distance", 99))
        dist    = closest.get("distance", 99)
        vy      = closest.get("vy", 0)
        closing = abs(vy) * 0.05 + speed * 0.44 * 0.05
        if closing < 0.01:
            return None
        return round(min(dist / closing, 60.0), 2)

    # ── Reasoning chain ───────────────────────────────────────

    def _build_reasoning(
        self, action, factors, scores, composite,
        confidence, ttc, fs_mode, inp,
    ) -> tuple[list[str], list[dict]]:
        chain = []
        top   = sorted(scores.items(), key=lambda x: -x[1])[:3]
        top_s = " + ".join(f"{k}({v:.2f})" for k, v in top)

        uncertainty = float(inp.get("uncertainty", 0))
        model_conf  = float(inp.get("model_confidence", 1.0))
        trend       = float(inp.get("trend", 0))

        chain.append(f"Risk factors → {top_s}")
        chain.append(
            f"Composite → {composite:.3f} "
            f"[w·sigmoid, Σw={TOTAL_WEIGHT:.1f}]"
        )
        chain.append(
            f"Ensemble scaling → uncertainty={uncertainty:.2f} "
            f"conf={model_conf:.2f} trend={trend:+.3f}"
        )
        threshold = [t for t, a in ACTION_THRESHOLDS if a == action]
        chain.append(
            f"Threshold → {composite:.2f} ≥ "
            f"{threshold[0] if threshold else '?':.2f} → {action}"
        )
        chain.append(
            f"Hysteresis gate → Δ={abs(composite-self._prev_composite):.3f} "
            f"(band={HYSTERESIS_BAND})"
        )
        chain.append(
            f"Bayesian confidence → {confidence*100:.1f}% "
            f"(anomaly={factors.get('anomaly',0):.2f})"
        )
        if model_conf < 0.4:
            chain.append(f"Confidence guard ACTIVE → model_conf={model_conf:.2f} < 0.4")
        if ttc is not None:
            chain.append(
                f"TTC → {ttc:.1f}s"
                f"{' ⚠ CRITICAL' if ttc < 2.5 else ''}"
            )
        if fs_mode != "NORMAL":
            chain.append(f"Failsafe → {fs_mode}")

        advisories = []
        if factors.get("hazard", 0) > 0.75:
            advisories.append({"text": f"HAZARD CRITICAL — {factors['hazard']*100:.0f}%", "sev":"CRITICAL"})
        if factors.get("fatigue", 0) > 0.55:
            advisories.append({"text": "DRIVER FATIGUE — Rest recommended", "sev":"WARNING"})
        if factors.get("lane_offset", 0) > 0.4:
            advisories.append({"text": "LANE DEPARTURE — Correction applied", "sev":"WARNING"})
        speed    = float(inp.get("speed", 0))
        sl       = float(inp.get("speed_limit", 70) or 70)
        if speed > sl * 1.1:
            advisories.append({"text": f"SPEED — {speed:.0f}/{sl:.0f} mph", "sev":"CAUTION"})
        if ttc is not None and ttc < 3.0:
            advisories.append({"text": f"COLLISION IMMINENT — TTC={ttc:.1f}s", "sev":"CRITICAL"})
        if uncertainty > 0.4:
            advisories.append({"text": f"MODEL DISAGREEMENT — uncertainty={uncertainty:.2f}", "sev":"WARNING"})

        return chain, advisories

    # ── Emergency override ────────────────────────────────────

    def _emergency_response(self, inp: dict) -> dict:
        self._prev_action = "AUTO_BRAKE"
        self._hold_frames = 999
        return {
            "action":           "AUTO_BRAKE",
            "composite_score":  1.0,
            "confidence":       0.99,
            "ttc":              self._compute_ttc(inp),
            "urgency":          "CRITICAL",
            **ACTIONS["AUTO_BRAKE"],
            "reasoning_chain":  [
                "FAILSAFE EMERGENCY MODE ACTIVE",
                "All non-safety computations bypassed",
                "Immediate braking command issued",
                "Hysteresis: disabled for emergency",
            ],
            "advisories":       [
                {"text": "⚠ EMERGENCY — Human intervention required", "sev":"CRITICAL"}
            ],
            "component_scores": {},
            "hysteresis_held":  False,
            "timestamp":        time.strftime("%H:%M:%S", time.localtime()),
        }
