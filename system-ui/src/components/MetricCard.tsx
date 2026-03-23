export default function MetricCard({ label, value }: any) {
  let color = "#22c55e"; // green

  if (value > 80) color = "#ef4444";
  else if (value > 60) color = "#f59e0b";

  return (
    <div className="glass" style={{
      padding: 20,
      borderRadius: 16,
      width: 160,
      boxShadow: `0 0 20px ${color}33`
    }}>
      <p style={{ opacity: 0.6 }}>{label}</p>

      <h2 style={{
        color,
        fontSize: 28,
        margin: 0
      }}>
        {value}%
      </h2>
    </div>
  );
}
