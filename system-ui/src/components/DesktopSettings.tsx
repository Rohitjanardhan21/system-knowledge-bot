import { useEffect, useState, type CSSProperties } from "react";
import { fetchDesktopSettings, saveDesktopSettings } from "../services/api";

interface DesktopSettingsProps {
  onClose: () => void;
}

export default function DesktopSettings({ onClose }: DesktopSettingsProps) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [backgroundMonitoring, setBackgroundMonitoring] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    fetchDesktopSettings()
      .then((settings) => {
        if (!active) return;
        setAvailable(settings.available);
        setBackgroundMonitoring(settings.background_monitoring ?? false);
      })
      .catch(() => {
        if (active) {
          setAvailable(false);
          setMessage("Could not load desktop preferences.");
        }
      });
    return () => { active = false; };
  }, []);

  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const settings = await saveDesktopSettings(backgroundMonitoring);
      setAvailable(settings.available);
      setBackgroundMonitoring(settings.background_monitoring ?? false);
      setMessage("Preference saved. It applies when the dashboard is hidden.");
    } catch {
      setMessage("Could not save this preference. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="desktop-settings-title" style={styles.backdrop}>
      <section style={styles.panel}>
        <div style={styles.header}>
          <h2 id="desktop-settings-title" style={styles.title}>Settings</h2>
          <button type="button" onClick={onClose} style={styles.close}>Close</button>
        </div>
        {available === null ? (
          <p style={styles.text}>Loading preferences…</p>
        ) : available ? (
          <>
            <label style={styles.choice}>
              <input
                type="checkbox"
                checked={backgroundMonitoring}
                onChange={(event) => setBackgroundMonitoring(event.target.checked)}
              />
              <span>
                <strong>Enable Background Monitoring</strong>
                <small>When the dashboard is hidden, keep CVIS monitoring. Turn this off for on-demand use; CVIS stops collecting while hidden.</small>
              </span>
            </label>
            <p style={styles.note}>The choice applies when you hide the dashboard. You can change modes any time from the CVIS tray icon, even while the dashboard is hidden. CVIS does not advertise a RAM or CPU estimate; actual idle resource use has not been measured.</p>
            <button type="button" disabled={busy} onClick={save} style={styles.save}>
              {busy ? "Saving…" : "Save preference"}
            </button>
          </>
        ) : (
          <p style={styles.text}>Background monitoring preferences are available in the Windows desktop app only.</p>
        )}
        {message && <p aria-live="polite" style={styles.message}>{message}</p>}
      </section>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  backdrop: { position: "fixed", inset: 0, zIndex: 1100, display: "grid", placeItems: "center", padding: 20, background: "rgba(1,5,15,.88)" },
  panel: { width: "min(600px, 100%)", padding: 24, color: "#ddeeff", background: "#081426", border: "1px solid rgba(0,212,255,.35)", borderRadius: 10, fontFamily: "system-ui, sans-serif" },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 },
  title: { margin: "0 0 12px", color: "#00d4ff" },
  close: { padding: "7px 11px", color: "#ddeeff", background: "#13263d", border: "1px solid #38506b", cursor: "pointer" },
  choice: { display: "flex", alignItems: "flex-start", gap: 12, padding: 14, background: "#0c1d2f", borderRadius: 6, cursor: "pointer" },
  text: { color: "#c4d6e6", lineHeight: 1.5 },
  note: { color: "#9ab1c9", fontSize: 12, lineHeight: 1.5 },
  save: { padding: "10px 16px", color: "#001018", background: "#00d4ff", border: 0, borderRadius: 4, fontWeight: 700, cursor: "pointer" },
  message: { color: "#9bd8b2", fontSize: 13 },
};
