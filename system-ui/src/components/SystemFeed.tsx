import React, { useState } from "react";
import { AlertTriangle, CheckCircle, Info, ChevronRight } from "lucide-react";

/* ─────────────────────────────────────────────
   TYPES
───────────────────────────────────────────── */
type Event = {
  id: string;
  time: string;
  message: string;
  type?: "info" | "warning" | "critical" | "success";
  reason?: string;
  impact?: string;
};

/* ─────────────────────────────────────────────
   ICON + COLOR MAPPING
───────────────────────────────────────────── */
const getMeta = (type: string = "info") => {
  switch (type) {
    case "critical":
      return {
        icon: AlertTriangle,
        color: "#ef4444",
        bg: "rgba(239,68,68,0.08)"
      };
    case "warning":
      return {
        icon: AlertTriangle,
        color: "#f59e0b",
        bg: "rgba(245,158,11,0.08)"
      };
    case "success":
      return {
        icon: CheckCircle,
        color: "#22c55e",
        bg: "rgba(34,197,94,0.08)"
      };
    default:
      return {
        icon: Info,
        color: "#6366f1",
        bg: "rgba(99,102,241,0.08)"
      };
  }
};

/* ─────────────────────────────────────────────
   COMPONENT
───────────────────────────────────────────── */
export default function SystemFeed({ events = [] }: { events: Event[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggle = (id: string) => {
    setExpanded(prev => (prev === id ? null : id));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {events.length === 0 && (
        <div style={{
          padding: 16,
          borderRadius: 10,
          background: "rgba(99,102,241,0.05)",
          fontSize: 13,
          color: "#6b7280"
        }}>
          Awaiting system events...
        </div>
      )}

      {events.map((e) => {
        const meta = getMeta(e.type);
        const Icon = meta.icon;

        return (
          <div
            key={e.id}
            onClick={() => toggle(e.id)}
            style={{
              padding: 14,
              borderRadius: 12,
              cursor: "pointer",
              background: meta.bg,
              border: "1px solid rgba(255,255,255,0.05)",
              transition: "all 0.25s ease",
              transform: expanded === e.id ? "scale(1.01)" : "scale(1)"
            }}
          >
            {/* TOP ROW */}
            <div style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Icon size={16} color={meta.color} />

                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {e.message}
                </div>
              </div>

              <div style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 11,
                color: "#6b7280"
              }}>
                {e.time}
                <ChevronRight
                  size={14}
                  style={{
                    transform: expanded === e.id ? "rotate(90deg)" : "rotate(0deg)",
                    transition: "0.2s"
                  }}
                />
              </div>
            </div>

            {/* EXPANDED REASONING */}
            {expanded === e.id && (
              <div style={{
                marginTop: 12,
                paddingTop: 12,
                borderTop: "1px solid rgba(255,255,255,0.06)",
                fontSize: 12,
                lineHeight: 1.6,
                color: "#9ca3af"
              }}>
                {e.reason && (
                  <div style={{ marginBottom: 6 }}>
                    <b style={{ color: "#e5e7eb" }}>Reason:</b> {e.reason}
                  </div>
                )}

                {e.impact && (
                  <div>
                    <b style={{ color: "#e5e7eb" }}>Impact:</b> {e.impact}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
