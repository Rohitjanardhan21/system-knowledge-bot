export default function StatusBar({ posture }: any) {
  const color =
    posture === "critical"
      ? "#ef4444"
      : posture === "stressed"
      ? "#f59e0b"
      : "#22c55e";

  return (
    <div style={{
      marginTop: 10,
      marginBottom: 20,
      padding: 10,
      borderRadius: 12,
      background: `${color}22`,
      border: `1px solid ${color}`
    }}>
      <h2 style={{ margin: 0, color }}>
        ● {posture.toUpperCase()}
      </h2>
    </div>
  );
}
