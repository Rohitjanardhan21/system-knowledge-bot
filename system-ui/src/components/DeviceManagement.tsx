import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  fetchDevices,
  registerDevice,
  type ManagedDevice,
  type RegisterDeviceRequest,
} from "../services/api";

const colors = {
  accent: "#00d4ff",
  border: "rgba(0, 212, 255, 0.18)",
  danger: "#ff5577",
  muted: "#7a9bbf",
  success: "#00ff9d",
  surface: "rgba(6, 14, 35, 0.72)",
  text: "#ddeeff",
  warning: "#ffaa00",
};

const inputStyle = {
  width: "100%",
  padding: "9px 10px",
  color: colors.text,
  background: "#050916",
  border: `1px solid ${colors.border}`,
  borderRadius: 4,
  fontFamily: "'Share Tech Mono', monospace",
  fontSize: 11,
};

const initialForm: RegisterDeviceRequest = {
  device_id: "",
  device_name: "",
  os: "Windows",
  os_version: "",
  hostname: "",
  capabilities: [],
};

function formatLastSeen(seconds?: number | null) {
  if (seconds == null) return "never";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
}

function exportDevices(devices: ManagedDevice[]) {
  if (devices.length === 0) return;
  const rows = devices.map((device) => ({
    device_id: device.device_id,
    device_name: device.device_name,
    os: device.os,
    os_version: device.os_version,
    hostname: device.hostname,
    status: device.status,
    last_seen_s: device.last_seen_s,
  }));
  const columns = Object.keys(rows[0]);
  const escape = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => escape(row[column as keyof typeof row])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "cvis-devices.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export default function DeviceManagement() {
  const [devices, setDevices] = useState<ManagedDevice[]>([]);
  const [form, setForm] = useState(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [credential, setCredential] = useState("");
  const [copied, setCopied] = useState(false);

  const refreshDevices = useCallback(async () => {
    try {
      setDevices(await fetchDevices());
      setError("");
    } catch (requestError) {
      console.error("Could not load devices:", requestError);
      setError("Device inventory is unavailable. Check your connection and permissions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDevices();
    const interval = window.setInterval(() => void refreshDevices(), 15000);
    return () => window.clearInterval(interval);
  }, [refreshDevices]);

  const submitRegistration = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setCredential("");
    try {
      const response = await registerDevice(form);
      setCredential(response.credential);
      setForm(initialForm);
      setShowForm(false);
      await refreshDevices();
    } catch (requestError) {
      console.error("Could not register device:", requestError);
      setError("Registration failed. Confirm the device ID is unique and admin access is available.");
    } finally {
      setSubmitting(false);
    }
  };

  const copyCredential = async () => {
    if (!credential) return;
    try {
      await navigator.clipboard.writeText(credential);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch (copyError) {
      console.error("Could not copy device credential:", copyError);
      setError("Copy failed. Select the credential manually.");
    }
  };

  return (
    <section
      id="devices"
      style={{
        padding: 22,
        borderRadius: 6,
        border: `1px solid ${colors.border}`,
        background: colors.surface,
        boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div>
          <div style={{ color: colors.accent, fontSize: 11, letterSpacing: "0.12em", fontFamily: "'Share Tech Mono', monospace" }}>
            ▸ DEVICE MANAGEMENT
          </div>
          <div style={{ color: colors.muted, fontSize: 10, marginTop: 4, fontFamily: "'Share Tech Mono', monospace" }}>
            Register agents and verify telemetry connections
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((value) => !value)}
          style={{ padding: "8px 10px", color: colors.accent, background: "rgba(0,212,255,0.07)", border: `1px solid ${colors.border}`, borderRadius: 4, cursor: "pointer", fontFamily: "'Share Tech Mono', monospace", fontSize: 10 }}
        >
          {showForm ? "CANCEL" : "+ REGISTER DEVICE"}
        </button>
        <button
          type="button"
          onClick={() => exportDevices(devices)}
          disabled={devices.length === 0}
          style={{ padding: "8px 10px", color: colors.muted, background: "transparent", border: `1px solid ${colors.border}`, borderRadius: 4, cursor: devices.length === 0 ? "not-allowed" : "pointer", fontFamily: "'Share Tech Mono', monospace", fontSize: 10 }}
        >
          EXPORT CSV
        </button>
      </div>

      {credential && (
        <div style={{ marginTop: 16, padding: 14, borderRadius: 4, border: `1px solid ${colors.warning}66`, background: "rgba(255,170,0,0.08)", fontFamily: "'Share Tech Mono', monospace" }}>
          <div style={{ color: colors.warning, fontSize: 10, fontWeight: 700 }}>DEVICE CREDENTIAL CREATED</div>
          <div style={{ color: colors.muted, fontSize: 9, margin: "6px 0 8px" }}>Copy this credential now. It will not be shown again by this panel.</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <code style={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: colors.text, fontSize: 10 }}>{credential}</code>
            <button type="button" onClick={() => void copyCredential()} style={{ flexShrink: 0, padding: "6px 8px", color: colors.warning, background: "transparent", border: `1px solid ${colors.warning}66`, borderRadius: 3, cursor: "pointer", fontFamily: "'Share Tech Mono', monospace", fontSize: 9 }}>
              {copied ? "COPIED" : "COPY"}
            </button>
          </div>
        </div>
      )}

      {showForm && (
        <form onSubmit={submitRegistration} style={{ display: "grid", gap: 10, marginTop: 16, padding: 14, borderRadius: 4, border: `1px solid ${colors.border}`, background: "rgba(0,0,0,0.2)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
            <label style={{ color: colors.muted, fontSize: 9, fontFamily: "'Share Tech Mono', monospace" }}>
              DEVICE ID *
              <input required maxLength={128} value={form.device_id} onChange={(event) => setForm({ ...form, device_id: event.target.value })} style={inputStyle} placeholder="workstation-01" />
            </label>
            <label style={{ color: colors.muted, fontSize: 9, fontFamily: "'Share Tech Mono', monospace" }}>
              DISPLAY NAME *
              <input required value={form.device_name} onChange={(event) => setForm({ ...form, device_name: event.target.value })} style={inputStyle} placeholder="Build server" />
            </label>
            <label style={{ color: colors.muted, fontSize: 9, fontFamily: "'Share Tech Mono', monospace" }}>
              OPERATING SYSTEM *
              <input required value={form.os} onChange={(event) => setForm({ ...form, os: event.target.value })} style={inputStyle} placeholder="Windows" />
            </label>
            <label style={{ color: colors.muted, fontSize: 9, fontFamily: "'Share Tech Mono', monospace" }}>
              OS VERSION
              <input value={form.os_version} onChange={(event) => setForm({ ...form, os_version: event.target.value })} style={inputStyle} placeholder="11 24H2" />
            </label>
            <label style={{ color: colors.muted, fontSize: 9, fontFamily: "'Share Tech Mono', monospace" }}>
              HOSTNAME
              <input value={form.hostname} onChange={(event) => setForm({ ...form, hostname: event.target.value })} style={inputStyle} placeholder="BUILD-01" />
            </label>
            <label style={{ color: colors.muted, fontSize: 9, fontFamily: "'Share Tech Mono', monospace" }}>
              CAPABILITIES
              <input value={form.capabilities?.join(", ") ?? ""} onChange={(event) => setForm({ ...form, capabilities: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) })} style={inputStyle} placeholder="metrics, processes" />
            </label>
          </div>
          <button disabled={submitting} type="submit" style={{ justifySelf: "start", padding: "8px 12px", color: colors.success, background: "rgba(0,255,157,0.07)", border: `1px solid ${colors.success}66`, borderRadius: 4, cursor: submitting ? "wait" : "pointer", fontFamily: "'Share Tech Mono', monospace", fontSize: 10 }}>
            {submitting ? "REGISTERING…" : "CREATE DEVICE CREDENTIAL"}
          </button>
        </form>
      )}

      {error && <div role="alert" style={{ marginTop: 14, color: colors.danger, fontSize: 10, fontFamily: "'Share Tech Mono', monospace" }}>{error}</div>}

      <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
        {loading ? (
          <div style={{ color: colors.muted, fontSize: 10, fontFamily: "'Share Tech Mono', monospace" }}>Loading device inventory…</div>
        ) : devices.length === 0 ? (
          <div style={{ padding: 14, color: colors.muted, border: `1px dashed ${colors.border}`, borderRadius: 4, fontSize: 10, fontFamily: "'Share Tech Mono', monospace" }}>
            No devices registered yet. Register an agent to start receiving telemetry.
          </div>
        ) : devices.map((device) => {
          const online = device.status === "online";
          return (
            <div key={device.device_id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 10, alignItems: "center", padding: "11px 12px", border: `1px solid ${online ? colors.success : colors.border}40`, borderRadius: 4, background: "rgba(0,0,0,0.2)", fontFamily: "'Share Tech Mono', monospace" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: colors.text, fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{device.device_name} <span style={{ color: colors.muted }}>· {device.device_id}</span></div>
                <div style={{ color: colors.muted, fontSize: 9, marginTop: 4 }}>{device.os}{device.os_version ? ` ${device.os_version}` : ""}{device.hostname ? ` · ${device.hostname}` : ""}</div>
              </div>
              <div style={{ color: online ? colors.success : colors.muted, fontSize: 9, textAlign: "right" }}>
                <div>{online ? "● ONLINE" : "○ OFFLINE"}</div>
                <div style={{ marginTop: 4, color: colors.muted }}>{formatLastSeen(device.last_seen_s)}</div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
