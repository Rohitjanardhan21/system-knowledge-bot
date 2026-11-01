import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  fetchDevices,
  registerDevice,
  type ManagedDevice,
  type RegisterDeviceRequest,
} from "../services/api";

interface SetupWizardProps {
  onComplete: () => void;
  onClose: () => void;
}

const STORAGE_KEY = "cvis:setup-profile";
const steps = ["Workspace", "Connect device", "Verify telemetry", "Alert preferences", "Team access"];

const colors = {
  accent: "#00d4ff",
  border: "rgba(0, 212, 255, 0.22)",
  danger: "#ff5577",
  muted: "#7a9bbf",
  success: "#00ff9d",
  surface: "#071126",
  text: "#ddeeff",
  warning: "#ffaa00",
};

const fieldStyle = {
  width: "100%",
  boxSizing: "border-box" as const,
  padding: "10px",
  color: colors.text,
  background: "#050916",
  border: `1px solid ${colors.border}`,
  borderRadius: 4,
  fontFamily: "'Share Tech Mono', monospace",
  fontSize: 11,
};

const initialDevice: RegisterDeviceRequest = {
  device_id: "",
  device_name: "",
  os: "Windows",
  os_version: "",
  hostname: "",
  capabilities: ["metrics", "processes"],
};

function readProfile() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as { workspaceName?: string; timezone?: string } : {};
  } catch (error) {
    console.error("Could not read setup profile:", error);
    return {};
  }
}

