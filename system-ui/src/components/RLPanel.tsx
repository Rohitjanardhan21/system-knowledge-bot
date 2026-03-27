export default function RLPanel({ decision }: any) {
  if (!decision) return null;

  return (
    <div className="glass-card p-4">
      <h2 className="text-lg font-semibold">🧠 RL Learning Signal</h2>

      <p className="text-sm mt-2">
        Selected Action: <strong>{decision.action}</strong>
      </p>

      <p className="text-sm">
        Confidence: {(decision.confidence * 100).toFixed(1)}%
      </p>

      <p className="text-xs text-gray-400 mt-2">
        Policy adapts based on system feedback over time.
      </p>
    </div>
  );
}
