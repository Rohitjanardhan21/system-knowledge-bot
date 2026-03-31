import { useState } from "react";
import ConfidenceBar from "./ConfidenceBar";

/* ─────────────────────────────────────────────
   GlassCard (fallback if not defined globally)
───────────────────────────────────────────── */
const GlassCard = ({ children }: any) => (
  <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-lg">
    {children}
  </div>
);

export default function DecisionPanel({ decision }: any) {
  if (!decision) return null;

  const {
    action = "N/A",
    confidence = 0,
    reason = "No reasoning available",
    explanation = "",
    impact = [],
    alternatives = [],
    risk = "low",
    executable = false,
  } = decision;

  const [confirm, setConfirm] = useState(false);
  const [status, setStatus] = useState<"idle" | "executing" | "success" | "error">("idle");

  const handleExecute = async () => {
    try {
      setStatus("executing");

      const res = await fetch("http://localhost:8000/execute", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(decision),
      });

      const data = await res.json();
      console.log("Execution Result:", data);

      setStatus("success");
      setTimeout(() => setStatus("idle"), 3000);
    } catch (err) {
      console.error("Execution failed:", err);
      setStatus("error");
    }
  };

  return (
    <GlassCard>
      <h2 className="text-lg mb-4 font-semibold text-white">
        Decision Engine
      </h2>

      {/* ACTION */}
      <div className="mb-3">
        <div className="text-xs text-gray-400">Recommended Action</div>
        <div className="text-indigo-400 text-lg font-semibold">
          {action}
        </div>
      </div>

      {/* REASON */}
      <p className="text-xs text-gray-400 mb-3">
        {reason}
      </p>

      {/* CONFIDENCE */}
      <div className="mb-3">
        <ConfidenceBar value={confidence} />
      </div>

      {/* RISK */}
      <div className="flex justify-between text-xs mb-3">
        <span className="text-gray-500">Risk</span>
        <span
          className={
            risk === "high"
              ? "text-red-400"
              : risk === "medium"
              ? "text-yellow-400"
              : "text-green-400"
          }
        >
          {risk}
        </span>
      </div>

      {/* IMPACT */}
      {impact.length > 0 && (
        <div className="mb-3 text-xs text-gray-400">
          <div className="mb-1 text-gray-500">Expected Impact</div>
          <ul className="space-y-1">
            {impact.map((i: string, idx: number) => (
              <li key={idx}>• {i}</li>
            ))}
          </ul>
        </div>
      )}

      {/* EXPLANATION */}
      {explanation && (
        <div className="mb-3 text-xs text-gray-400 border-t border-white/10 pt-2">
          <b className="text-gray-300">Why this action?</b>
          <p className="mt-1">{explanation}</p>
        </div>
      )}

      {/* ALTERNATIVES */}
      {alternatives.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-gray-500 mb-1">Alternatives</div>
          <div className="flex flex-wrap gap-2">
            {alternatives.map((alt: any, i: number) => (
              <button
                key={i}
                className="text-xs px-2 py-1 bg-white/5 rounded-lg hover:bg-white/10 transition"
              >
                {alt.action}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* EXECUTION FLOW */}
      {executable && (
        <>
          {!confirm ? (
            <button
              onClick={() => setConfirm(true)}
              className="mt-2 w-full bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-300 py-2 rounded-xl text-sm transition"
            >
              Review Action
            </button>
          ) : (
            <button
              onClick={handleExecute}
              className="mt-2 w-full bg-green-500/20 hover:bg-green-500/30 text-green-300 py-2 rounded-xl text-sm transition"
            >
              Confirm & Execute
            </button>
          )}
        </>
      )}

      {/* STATUS */}
      {status !== "idle" && (
        <div className="mt-3 text-xs text-gray-400">
          Status:{" "}
          <span
            className={
              status === "executing"
                ? "text-yellow-400"
                : status === "success"
                ? "text-green-400"
                : "text-red-400"
            }
          >
            {status}
          </span>
        </div>
      )}
    </GlassCard>
  );
}