export default function SetupWizard({ onComplete, onClose }: SetupWizardProps) {
  const savedProfile = useMemo(readProfile, []);
  const [step, setStep] = useState(0);
  const [workspaceName, setWorkspaceName] = useState(savedProfile.workspaceName ?? "");
  const [timezone, setTimezone] = useState(savedProfile.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [deviceForm, setDeviceForm] = useState(initialDevice);
  const [registeredDevice, setRegisteredDevice] = useState<ManagedDevice | null>(null);
  const [credential, setCredential] = useState("");
  const [devices, setDevices] = useState<ManagedDevice[]>([]);
  const [notifications, setNotifications] = useState(true);
  const [emailAlerts, setEmailAlerts] = useState(false);
  const [teamNote, setTeamNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const saveProfile = () => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ workspaceName: workspaceName.trim(), timezone }));
    } catch (saveError) {
      console.error("Could not save setup profile:", saveError);
    }
  };

  const next = () => {
    setError("");
    if (step === 0 && !workspaceName.trim()) {
      setError("Enter a workspace name to continue.");
      return;
    }
    saveProfile();
    setStep((current) => Math.min(steps.length - 1, current + 1));
  };

  const submitDevice = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await registerDevice(deviceForm);
      setCredential(response.credential);
      const inventory = await fetchDevices();
      const device = inventory.find((item) => item.device_id === response.device_id) ?? null;
      setRegisteredDevice(device);
      setDevices(inventory);
    } catch (requestError) {
      console.error("Setup device registration failed:", requestError);
      setError("Device registration failed. Confirm admin access, Redis availability, and that the device ID is unique.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (step !== 2) return;
    let active = true;
    const refresh = async () => {
      try {
        const inventory = await fetchDevices();
        if (!active) return;
        setDevices(inventory);
        if (registeredDevice) {
          setRegisteredDevice(inventory.find((item) => item.device_id === registeredDevice.device_id) ?? registeredDevice);
        }
      } catch (requestError) {
        console.error("Setup telemetry verification failed:", requestError);
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 5000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [registeredDevice, step]);

  const finish = () => {
    saveProfile();
    try {
      window.localStorage.setItem("cvis:alert-preferences", JSON.stringify({
        browserNotifications: notifications,
        emailAlerts,
      }));
      window.localStorage.setItem("cvis:setup-complete", "true");
    } catch (saveError) {
      console.error("Could not save setup preferences:", saveError);
    }
    onComplete();
  };

  const deviceOnline = registeredDevice?.status === "online";

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="setup-wizard-title" style={{ position: "fixed", inset: 0, zIndex: 1000, display: "grid", placeItems: "center", padding: 20, background: "rgba(0,0,0,0.72)", backdropFilter: "blur(6px)" }}>
      <div style={{ width: "min(760px, 100%)", maxHeight: "min(720px, 92vh)", overflow: "auto", padding: 26, border: `1px solid ${colors.border}`, borderRadius: 8, background: colors.surface, color: colors.text, boxShadow: "0 20px 70px rgba(0,0,0,0.5)", fontFamily: "'Share Tech Mono', monospace" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
          <div>
            <div style={{ color: colors.accent, fontSize: 12, letterSpacing: "0.12em" }}>CVIS SETUP WIZARD</div>
            <h2 id="setup-wizard-title" style={{ margin: "8px 0 4px", fontFamily: "'Rajdhani', sans-serif" }}>Connect your monitoring workspace</h2>
            <div style={{ color: colors.muted, fontSize: 10 }}>Complete the essentials now; every step can be revisited later.</div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close setup wizard" style={{ padding: "6px 9px", color: colors.muted, background: "transparent", border: `1px solid ${colors.border}`, borderRadius: 4, cursor: "pointer", fontSize: 16 }}>×</button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(${steps.length}, 1fr)`, gap: 5, margin: "24px 0" }}>
          {steps.map((label, index) => (
            <div key={label} style={{ minWidth: 0 }}>
              <div style={{ height: 4, borderRadius: 3, background: index <= step ? colors.accent : "rgba(255,255,255,0.12)" }} />
              <div style={{ marginTop: 6, color: index === step ? colors.text : colors.muted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 9 }}>{index + 1}. {label}</div>
            </div>
          ))}
        </div>

        {step === 0 && (
          <div style={{ display: "grid", gap: 14 }}>
            <p style={{ color: colors.muted, fontSize: 11, lineHeight: 1.6 }}>A workspace keeps your devices, alerts, and incident history organized. This profile is stored locally until server-side workspace administration is enabled.</p>
            <label style={{ color: colors.muted, fontSize: 10 }}>WORKSPACE NAME *
              <input autoFocus required value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="Production operations" style={fieldStyle} />
            </label>
            <label style={{ color: colors.muted, fontSize: 10 }}>TIMEZONE
              <input value={timezone} onChange={(event) => setTimezone(event.target.value)} style={fieldStyle} />
            </label>
          </div>
        )}

        {step === 1 && (
          <div style={{ display: "grid", gap: 14 }}>
            <p style={{ color: colors.muted, fontSize: 11, lineHeight: 1.6 }}>Register the machine that will send heartbeats and telemetry. The generated credential is shown once so it can be placed in the agent configuration.</p>
            <form onSubmit={submitDevice} style={{ display: "grid", gap: 10 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 10 }}>
                {([
                  ["device_id", "DEVICE ID *", "workstation-01", true],
                  ["device_name", "DISPLAY NAME *", "Production server", true],
                  ["os", "OPERATING SYSTEM *", "Windows", true],
                  ["os_version", "OS VERSION", "11 24H2", false],
                  ["hostname", "HOSTNAME", "PROD-01", false],
                ] as const).map(([field, label, placeholder, required]) => (
                  <label key={field} style={{ color: colors.muted, fontSize: 9 }}>{label}
                    <input required={required} value={deviceForm[field] ?? ""} onChange={(event) => setDeviceForm({ ...deviceForm, [field]: event.target.value })} placeholder={placeholder} style={fieldStyle} />
                  </label>
                ))}
              </div>
              <button type="submit" disabled={loading} style={{ justifySelf: "start", padding: "9px 12px", color: colors.success, background: "rgba(0,255,157,0.07)", border: `1px solid ${colors.success}66`, borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10 }}>
                {loading ? "REGISTERING…" : "REGISTER DEVICE"}
              </button>
            </form>
            {credential && (
              <div style={{ padding: 13, border: `1px solid ${colors.warning}66`, borderRadius: 4, background: "rgba(255,170,0,0.08)" }}>
                <div style={{ color: colors.warning, fontSize: 10 }}>COPY THIS DEVICE CREDENTIAL NOW</div>
                <code style={{ display: "block", marginTop: 8, overflowWrap: "anywhere", color: colors.text, fontSize: 10 }}>{credential}</code>
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div style={{ display: "grid", gap: 14 }}>
            <p style={{ color: colors.muted, fontSize: 11, lineHeight: 1.6 }}>Start the agent with the credential from the previous step. This page checks the device inventory every five seconds.</p>
            <div style={{ padding: 18, border: `1px solid ${deviceOnline ? colors.success : colors.border}`, borderRadius: 5, background: "rgba(0,0,0,0.2)", textAlign: "center" }}>
              <div style={{ color: deviceOnline ? colors.success : colors.warning, fontSize: 24 }}>{deviceOnline ? "● ONLINE" : "○ WAITING FOR HEARTBEAT"}</div>
              <div style={{ marginTop: 8, color: colors.muted, fontSize: 10 }}>{registeredDevice ? `${registeredDevice.device_name} · ${registeredDevice.device_id}` : "Register a device first to verify telemetry."}</div>
              {registeredDevice && <div style={{ marginTop: 6, color: colors.muted, fontSize: 10 }}>Last seen: {registeredDevice.last_seen_s == null ? "never" : `${Math.round(registeredDevice.last_seen_s)} seconds ago`}</div>}
            </div>
            {devices.length > 0 && <div style={{ color: colors.muted, fontSize: 10 }}>{devices.length} device{devices.length === 1 ? "" : "s"} visible in this workspace.</div>}
          </div>
        )}

        {step === 3 && (
          <div style={{ display: "grid", gap: 14 }}>
            <p style={{ color: colors.muted, fontSize: 11, lineHeight: 1.6 }}>Choose how the browser should surface urgent monitoring conditions. These preferences are local to this browser; server-side delivery channels can be configured later.</p>
            <label style={{ display: "flex", gap: 10, alignItems: "center", color: colors.text, fontSize: 11 }}>
              <input type="checkbox" checked={notifications} onChange={(event) => setNotifications(event.target.checked)} />
              Browser notifications for high and critical alerts
            </label>
            <label style={{ display: "flex", gap: 10, alignItems: "center", color: colors.muted, fontSize: 11 }}>
              <input type="checkbox" checked={emailAlerts} onChange={(event) => setEmailAlerts(event.target.checked)} />
              Email alerts (requires server notification configuration)
            </label>
          </div>
        )}

        {step === 4 && (
          <div style={{ display: "grid", gap: 14 }}>
            <p style={{ color: colors.muted, fontSize: 11, lineHeight: 1.6 }}>Team invitations need a server-side invitation endpoint and role-management policy. The current account system supports registration, but does not yet expose invitation management.</p>
            <div style={{ padding: 14, border: `1px solid ${colors.warning}44`, borderRadius: 4, background: "rgba(255,170,0,0.06)", color: colors.warning, fontSize: 10 }}>
              TEAM ACCESS: ADMINISTRATOR ONLY
            </div>
            <label style={{ color: colors.muted, fontSize: 10 }}>TEAM SETUP NOTE
              <textarea value={teamNote} onChange={(event) => setTeamNote(event.target.value)} placeholder="Record who should receive access later…" rows={4} style={{ ...fieldStyle, resize: "vertical" }} />
            </label>
          </div>
        )}

        {error && <div role="alert" style={{ marginTop: 16, color: colors.danger, fontSize: 10 }}>{error}</div>}

        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginTop: 24 }}>
          <button type="button" disabled={step === 0} onClick={() => { setError(""); setStep((current) => Math.max(0, current - 1)); }} style={{ padding: "9px 12px", color: colors.muted, background: "transparent", border: `1px solid ${colors.border}`, borderRadius: 4, cursor: step === 0 ? "not-allowed" : "pointer", fontFamily: "inherit", fontSize: 10 }}>BACK</button>
          {step < steps.length - 1 ? (
            <button type="button" onClick={next} style={{ padding: "9px 12px", color: colors.accent, background: "rgba(0,212,255,0.08)", border: `1px solid ${colors.border}`, borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10 }}>CONTINUE</button>
          ) : (
            <button type="button" onClick={finish} style={{ padding: "9px 12px", color: colors.success, background: "rgba(0,255,157,0.08)", border: `1px solid ${colors.success}66`, borderRadius: 4, cursor: "pointer", fontFamily: "inherit", fontSize: 10 }}>FINISH SETUP</button>
          )}
        </div>
      </div>
    </div>
  );
}
