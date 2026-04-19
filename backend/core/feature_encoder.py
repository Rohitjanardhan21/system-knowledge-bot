# ---------------------------------------------------------
# 🧠 FEATURE ENCODER (ROBUST + CROSS-SYSTEM READY)
# ---------------------------------------------------------

import numpy as np


# ---------------------------------------------------------
# 🔧 UTILS
# ---------------------------------------------------------
def safe_array(x):
    try:
        arr = np.array(x, dtype=float)
        if np.isnan(arr).any() or np.isinf(arr).any():
            return np.zeros(1)
        return arr
    except:
        return np.zeros(1)


def normalize(value, max_val):
    try:
        v = float(value) / (max_val + 1e-5)
        return float(np.clip(v, 0, 1.5))  # 🔥 prevent explosion
    except:
        return 0.0


# ---------------------------------------------------------
# 🔊 AUDIO FEATURES
# ---------------------------------------------------------
def extract_audio_features(audio):

    audio = safe_array(audio)

    if len(audio) < 2:
        return {
            "acoustic_energy": 0,
            "acoustic_variance": 0,
            "acoustic_peak": 0,
            "acoustic_entropy": 0
        }

    energy = np.mean(audio ** 2)
    variance = np.var(audio)
    peak = np.max(np.abs(audio))

    hist, _ = np.histogram(audio, bins=20)
    prob = hist / (np.sum(hist) + 1e-8)
    prob = prob + 1e-8
    entropy = -np.sum(prob * np.log(prob))

    return {
        "acoustic_energy": normalize(energy, 1),
        "acoustic_variance": normalize(variance, 1),
        "acoustic_peak": normalize(peak, 1),
        "acoustic_entropy": normalize(entropy, 5)
    }


# ---------------------------------------------------------
# 📳 VIBRATION FEATURES
# ---------------------------------------------------------
def extract_vibration_features(vibration):

    vibration = safe_array(vibration)

    if len(vibration) < 2:
        return {
            "vibration_intensity": 0,
            "vibration_variance": 0,
            "vibration_peak": 0
        }

    return {
        "vibration_intensity": normalize(np.mean(np.abs(vibration)), 1),
        "vibration_variance": normalize(np.var(vibration), 1),
        "vibration_peak": normalize(np.max(np.abs(vibration)), 1)
    }


# ---------------------------------------------------------
# 🌡️ THERMAL FEATURES
# ---------------------------------------------------------
def extract_thermal_features(temp):

    try:
        temp = float(temp)
    except:
        temp = 0

    return {
        "thermal": normalize(temp, 100),
        "thermal_high": 1 if temp > 75 else 0,
        "thermal_critical": 1 if temp > 85 else 0
    }


# ---------------------------------------------------------
# ⚡ ELECTRICAL FEATURES
# ---------------------------------------------------------
def extract_electrical_features(current):

    try:
        current = float(current)
    except:
        current = 0

    return {
        "electrical": normalize(current, 100),
        "electrical_spike": 1 if current > 90 else 0
    }


# ---------------------------------------------------------
# 💻 COMPUTE FEATURES
# ---------------------------------------------------------
def extract_compute_features(cpu):

    try:
        cpu = float(cpu)
    except:
        cpu = 0

    return {
        "compute": normalize(cpu, 100),
        "compute_high": 1 if cpu > 70 else 0,
        "compute_critical": 1 if cpu > 90 else 0
    }


# ---------------------------------------------------------
# 🧠 DERIVED FEATURES (SAFE)
# ---------------------------------------------------------
def extract_cross_features(features):

    compute = features.get("compute", 0)
    thermal = features.get("thermal", 0)
    acoustic = features.get("acoustic_energy", 0)
    vibration = features.get("vibration_intensity", 0)

    return {
        "thermal_compute_ratio": thermal / (compute + 1e-5),

        "acoustic_vibration_coupling":
            acoustic * vibration,

        "stress_index":
            (0.4 * compute + 0.3 * thermal + 0.3 * vibration)
    }


# ---------------------------------------------------------
# 🧠 MAIN PIPELINE
# ---------------------------------------------------------
def extract_features(packet):

    signals = packet.get("signals", {}) if isinstance(packet, dict) else {}

    audio = extract_audio_features(signals.get("acoustic", []))
    vibration = extract_vibration_features(signals.get("vibration", []))
    thermal = extract_thermal_features(signals.get("thermal", 0))
    electrical = extract_electrical_features(signals.get("electrical", 0))
    compute = extract_compute_features(signals.get("compute", 0))

    features = {
        **audio,
        **vibration,
        **thermal,
        **electrical,
        **compute
    }

    features.update(extract_cross_features(features))

    return features
