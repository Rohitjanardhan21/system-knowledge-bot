import { useEffect, useState } from "react";

const STORAGE_KEY = "cvis:browser-notifications";

export default function NotificationPreferences() {
  const [enabled, setEnabled] = useState(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    typeof window !== "undefined" && "Notification" in window
      ? Notification.permission
      : "unsupported",
  );

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(enabled));
    } catch (error) {
      console.error("Could not persist notification preference:", error);
    }
  }, [enabled]);

  const toggle = async () => {
    if (!("Notification" in window)) {
      setPermission("unsupported");
      return;
    }
    if (!enabled && Notification.permission === "default") {
      setPermission(await Notification.requestPermission());
    }
    setEnabled((value) => !value);
  };

  return (
    <section style={{ marginTop: 20, padding: 18, borderRadius: 6, border: "1px solid rgba(0, 212, 255, 0.18)", background: "rgba(6, 14, 35, 0.72)" }}>
      <div style={{ color: "#00d4ff", fontSize: 11, letterSpacing: "0.12em", fontFamily: "'Share Tech Mono', monospace" }}>
        ▸ NOTIFICATION PREFERENCES
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 14, flexWrap: "wrap", marginTop: 10 }}>
        <div style={{ color: "#7a9bbf", fontSize: 10, fontFamily: "'Share Tech Mono', monospace" }}>
          Browser alerts for new high-severity incidents
          <div style={{ marginTop: 4, color: "#3a5570" }}>Permission: {permission.toUpperCase()}</div>
        </div>
        <button type="button" onClick={() => void toggle()} style={{ padding: "8px 10px", color: enabled ? "#00ff9d" : "#7a9bbf", background: "rgba(0,212,255,0.07)", border: "1px solid rgba(0,212,255,0.3)", borderRadius: 4, cursor: "pointer", fontFamily: "'Share Tech Mono', monospace", fontSize: 10 }}>
          {enabled ? "BROWSER ALERTS ON" : "ENABLE BROWSER ALERTS"}
        </button>
      </div>
    </section>
  );
}
