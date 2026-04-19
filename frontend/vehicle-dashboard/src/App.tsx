import { useState, useEffect, useRef } from "react";

/* ---------------- HELPERS & CONFIG ---------------- */

const hazardMap: any = { 
  LOW: 20, 
  MODERATE: 50, 
  HIGH: 80, 
  CRITICAL: 95 
};

const cardStyle: any = {
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.08)",
  padding: "16px",
  borderRadius: "16px",
  backdropFilter: "blur(10px)",
  transition: "all 0.3s ease"
};

/* ---------------- CAMERA FEED COMPONENT ---------------- */

function CameraFeed() {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
          if (videoRef.current) videoRef.current.srcObject = stream;
        })
        .catch(() => console.warn("Camera feed restricted or unavailable"));
    }
  }, []);

  return (
    <div style={{ 
      position: "relative", 
      borderRadius: "20px", 
      overflow: "hidden", 
      border: "1px solid rgba(255,255,255,0.1)",
      background: "#000",
      lineHeight: 0
    }}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        style={{ width: "100%", height: "auto", opacity: 0.85, transform: "scaleX(-1)" }}
      />
      <div style={{ 
        position: "absolute", 
        top: "16px", 
        left: "16px", 
        display: "flex", 
        alignItems: "center", 
        gap: "8px",
        background: "rgba(0,0,0,0.5)",
        padding: "6px 12px",
        borderRadius: "20px",
        backdropFilter: "blur(4px)"
      }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#ef4444", animation: "pulse 1.5s infinite" }} />
        <span style={{ fontSize: "10px", fontWeight: 800, color: "#fff", letterSpacing: "0.1em" }}>LIVE OPTICAL STREAM</span>
      </div>
    </div>
  );
}

/* ---------------- HIGH-FIDELITY GAUGE ---------------- */

function ArcGauge({ value, max, label, unit, color, size = 110, warn = 0.75, crit = 0.9 }: any) {
  const pct = Math.min(value / max, 1);
  const r = (size - 18) / 2;
  const cx = size / 2, cy = size / 2;
  const startAngle = -220, sweep = 260;
  
  const toRad = (d: number) => (d * Math.PI) / 180;
  
  const arcPath = (p: number) => {
    const angle = startAngle + sweep * p;
    return `M ${cx + r * Math.cos(toRad(startAngle))} ${cy + r * Math.sin(toRad(startAngle))} 
            A ${r} ${r} 0 ${sweep * p > 180 ? 1 : 0} 1 
            ${cx + r * Math.cos(toRad(angle))} ${cy + r * Math.sin(toRad(angle))}`;
  };

  const currentColor = pct >= crit ? "#ef4444" : pct >= warn ? "#f59e0b" : color;

  return (
    <div style={{ textAlign: "center" }}>
      <svg width={size} height={size}>
        <path d={arcPath(1)} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={7} strokeLinecap="round" />
        <path d={arcPath(pct)} fill="none" stroke={currentColor} strokeWidth={7} strokeLinecap="round" 
              style={{ transition: "all 0.8s cubic-bezier(0.4, 0, 0.2, 1)" }} />
        <text x={cx} y={cy - 2} textAnchor="middle" fill="white" fontSize={18} fontWeight={800} style={{ fontFamily: "monospace" }}>
          {value?.toFixed(0)}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" fill="rgba(255,255,255,0.3)" fontSize={9} style={{ fontWeight: 600 }}>{unit}</text>
        <text x={cx} y={cy + 28} textAnchor="middle" fill="rgba(255,255,255,0.2)" fontSize={8} style={{ fontWeight: 900, letterSpacing: "0.05em" }}>
          {label.toUpperCase()}
        </text>
      </svg>
    </div>
  );
}

/* ---------------- MAIN DASHBOARD ---------------- */

