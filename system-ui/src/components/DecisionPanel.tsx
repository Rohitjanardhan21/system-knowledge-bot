import GlassCard from "./GlassCard";
import ConfidenceBar from "./ConfidenceBar";

export default function DecisionPanel({ decision }: any) {
  if (!decision) return null;

  const {
    action = "N/A",
    confidence = 0,
    reason = "No reasoning available",
    executable = false,
  } = decision;

  const handleExecute = async () => {
    try {
      const res = await fetch("http://localhost:8000/execute", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(decision),
      });

      const data = await res.json();
      console.log("Execution Result:", data);
    } catch (err) {
      console.error("Execution failed:", err);
    }
  };

  return (
    <GlassCard>
      <h2 className="text-lg mb-3">Decision Engine</h2>

      {/* Action */}
      <p className="text-blue-400 font-semibold text-base">
        {action}
      </p>

      {/* Reason */}
      <p className="text-xs text-gray-400 mt-1 mb-3">
        {reason}
      </p>

      {/* Confidence Bar */}
      <div className="mb-3">
        <ConfidenceBar value={confidence} />
      </div>

      {/* Execute Button */}
      {executable && (
        <button
          onClick={handleExecute}
          className="mt-2 w-full bg-green-500/20 hover:bg-green-500/30 text-green-300 py-2 rounded-xl text-sm transition"
        >
          Execute Action
        </button>
      )}
    </GlassCard>
  );
}
