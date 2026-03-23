export default function CausalPanel({ causal }: any) {
  return (
    <div>
      <h3>🔍 Root Cause Analysis</h3>

      <p style={{ fontWeight: "bold", fontSize: 18 }}>
        {causal.type.replace("_", " ").toUpperCase()}
      </p>

      <p style={{ opacity: 0.8 }}>
        {causal.reason}
      </p>

      <p style={{ fontSize: 12, opacity: 0.6 }}>
        Confidence: {(causal.confidence * 100).toFixed(0)}%
      </p>
    </div>
  );
}