export default function VehicleDashboard() {
  const [v, setV] = useState<any>({
    speed: 0, rpm: 0, hazard: 0, gear: 0,
    temp: 0, vibration: 0, acoustic: 0,
    obstacle: false, distance: 50, tti: 5,
    ai: { decision: "Syncing...", confidence: 0, reason: "Initializing reasoning kernel" },
    validation: "SYNC", anomalies: [], events: [], tick: 0
  });

  const [history, setHistory] = useState<number[]>([]);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch("http://localhost:8000/status");
        if (!res.ok) throw new Error("Connection failed");
        
        const json = await res.json();
        const intel = json.intelligence || {};
        const feat = intel.features || {};
        const insight = intel.vehicle_insight || {};
        const pre = json.pre_impact || {};
        const decision = json.latest_decision || {};

        setV({
          speed: feat.compute ? feat.compute * 140 : 0,
          rpm: feat.compute ? 1200 + feat.compute * 5800 : 0,
          hazard: hazardMap[insight.hazard?.level] || 0,
          gear: feat.compute ? Math.ceil(feat.compute * 6) : 0,
          temp: feat.thermal * 100 || 0,
          vibration: feat.vibration_intensity || 0,
          acoustic: feat.acoustic_energy * 100 || 0,
          obstacle: !!pre.prediction,
          distance: pre.prediction?.distance || 50,
          tti: pre.prediction?.time_to_impact || 5,
          ai: {
            decision: decision.action || "Observe",
            confidence: decision.confidence || 0,
            reason: decision.reason || "Monitoring nominal dynamics"
          },
          validation: json.validated ? "VERIFIED" : "BLOCKED",
          anomalies: Object.entries(insight.signals || {}).map(([k, val]: any) => `${k}: ${val.status || val.type}`),
          events: (json.system_feed || []).map((e: any) => e.message || e.msg || "..."),
          tick: json.tick
        });
        
        setHistory(prev => [...prev.slice(-40), feat.compute * 100 || 0]);
      } catch {
        console.warn("Backend link offline. Dashboard in sync-wait state.");
      }
    };

    const id = setInterval(fetchStatus, 1000);
    return () => clearInterval(id);
  }, []);

  const ttiColor = v.tti < 1.2 ? "#ef4444" : v.tti < 2.5 ? "#f59e0b" : "#10b981";

  return (
    <div style={{ 
      background: v.hazard > 80 ? "#1a0808" : "#050509", 
      minHeight: "100vh", 
      color: "white", 
      padding: "24px", 
      fontFamily: "'Inter', sans-serif", 
      transition: "background 0.5s ease" 
    }}>
      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        .blink { animation: pulse 1s infinite; }
        ::-webkit-scrollbar { display: none; }
      `}</style>

      {/* HEADER SECTION */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ width: 12, height: 12, borderRadius: "3px", background: "#6366f1", boxShadow: "0 0 15px #6366f1" }} />
          <span style={{ fontWeight: 900, letterSpacing: "0.25em", fontSize: "14px", color: "rgba(255,255,255,0.8)" }}>COGNI·DRIVE v3.2</span>
        </div>
        <div style={{ display: "flex", gap: "24px", fontSize: "11px", fontWeight: 700 }}>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <span style={{ color: "rgba(255,255,255,0.3)" }}>TRUTH ENGINE</span>
            <span style={{ color: v.validation === "VERIFIED" ? "#10b981" : "#ef4444" }}>{v.validation}</span>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <span style={{ color: "rgba(255,255,255,0.3)" }}>DECISION MODE</span>
            <span className="blink" style={{ color: "#6366f1" }}>ACTIVE</span>
          </div>
          <span style={{ color: "rgba(255,255,255,0.2)", fontFamily: "monospace" }}>T-ID: {v.tick}</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: "24px" }}>
        
        {/* LEFT COLUMN: LIVE FEED & PRIMARY INSTRUMENTS */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <CameraFeed />
          
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px" }}>
            <div style={cardStyle}>
               <ArcGauge value={v.speed} max={160} label="Speed" unit="km/h" color="#6366f1" />
            </div>
            <div style={cardStyle}>
               <ArcGauge value={v.temp} max={110} label="System Temp" unit="°C" color="#f59e0b" />
            </div>
            <div style={cardStyle}>
               <div style={{ textAlign: "center", padding: "4px 0" }}>
                  <div style={{ fontSize: "8px", color: "rgba(255,255,255,0.3)", fontWeight: 900, marginBottom: "16px", letterSpacing: "0.1em" }}>PRE-IMPACT RADAR</div>
                  <div style={{ fontSize: "32px", fontWeight: 900, color: ttiColor, fontFamily: "monospace" }}>{v.distance.toFixed(0)}m</div>
                  <div style={{ fontSize: "10px", color: ttiColor, fontWeight: 800, marginTop: "4px" }}>{v.tti.toFixed(1)}s TTI</div>
               </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: AI LOGIC & SYSTEM DIAGNOSTICS */}
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          
          {/* AI REASONING CARD */}
          <div style={{ ...cardStyle, borderLeft: `4px solid ${v.hazard > 80 ? "#ef4444" : "#6366f1"}`, background: "rgba(99,102,241,0.05)" }}>
            <div style={{ fontSize: "10px", color: "rgba(99,102,241,0.6)", fontWeight: 800, marginBottom: "8px" }}>AI COGNITION UNIT</div>
            <div style={{ fontSize: "20px", fontWeight: 800, color: v.hazard > 80 ? "#ef4444" : "white", letterSpacing: "-0.02em" }}>{v.ai.decision}</div>
            <div style={{ fontSize: "13px", color: "rgba(255,255,255,0.6)", marginTop: "8px", lineHeight: "1.6" }}>{v.ai.reason}</div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "20px" }}>
               <div style={{ flex: 1, height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", overflow: "hidden" }}>
                  <div style={{ width: `${v.ai.confidence * 100}%`, height: "100%", background: "#10b981", borderRadius: "2px", transition: "width 1s ease" }} />
               </div>
               <span style={{ fontSize: "11px", fontWeight: 900, color: "#10b981", fontFamily: "monospace" }}>{Math.round(v.ai.confidence * 100)}% CONFIDENCE</span>
            </div>
          </div>

          {/* SIGNALS & EVENTS GRID */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div style={cardStyle}>
              <div style={{ fontSize: "9px", fontWeight: 800, color: "rgba(255,255,255,0.3)", marginBottom: "14px", letterSpacing: "0.05em" }}>HIDDEN SIGNALS</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {v.anomalies.length > 0 ? v.anomalies.slice(0, 3).map((a: string, i: number) => (
                  <div key={i} style={{ fontSize: "11px", color: "rgba(255,255,255,0.7)", borderBottom: "1px solid rgba(255,255,255,0.05)", paddingBottom: "6px" }}>• {a}</div>
                )) : <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.2)" }}>Scanning for patterns...</div>}
              </div>
            </div>
            <div style={cardStyle}>
              <div style={{ fontSize: "9px", fontWeight: 800, color: "rgba(255,255,255,0.3)", marginBottom: "14px", letterSpacing: "0.05em" }}>SYSTEM LOGS</div>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {v.events.length > 0 ? v.events.slice(0, 3).map((e: string, i: number) => (
                  <div key={i} style={{ fontSize: "11px", color: "rgba(255,255,255,0.4)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>› {e}</div>
                )) : <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.2)" }}>Awaiting events...</div>}
              </div>
            </div>
          </div>

          {/* COMPUTE LOAD TREND */}
          <div style={cardStyle}>
            <div style={{ fontSize: "9px", fontWeight: 800, color: "rgba(255,255,255,0.3)", marginBottom: "18px", letterSpacing: "0.05em" }}>NEURAL LOAD TREND</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", height: "60px", paddingBottom: "4px" }}>
              {history.length > 0 ? history.map((h, i) => (
                <div key={i} style={{ 
                  flex: 1, 
                  background: "#6366f1", 
                  height: `${Math.max(5, h)}%`, 
                  opacity: 0.2 + (i / history.length) * 0.8, 
                  borderRadius: "2px 2px 0 0",
                  transition: "height 0.3s ease"
                }} />
              )) : <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.1)", width: "100%", textAlign: "center" }}>Establishing baseline...</div>}
            </div>
          </div>

          {/* EMERGENCY WARNINGS */}
          {v.hazard > 80 && (
            <div style={{ 
              background: "#ef4444", 
              color: "white", 
              padding: "16px", 
              borderRadius: "14px", 
              textAlign: "center", 
              fontWeight: 900, 
              fontSize: "13px",
              letterSpacing: "0.1em",
              boxShadow: "0 0 20px rgba(239, 68, 68, 0.4)",
              animation: "pulse 0.6s infinite" 
            }}>
               ⚠ CRITICAL HAZARD DETECTED
            </div>
          )}
          
          {v.validation === "BLOCKED" && (
            <div style={{ 
              border: "1px solid #ef4444", 
              color: "#ef4444", 
              padding: "12px", 
              borderRadius: "14px", 
              textAlign: "center", 
              fontWeight: 800, 
              fontSize: "11px",
              background: "rgba(239, 68, 68, 0.05)"
            }}>
               SAFETY OVERRIDE: AUTONOMOUS INTERVENTION ENGAGED
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
