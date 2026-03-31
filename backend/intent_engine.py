import time
from collections import deque
from statistics import mean


class IntentEngine:
    """
    Cognitive Intent Engine
    -----------------------
    Infers system intent using:
    - Multi-signal inputs (CPU, memory, network, processes)
    - Temporal stability (history tracking)
    - Adaptive baseline learning
    - Anomaly detection
    - Domain-agnostic abstractions
    """

    def __init__(self, history_size=20):
        self.intent_history = deque(maxlen=history_size)
        self.cpu_history = deque(maxlen=50)
        self.last_update = time.time()

    # ─────────────────────────────────────────────
    # ENTRY POINT
    # ─────────────────────────────────────────────
    def detect(self, processes, global_state):
        """
        processes: list of top processes [{name, cpu, memory}]
        global_state: {cpu, memory, network}
        """

        if not processes:
            return self._build_intent("idle", 0.95, "No active workload detected")

        # 🔹 STEP 1: Normalize inputs
        cpu = global_state.get("cpu", 0)
        memory = global_state.get("memory", 0)
        network = global_state.get("network", 0)

        self._update_learning(cpu)

        # 🔹 STEP 2: Extract features
        features = self._extract_features(processes, cpu, memory, network)

        # 🔹 STEP 3: Score intents
        scores = self._score_intents(features)

        # 🔹 STEP 4: Select best intent
        intent_type = max(scores, key=scores.get)
        confidence = scores[intent_type]

        # 🔹 STEP 5: Temporal stabilization
        confidence = self._apply_temporal_smoothing(intent_type, confidence)

        # 🔹 STEP 6: Build explanation
        reason = self._generate_reason(intent_type, features, processes)

        return self._build_intent(intent_type, confidence, reason)

    # ─────────────────────────────────────────────
    # FEATURE EXTRACTION
    # ─────────────────────────────────────────────
    def _extract_features(self, processes, cpu, memory, network):
        top = processes[0]
        name = top.get("name", "").lower()

        return {
            "high_cpu": cpu > 75,
            "moderate_cpu": 40 < cpu <= 75,
            "high_memory": memory > 70,
            "high_network": network > 60,

            # Abstract classification (OS-agnostic)
            "interactive": any(x in name for x in ["chrome", "firefox", "edge"]),
            "compute": any(x in name for x in ["python", "node", "java"]),
            "background": any(x in name for x in ["docker", "system", "service"]),

            "process_count": len(processes),
            "top_cpu": top.get("cpu", 0),

            # Learned baseline comparison
            "anomaly": self._is_anomaly(cpu)
        }

    # ─────────────────────────────────────────────
    # SCORING MODEL (CORE INTELLIGENCE)
    # ─────────────────────────────────────────────
    def _score_intents(self, f):
        scores = {
            "user_interaction": 0.0,
            "development": 0.0,
            "background_processing": 0.0,
            "system_stress": 0.0,
            "anomalous_behavior": 0.0,
        }

        # USER INTERACTION
        if f["interactive"]:
            scores["user_interaction"] += 0.6
        if f["moderate_cpu"]:
            scores["user_interaction"] += 0.2

        # DEVELOPMENT / COMPUTE
        if f["compute"]:
            scores["development"] += 0.7
        if f["high_cpu"]:
            scores["development"] += 0.2

        # BACKGROUND / INFRA
        if f["background"]:
            scores["background_processing"] += 0.6
        if f["high_memory"]:
            scores["background_processing"] += 0.2

        # SYSTEM STRESS
        if f["high_cpu"]:
            scores["system_stress"] += 0.6
        if f["high_memory"]:
            scores["system_stress"] += 0.3

        # ANOMALY (LEARNING-BASED)
        if f["anomaly"]:
            scores["anomalous_behavior"] += 0.8

        return scores

    # ─────────────────────────────────────────────
    # TEMPORAL STABILITY
    # ─────────────────────────────────────────────
    def _apply_temporal_smoothing(self, intent, confidence):
        self.intent_history.append(intent)

        if list(self.intent_history).count(intent) >= 4:
            confidence += 0.05  # stable boost

        return round(min(confidence, 0.98), 2)

    # ─────────────────────────────────────────────
    # LEARNING ENGINE
    # ─────────────────────────────────────────────
    def _update_learning(self, cpu):
        self.cpu_history.append(cpu)

    def _get_baseline(self):
        if len(self.cpu_history) < 5:
            return 50  # fallback
        return mean(self.cpu_history)

    def _is_anomaly(self, cpu):
        baseline = self._get_baseline()
        return cpu > baseline * 1.5

    # ─────────────────────────────────────────────
    # EXPLANATION ENGINE (VERY IMPORTANT)
    # ─────────────────────────────────────────────
    def _generate_reason(self, intent, features, processes):
        top = processes[0]
        name = top.get("name", "unknown")

        if intent == "user_interaction":
            return f"{name} shows interactive usage with moderate load"

        if intent == "development":
            return f"{name} indicates compute-heavy development workload"

        if intent == "background_processing":
            return f"{name} behaving as background/system service"

        if intent == "system_stress":
            return f"High resource usage detected from {name}"

        if intent == "anomalous_behavior":
            return f"Detected deviation from normal baseline behavior"

        return "System operating normally"

    # ─────────────────────────────────────────────
    # OUTPUT FORMAT
    # ─────────────────────────────────────────────
    def _build_intent(self, intent, confidence, reason):
        return {
            "type": intent,
            "confidence": confidence,
            "reason": reason,
            "timestamp": time.time()
        }
