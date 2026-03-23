export default function DigitalTwinPanel({ data }: any) {
  const { temporal, forecast, posture, cpu } = data;

  const cpuTrend = temporal?.cpu?.pattern;
  const risk = forecast?.risk_score || 0;

  let simulation = "";

  // 🔥 Simulation override logic (highest priority)
  if (cpu > 85) {
    simulation = "Simulated load indicates the system will soon enter a critical state due to high CPU usage.";
  } else if (cpu > 70) {
    simulation = "System is under increasing load and performance degradation is likely.";
  } else {
    // 🔮 Default predictive logic
    if (risk > 0.85) {
      simulation = "System is likely to reach a critical state very soon if no action is taken.";
    } else if (risk > 0.6) {
      simulation = "System performance is expected to degrade within a few minutes.";
    } else if (cpuTrend === "gradual_increase") {
      simulation = "CPU load is increasing steadily and may lead to future performance issues.";
    } else {
      simulation = "System is expected to remain stable under current conditions.";
    }
  }

  return (
    <div style={{
      background: "#111827",
      padding: 20,
      borderRadius: 12,
      marginTop: 20,
      border: "1px solid #374151"
    }}>
      <h3>🔮 Digital Twin Simulation</h3>

      <p style={{
        marginTop: 10,
        lineHeight: 1.6,
        fontSize: 15,
        opacity: 0.9
      }}>
        {simulation}
      </p>
    </div>
  );
}
