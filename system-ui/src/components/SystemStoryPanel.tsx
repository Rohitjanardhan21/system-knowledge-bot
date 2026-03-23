export default function SystemStoryPanel({ data }: any) {
  const { posture } = data;

  let color =
    posture === "critical"
      ? "#ef4444"
      : posture === "stressed"
      ? "#f59e0b"
      : "#22c55e";

  return (
    <div className="glass" style={{
      padding: 20,
      borderRadius: 16,
      marginTop: 20,
      borderLeft: `4px solid ${color}`
    }}>
      <h3>🧠 System Story</h3>

      <p style={{
        lineHeight: 1.6,
        opacity: 0.9
      }}>
        {data.explanation}
      </p>
    </div>
  );
}
