import React, { useState } from "react";

interface ExplainButtonProps {
  context?: string;              // e.g. "cpu_high", "memory_spike"
  data?: any;                    // full system data (optional)
  onExplain?: (response: any) => void; // callback to parent (chat / modal)
}

export default function ExplainButton({
  context = "general",
  data = {},
  onExplain
}: ExplainButtonProps) {

  const [loading, setLoading] = useState(false);

  /* ─────────────────────────────────────────────
      BUILD CONTEXTUAL QUERY
  ───────────────────────────────────────────── */
  const buildQuery = () => {
    switch (context) {
      case "cpu":
        return `Explain why CPU usage is ${data.cpu}% and what it means`;
      case "memory":
        return `Explain current memory usage and impact`;
      case "prediction":
        return `Explain future system prediction and risks`;
      case "decision":
        return `Why is this action recommended and what happens if applied?`;
      default:
        return `Explain current system state in simple terms`;
    }
  };

  /* ─────────────────────────────────────────────
      CALL AI BACKEND
  ───────────────────────────────────────────── */
  const handleExplain = async () => {
    try {
      setLoading(true);

      const query = buildQuery();

      const res = await fetch("http://localhost:8000/ai/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          query,
          metrics: data
        })
      });

      const result = await res.json();

      if (onExplain) {
        onExplain(result);
      }

    } catch (err) {
      console.error("Explain error:", err);
    } finally {
      setLoading(false);
    }
  };

  /* ─────────────────────────────────────────────
      UI
  ───────────────────────────────────────────── */
  return (
    <button
      onClick={handleExplain}
      disabled={loading}
      style={{
        marginTop: 10,
        fontSize: 12,
        fontWeight: 600,
        color: "#6366f1",
        background: "rgba(99,102,241,0.08)",
        border: "1px solid rgba(99,102,241,0.2)",
        padding: "6px 10px",
        borderRadius: 8,
        cursor: loading ? "not-allowed" : "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        transition: "all 0.2s ease",
        opacity: loading ? 0.7 : 1
      }}
      onMouseEnter={(e) => {
        if (!loading) {
          e.currentTarget.style.background = "rgba(99,102,241,0.15)";
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "rgba(99,102,241,0.08)";
      }}
    >
      {loading ? (
        <>
          <span className="spinner" /> Thinking...
        </>
      ) : (
        <>
          🧠 Explain
        </>
      )}

      {/* Spinner animation */}
      <style>{`
        .spinner {
          width: 12px;
          height: 12px;
          border: 2px solid rgba(99,102,241,0.3);
          border-top: 2px solid #6366f1;
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </button>
  );
}
