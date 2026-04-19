# backend/vehicle_signal_analyzer.py

import numpy as np

def analyze_vehicle_signals(features, history):

    vib = features.get("vibration_intensity", 0)
    thermal = features.get("thermal", 0)
    acoustic = features.get("acoustic_energy", 0)

    signals = {}

    # 🔥 MICRO VIBRATION INSTABILITY
    if len(history) > 5:
        vib_series = [h.get("vibration_intensity", 0) for h in history]
        signals["vibration_variance"] = float(np.std(vib_series))

    else:
        signals["vibration_variance"] = 0

    # 🔥 THERMAL DRIFT
    if len(history) > 5:
        temps = [h.get("thermal", 0) for h in history]
        trend = np.polyfit(range(len(temps)), temps, 1)[0]
        signals["thermal_trend"] = float(trend)
    else:
        signals["thermal_trend"] = 0

    # 🔥 ACOUSTIC SPIKE DETECTION
    signals["acoustic_spike"] = acoustic > 0.85

    # 🔥 COMBINED RISK SIGNAL
    signals["latent_instability"] = (
        signals["vibration_variance"] > 0.15 and
        signals["thermal_trend"] > 0.02
    )

    return signals
