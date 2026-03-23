export default function DecisionPanel({ decision }: any) {
  const color =
    decision.urgency === "critical"
      ? "red"
      : decision.urgency === "high"
      ? "orange"
      : "lightgreen";

  return (
    <div>
      <h3>⚠️ Recommended Action</h3>

      <p style={{ color, fontWeight: "bold", fontSize: 18 }}>
        {decision.urgency.toUpperCase()}
      </p>

      <p><strong>Action:</strong> {decision.action}</p>
      <p><strong>Time:</strong> {decision.time_window}</p>

      <p style={{ opacity: 0.8 }}>
        {decision.reason}
      </p>
    </div>
  );
}
