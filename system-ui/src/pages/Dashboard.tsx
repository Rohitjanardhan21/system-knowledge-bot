import { useEffect, useState, useRef, useCallback } from "react";
import {
  AreaChart, Area, CartesianGrid, ResponsiveContainer, RadarChart,
  PolarGrid, PolarAngleAxis, Radar, XAxis, YAxis, Tooltip
} from "recharts";

/* ── THEME ───────────────────────────────────────────────────── */
const T = {
  bg: "#050916",
  surface: "rgba(10, 20, 50, 0.55)",
  surfaceHover: "rgba(20, 35, 75, 0.7)",
  border: "rgba(0, 212, 255, 0.12)",
  borderActive: "rgba(0, 212, 255, 0.45)",
  accent: "#00d4ff",
  accentGlow: "rgba(0, 212, 255, 0.35)",
  primary: "#4a7fff",
  success: "#00ff9d",
  warning: "#ffaa00",
  danger: "#ff3366",
  text: "#ddeeff",
  textMuted: "#7a9bbf",
  textDim: "#3a5570",
};

/* ── KEYFRAMES ────────────────────────────────────────────── */
const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap');
  @keyframes float { 0%,100%{transform:translate(0,0) scale(1);} 50%{transform:translate(20px,-20px) scale(1.05);} }
  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.5;} }
  @keyframes pulseRing { 0%{transform:scale(0.95);box-shadow:0 0 0 0 rgba(0,212,255,0.5);} 70%{transform:scale(1);box-shadow:0 0 0 20px rgba(0,212,255,0);} 100%{transform:scale(0.95);} }
  @keyframes slideIn { from{opacity:0;transform:translateY(12px);} to{opacity:1;transform:translateY(0);} }
  @keyframes criticalGlow { 0%,100%{box-shadow:0 0 30px rgba(255,51,102,0.3);} 50%{box-shadow:0 0 60px rgba(255,51,102,0.7);} }
  @keyframes criticalPulse { 0%,100%{filter:brightness(1);} 50%{filter:brightness(1.3);} }
  @keyframes scanline { 0%{top:-5%;} 100%{top:105%;} }
  @keyframes orbitDot { 0%{transform:rotate(0deg) translateX(90px) rotate(0deg);} 100%{transform:rotate(360deg) translateX(90px) rotate(-360deg);} }
  @keyframes orbitDot2 { 0%{transform:rotate(120deg) translateX(90px) rotate(-120deg);} 100%{transform:rotate(480deg) translateX(90px) rotate(-480deg);} }
  @keyframes orbitDot3 { 0%{transform:rotate(240deg) translateX(90px) rotate(-240deg);} 100%{transform:rotate(600deg) translateX(90px) rotate(-600deg);} }
  @keyframes warningGlow { 0%,100%{box-shadow:0 0 20px rgba(255,170,0,0.3);} 50%{box-shadow:0 0 50px rgba(255,170,0,0.6);} }
  @keyframes tickerSlide { 0%{transform:translateX(0);} 100%{transform:translateX(-50%);} }
  * { box-sizing: border-box; }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: rgba(0,0,0,0.3); }
  ::-webkit-scrollbar-thumb { background: rgba(0,212,255,0.3); border-radius: 2px; }
`;

/* ── CIRCUIT BOARD CANVAS BACKGROUND ─────────────────────── */
const CircuitBg = ({ isCritical, isWarning }) => {
  const canvasRef = useRef(null);
  const animRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const G = 55;
    const cols = Math.ceil(window.innerWidth / G) + 2;
    const rows = Math.ceil(window.innerHeight / G) + 2;

    const generateTraces = () => {
      const traces = [];
      for (let r = 1; r < rows; r++) {
        if (Math.random() > 0.45) {
          const y = r * G;
          const c1 = Math.floor(Math.random() * (cols - 4));
          const c2 = c1 + Math.floor(Math.random() * 6) + 3;
          traces.push({ x1: c1 * G, y1: y, x2: Math.min(c2 * G, canvas.width), y2: y });
        }
      }
      for (let c = 1; c < cols; c++) {
        if (Math.random() > 0.45) {
          const x = c * G;
          const r1 = Math.floor(Math.random() * (rows - 4));
          const r2 = r1 + Math.floor(Math.random() * 6) + 3;
          traces.push({ x1: x, y1: r1 * G, x2: x, y2: Math.min(r2 * G, canvas.height) });
        }
      }
      return traces;
    };

    const generateChips = () => {
      const chips = [];
      for (let i = 0; i < 8; i++) {
        const cx = Math.floor(Math.random() * (cols - 3) + 1) * G;
        const cy = Math.floor(Math.random() * (rows - 3) + 1) * G;
        const w = (Math.floor(Math.random() * 2) + 2) * G;
        const h = (Math.floor(Math.random() * 2) + 2) * G;
        const pins = Math.floor(Math.random() * 4) + 3;
        chips.push({ cx, cy, w, h, pins });
      }
      return chips;
    };

    const traces = generateTraces();
    const chips = generateChips();

    const pulses = [];
    const pulseSources = traces.filter((_, i) => i % 3 === 0).slice(0, 20);
    pulseSources.forEach(t => {
      pulses.push({
        trace: t,
        progress: Math.random(),
        speed: 0.0015 + Math.random() * 0.003,
        size: 2.5 + Math.random() * 2,
        color: Math.random() > 0.7 ? "#00ff9d" : "#00d4ff",
      });
    });

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      grad.addColorStop(0, "#050916");
      grad.addColorStop(0.5, "#080e1e");
      grad.addColorStop(1, "#040c18");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (let c = 0; c < cols + 1; c++) {
        for (let r = 0; r < rows + 1; r++) {
          ctx.beginPath();
          ctx.arc(c * G, r * G, 1, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(0, 212, 255, 0.07)";
          ctx.fill();
        }
      }

      chips.forEach(ch => {
        ctx.strokeStyle = "rgba(0, 212, 255, 0.09)";
        ctx.lineWidth = 0.75;
        ctx.setLineDash([]);
        ctx.strokeRect(ch.cx, ch.cy, ch.w, ch.h);
        for (let p = 0; p < ch.pins; p++) {
          const px = ch.cx + ((p + 1) * ch.w) / (ch.pins + 1);
          ctx.beginPath();
          ctx.moveTo(px, ch.cy);
          ctx.lineTo(px, ch.cy - 8);
          ctx.strokeStyle = "rgba(0, 212, 255, 0.08)";
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(px, ch.cy + ch.h);
          ctx.lineTo(px, ch.cy + ch.h + 8);
          ctx.stroke();
        }
        ctx.fillStyle = "rgba(0, 212, 255, 0.06)";
        ctx.font = "8px 'Share Tech Mono', monospace";
        ctx.fillText(`IC${Math.floor(Math.random() * 9000 + 1000)}`, ch.cx + 6, ch.cy + ch.h / 2);
      });

      const traceColor = isCritical
        ? "rgba(255,51,102,0.12)"
        : isWarning
          ? "rgba(255,170,0,0.10)"
          : "rgba(0,212,255,0.09)";

      const padColor = isCritical
        ? "rgba(255,51,102,0.2)"
        : isWarning
          ? "rgba(255,170,0,0.18)"
          : "rgba(0,212,255,0.18)";

      traces.forEach(t => {
        ctx.beginPath();
        ctx.moveTo(t.x1, t.y1);
        ctx.lineTo(t.x2, t.y2);
        ctx.strokeStyle = traceColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.stroke();
        [{ x: t.x1, y: t.y1 }, { x: t.x2, y: t.y2 }].forEach(pt => {
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 3, 0, Math.PI * 2);
          ctx.fillStyle = padColor;
          ctx.fill();
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 5, 0, Math.PI * 2);
          ctx.strokeStyle = padColor;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        });
      });

      pulses.forEach(p => {
        p.progress += p.speed;
        if (p.progress > 1) p.progress = 0;

        const t = p.trace;
        const x = t.x1 + (t.x2 - t.x1) * p.progress;
        const y = t.y1 + (t.y2 - t.y1) * p.progress;

        const radGrad = ctx.createRadialGradient(x, y, 0, x, y, p.size * 5);
        const pulseColor = isCritical ? "#ff3366" : p.color;
        radGrad.addColorStop(0, pulseColor.replace(")", ", 0.7)").replace("rgb", "rgba"));
        radGrad.addColorStop(1, "transparent");
        ctx.beginPath();
        ctx.arc(x, y, p.size * 5, 0, Math.PI * 2);
        ctx.fillStyle = radGrad;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = pulseColor;
        ctx.fill();

        const tx = t.x1 + (t.x2 - t.x1) * Math.max(0, p.progress - 0.06);
        const ty = t.y1 + (t.y2 - t.y1) * Math.max(0, p.progress - 0.06);
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(x, y);
        ctx.strokeStyle = pulseColor.includes("#")
          ? pulseColor + "66"
          : pulseColor.replace(")", ", 0.4)").replace("rgb", "rgba");
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      ctx.fillStyle = "rgba(0, 0, 0, 0.015)";
      for (let y = 0; y < canvas.height; y += 3) {
        ctx.fillRect(0, y, canvas.width, 1);
      }

      const blobGrad1 = ctx.createRadialGradient(canvas.width * 0.8, canvas.height * 0.15, 0, canvas.width * 0.8, canvas.height * 0.15, 350);
      blobGrad1.addColorStop(0, "rgba(74, 127, 255, 0.07)");
      blobGrad1.addColorStop(1, "transparent");
      ctx.fillStyle = blobGrad1;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const blobGrad2 = ctx.createRadialGradient(canvas.width * 0.1, canvas.height * 0.85, 0, canvas.width * 0.1, canvas.height * 0.85, 280);
      blobGrad2.addColorStop(0, "rgba(0, 212, 255, 0.05)");
      blobGrad2.addColorStop(1, "transparent");
      ctx.fillStyle = blobGrad2;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [isCritical, isWarning]);

  return (
    <canvas
      ref={canvasRef}
      style={{ position: "fixed", top: 0, left: 0, width: "100%", height: "100%", zIndex: 0, pointerEvents: "none" }}
    />
  );
};

/* ── TICKER BAR ───────────────────────────────────────────── */
const TickerBar = ({ history, color }) => {
  const last = history[history.length - 1] || {};
  const items = [
    `CPU ${(last.cpu || 0).toFixed(1)}%`,
    `MEM ${(last.memory || 0).toFixed(1)}%`,
    `DISK I/O ${(last.disk || 28).toFixed(1)}%`,
    `NET ${(last.network || 32).toFixed(1)}%`,
    `ANOMALY ${(last.anomaly || 0).toFixed(2)}`,
    `HEALTH ${(last.health || 100).toFixed(1)}%`,
    `UPTIME 99.7%`,
    `THREADS 142`,
    `LATENCY 4ms`,
  ];
  const text = items.join("   ·   ");
  return (
    <div style={{
      overflow: "hidden",
      borderTop: `1px solid ${T.border}`,
      borderBottom: `1px solid ${T.border}`,
      background: "rgba(0,0,0,0.3)",
      padding: "5px 0",
      marginBottom: "22px",
      position: "relative",
    }}>
      <div style={{
        display: "inline-block",
        whiteSpace: "nowrap",
        animation: "tickerSlide 20s linear infinite",
        fontSize: "10px",
        fontFamily: "'Share Tech Mono', monospace",
        color: T.textMuted,
        letterSpacing: "0.06em",
      }}>
        {text}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{text}
      </div>
    </div>
  );
};

/* ── MINI SPARKLINE ───────────────────────────────────────── */
const Sparkline = ({ data, color, width = 80, height = 28 }) => {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / (max - min || 1)) * height;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={pts.split(" ").pop().split(",")[0]} cy={pts.split(" ").pop().split(",")[1]} r="2.5" fill={color} />
    </svg>
  );
};

/* ── SYSTEM CORE ORB ──────────────────────────────────────── */
const SystemCore = ({ risk, level, color, health }) => {
  const isCritical = level === "CRITICAL";
  const isWarning = level === "WARNING";

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", marginBottom: "36px", padding: "16px 0" }}>
      <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{
          position: "absolute",
          width: "220px", height: "220px",
          borderRadius: "50%",
          border: `1px solid ${color}30`,
          animation: isCritical ? "criticalPulse 1s infinite" : "none",
        }} />
        <div style={{
          position: "absolute",
          width: "200px", height: "200px",
          borderRadius: "50%",
          border: `1px dashed ${color}25`,
        }}>
          <div style={{ position: "absolute", top: "50%", left: "50%", width: "8px", height: "8px", borderRadius: "50%", background: color, marginLeft: "-4px", marginTop: "-4px", animation: "orbitDot 4s linear infinite", boxShadow: `0 0 8px ${color}` }} />
          <div style={{ position: "absolute", top: "50%", left: "50%", width: "6px", height: "6px", borderRadius: "50%", background: T.success, marginLeft: "-3px", marginTop: "-3px", animation: "orbitDot2 4s linear infinite", boxShadow: `0 0 6px ${T.success}` }} />
          <div style={{ position: "absolute", top: "50%", left: "50%", width: "5px", height: "5px", borderRadius: "50%", background: T.primary, marginLeft: "-2.5px", marginTop: "-2.5px", animation: "orbitDot3 4s linear infinite", boxShadow: `0 0 5px ${T.primary}` }} />
        </div>

        <div style={{
          width: "160px", height: "160px",
          borderRadius: "50%",
          background: `radial-gradient(circle at 38% 38%, ${color}35 0%, ${color}12 40%, transparent 70%)`,
          border: `1.5px solid ${color}60`,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          backdropFilter: "blur(12px)",
          boxShadow: `0 0 60px ${color}40, inset 0 0 40px ${color}10, 0 0 120px ${color}20`,
          animation: isCritical ? "criticalGlow 1.5s infinite" : isWarning ? "warningGlow 2s infinite" : "pulseRing 3s ease-in-out infinite",
          position: "relative",
          zIndex: 1,
        }}>
          <div style={{
            position: "absolute", width: "130px", height: "130px",
            borderRadius: "50%", border: `1px solid ${color}20`,
          }} />
          <div style={{
            fontSize: "36px", fontWeight: 700, color,
            fontFamily: "'Rajdhani', sans-serif",
            textShadow: `0 0 20px ${color}`,
            lineHeight: 1,
          }}>
            {(risk * 100).toFixed(0)}%
          </div>
          <div style={{ fontSize: "9px", color: T.textMuted, fontFamily: "'Share Tech Mono', monospace", letterSpacing: "0.15em", marginTop: "4px" }}>
            SYSTEM RISK
          </div>
          <div style={{ marginTop: "6px", fontSize: "9px", fontFamily: "'Share Tech Mono', monospace", color, letterSpacing: "0.1em" }}>
            {level}
          </div>
        </div>

        <svg width="200" height="200" style={{ position: "absolute", top: "10px", left: "10px" }}>
          <circle cx="100" cy="100" r="88" fill="none" stroke={`${color}12`} strokeWidth="2" />
          <circle cx="100" cy="100" r="88" fill="none" stroke={color} strokeWidth="2"
            strokeDasharray={`${health * 5.53} 553`}
            strokeDashoffset="138"
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 4px ${color})`, transition: "stroke-dasharray 1s ease" }}
          />
          <text x="100" y="14" textAnchor="middle" fontSize="8" fill={T.textDim} fontFamily="'Share Tech Mono',monospace">
            HEALTH {health.toFixed(0)}%
          </text>
        </svg>
      </div>
    </div>
  );
};

/* ── STATUS BADGE ─────────────────────────────────────────── */
const StatusBadge = ({ level, color }) => (
  <div style={{
    display: "inline-flex", alignItems: "center", gap: "8px",
    padding: "8px 18px", borderRadius: "4px",
    background: `${color}10`,
    border: `1px solid ${color}80`,
    animation: level === "CRITICAL" ? "criticalGlow 1.5s infinite" : "none",
    fontFamily: "'Rajdhani', sans-serif",
  }}>
    <div style={{ width: "7px", height: "7px", borderRadius: "50%", background: color, boxShadow: `0 0 6px ${color}`, animation: "pulse 1.5s infinite" }} />
    <span style={{ fontSize: "13px", fontWeight: 700, color, letterSpacing: "0.12em" }}>{level}</span>
  </div>
);

/* ── METRIC CARD — enhanced with sparkline ────────────────── */
const MetricCard = ({ label, value, subtitle, trend, icon, tooltip, alert, sparkData, sparkColor }) => {
  const [hovered, setHovered] = useState(false);
  const [tip, setTip] = useState(false);

  return (
    <div
      style={{
        position: "relative",
        backdropFilter: "blur(20px)",
        background: alert ? "rgba(255,51,102,0.06)" : T.surface,
        padding: "18px 20px",
        borderRadius: "6px",
        border: `1px solid ${alert ? T.danger + "50" : T.border}`,
        transition: "all 0.25s cubic-bezier(0.4,0,0.2,1)",
        cursor: "pointer",
        animation: "slideIn 0.5s ease-out",
        transform: hovered ? "translateY(-4px) scale(1.01)" : "none",
        boxShadow: hovered
          ? `0 16px 48px rgba(0,0,0,0.5), 0 0 16px ${alert ? T.danger : T.accent}20`
          : alert ? `0 0 20px ${T.danger}15` : "none",
      }}
      onMouseEnter={() => { setHovered(true); setTip(true); }}
      onMouseLeave={() => { setHovered(false); setTip(false); }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
        <div style={{ fontSize: "10px", fontWeight: 600, color: T.textMuted, letterSpacing: "0.12em", textTransform: "uppercase", fontFamily: "'Share Tech Mono', monospace" }}>
          {label}
        </div>
        {icon && <div style={{ fontSize: "14px", opacity: 0.45 }}>{icon}</div>}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <div style={{ fontSize: "26px", fontWeight: 700, color: alert ? T.danger : T.text, marginBottom: "3px", fontFamily: "'Rajdhani', sans-serif", letterSpacing: "0.02em", textShadow: alert ? `0 0 12px ${T.danger}` : "none" }}>
            {value}
          </div>
          {subtitle && <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace" }}>{subtitle}</div>}
          {trend !== undefined && (
            <div style={{ marginTop: "4px", fontSize: "11px", color: trend > 0 ? T.success : T.danger, fontWeight: 600 }}>
              {trend > 0 ? "↗" : "↘"} {Math.abs(trend)}%
            </div>
          )}
        </div>
        {sparkData && <Sparkline data={sparkData} color={sparkColor || (alert ? T.danger : T.accent)} />}
      </div>
      {tip && tooltip && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 8px)", left: "50%", transform: "translateX(-50%)",
          background: "rgba(5,9,22,0.98)", border: `1px solid ${T.borderActive}`,
          borderRadius: "4px", padding: "10px 14px", fontSize: "11px", color: T.text,
          whiteSpace: "nowrap", zIndex: 1000, boxShadow: `0 8px 32px rgba(0,0,0,0.5)`,
          backdropFilter: "blur(12px)", animation: "slideIn 0.2s ease-out",
          fontFamily: "'Share Tech Mono', monospace",
        }}>
          {tooltip}
        </div>
      )}
    </div>
  );
};

/* ── SECTION CARD ─────────────────────────────────────────── */
const Section = ({ title, subtitle, children, alert, accentColor }) => (
  <div style={{
    backdropFilter: "blur(20px)",
    background: T.surface,
    padding: "22px",
    borderRadius: "6px",
    border: `1px solid ${alert ? T.danger + "50" : accentColor ? accentColor + "20" : T.border}`,
    boxShadow: alert ? `0 0 40px ${T.danger}15, 0 8px 32px rgba(0,0,0,0.3)` : "0 8px 32px rgba(0,0,0,0.2)",
    animation: "slideIn 0.5s ease-out",
    transition: "all 0.3s ease",
  }}>
    <div style={{ marginBottom: "18px" }}>
      <div style={{ fontSize: "11px", fontWeight: 700, color: accentColor || T.accent, letterSpacing: "0.12em", fontFamily: "'Share Tech Mono', monospace", marginBottom: "3px", textTransform: "uppercase" }}>
        ▸ {title}
      </div>
      {subtitle && <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace" }}>{subtitle}</div>}
    </div>
    {children}
  </div>
);

/* ── CUSTOM TOOLTIP ───────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "rgba(5,9,22,0.95)", border: `1px solid ${T.borderActive}`,
      borderRadius: "4px", padding: "8px 12px", fontSize: "10px",
      fontFamily: "'Share Tech Mono', monospace", color: T.text,
    }}>
      <div style={{ color: T.textDim, marginBottom: "4px" }}>
        {new Date(label).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.stroke, marginBottom: "2px" }}>
          {p.dataKey.toUpperCase()}: {typeof p.value === "number" ? p.value.toFixed(1) : p.value}%
        </div>
      ))}
    </div>
  );
};

/* ── AI COGNITIVE CORE CHAT ───────────────────────────────── */
const AIChat = ({ data, level, risk, decision }) => {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "COGNITIVE CORE ONLINE — Systems nominal. I monitor all subsystems in real-time. Query: status | anomaly | predict | recommend | why" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const chatRef = useRef(null);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim().toLowerCase();
    const origInput = input;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: origInput }]);
    setLoading(true);

    let internalResponse = null;
    if (userMsg.match(/status|health|ok|fine/)) {
      internalResponse = `SYSTEM STATUS: ${level} — Health: ${(data.health_score || 100).toFixed(1)}% — ${level === "CRITICAL" ? "⚠ IMMEDIATE ATTENTION REQUIRED" : level === "WARNING" ? "MONITORING ELEVATED ACTIVITY" : "ALL SUBSYSTEMS NOMINAL"}`;
    } else if (userMsg.match(/anomaly|problem|issue|error/)) {
      internalResponse = `ANOMALY SCAN: Score ${(data.anomaly_score || 0).toFixed(3)} — Risk ${(risk * 100).toFixed(0)}% — ${data.intelligence?.fusion?.cause || "No anomalies detected"}`;
    } else if (userMsg.match(/recommend|action|do|fix/)) {
      internalResponse = `DECISION ENGINE: "${decision?.action || "System Monitoring"}" — Confidence ${((decision?.confidence || 0) * 100).toFixed(0)}% — ${risk > 0.7 ? "Recommend immediate investigation" : risk > 0.4 ? "Continue elevated monitoring" : "No action required"}`;
    } else if (userMsg.match(/predict|future|will|next/)) {
      internalResponse = `TEMPORAL FORECAST: ${risk > 0.6 ? "CPU spike predicted ~12s. Stability degradation likely." : risk > 0.3 ? "Minor fluctuations expected. Self-stabilization probable." : "System stable projection for next 60s."} Failure probability: ${(risk * 120).toFixed(0)}%`;
    } else if (userMsg.match(/why|cause|reason|root/)) {
      internalResponse = `ROOT CAUSE ANALYSIS: ${data.intelligence?.fusion?.cause || "Operating within baseline parameters."} — Events logged: ${data.events?.length || 0}`;
    }

    if (internalResponse) {
      setTimeout(() => {
        setMessages(prev => [...prev, { role: "assistant", content: internalResponse }]);
        setLoading(false);
      }, 600);
    } else {
      try {
        const context = `System state: Health=${data.health_score || 100}%, CPU=${data.cpu_percent || 0}%, Memory=${data.memory || 0}%, Anomaly=${data.anomaly_score || 0}, Status=${level}, Decision="${decision?.action || 'None'}", Cause="${data.intelligence?.fusion?.cause || 'Unknown'}". User query: ${origInput}`;
        const res = await fetch("https://api.anthropic.com/v1/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: "claude-sonnet-4-20250514", max_tokens: 1000, messages: [{ role: "user", content: context }] }),
        });
        const result = await res.json();
        setMessages(prev => [...prev, { role: "assistant", content: result.content?.[0]?.text || "Analysis unavailable." }]);
      } catch {
        setMessages(prev => [...prev, { role: "assistant", content: `LOCAL INTELLIGENCE: ${data.intelligence?.fusion?.cause || "All systems nominal."}` }]);
      }
      setLoading(false);
    }
  }, [input, loading, data, level, risk, decision]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100%",
      backdropFilter: "blur(20px)", background: T.surface,
      borderRadius: "6px", border: `1px solid ${T.border}`, overflow: "hidden",
    }}>
      <div style={{ padding: "18px 20px", borderBottom: `1px solid ${T.border}`, background: "rgba(0,0,0,0.3)" }}>
        <div style={{ fontSize: "11px", fontWeight: 700, color: T.accent, fontFamily: "'Share Tech Mono', monospace", letterSpacing: "0.12em" }}>
          ◈ COGNITIVE CORE INTERFACE
        </div>
        <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginTop: "3px" }}>
          STATUS: CONNECTED TO SYSTEM INTELLIGENCE
        </div>
      </div>

      <div ref={chatRef} style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "88%",
            padding: "10px 14px",
            borderRadius: "4px",
            background: msg.role === "user"
              ? `linear-gradient(135deg, ${T.primary}cc, ${T.accent}bb)`
              : "rgba(0,212,255,0.05)",
            border: msg.role === "assistant" ? `1px solid ${T.border}` : "none",
            fontSize: "12px", lineHeight: "1.65", color: T.text,
            animation: "slideIn 0.3s ease-out",
            fontFamily: "'Share Tech Mono', monospace",
          }}>
            {msg.role === "assistant" && <span style={{ color: T.accent, marginRight: "6px" }}>◈</span>}
            {msg.content}
          </div>
        ))}
        {loading && (
          <div style={{
            alignSelf: "flex-start", padding: "10px 14px", borderRadius: "4px",
            background: "rgba(0,212,255,0.05)", border: `1px solid ${T.border}`,
            fontSize: "12px", color: T.accent, fontFamily: "'Share Tech Mono', monospace",
            animation: "pulse 1s infinite",
          }}>
            ◈ PROCESSING...
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div style={{ padding: "8px 16px", borderTop: `1px solid ${T.border}`, display: "flex", gap: "6px", flexWrap: "wrap" }}>
        {["status", "anomaly", "predict", "recommend"].map(cmd => (
          <button
            key={cmd}
            onClick={() => { setInput(cmd); }}
            style={{
              background: "rgba(0,212,255,0.06)", border: `1px solid ${T.border}`,
              borderRadius: "3px", padding: "3px 8px", fontSize: "9px",
              color: T.textMuted, cursor: "pointer", fontFamily: "'Share Tech Mono', monospace",
              letterSpacing: "0.06em", transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(0,212,255,0.14)"; e.currentTarget.style.color = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.background = "rgba(0,212,255,0.06)"; e.currentTarget.style.color = T.textMuted; }}
          >
            {cmd}
          </button>
        ))}
      </div>

      <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.border}`, background: "rgba(0,0,0,0.25)" }}>
        <div style={{ display: "flex", gap: "8px" }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && sendMessage()}
            placeholder="> QUERY SYSTEM..."
            style={{
              flex: 1, background: "rgba(0,212,255,0.04)",
              border: `1px solid ${T.border}`, borderRadius: "4px",
              padding: "9px 12px", color: T.text, fontSize: "12px", outline: "none",
              fontFamily: "'Share Tech Mono', monospace",
              letterSpacing: "0.04em",
            }}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            style={{
              background: `linear-gradient(135deg, ${T.primary}, ${T.accent})`,
              border: "none", borderRadius: "4px", padding: "0 18px",
              color: "#050916", fontSize: "12px", fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading || !input.trim() ? 0.4 : 1,
              fontFamily: "'Rajdhani', sans-serif", letterSpacing: "0.08em",
              transition: "all 0.2s",
            }}
          >
            SEND
          </button>
        </div>
      </div>
    </div>
  );
};

/* ── EVENT LOG ────────────────────────────────────────────── */
const EventLog = ({ events }) => {
  const demo = [
    { severity: "INFO", message: "System heartbeat nominal", timestamp: "00:01" },
    { severity: "MEDIUM", message: "Memory usage elevated 68%", timestamp: "00:05" },
    { severity: "HIGH", message: "CPU anomaly detected — burst pattern", timestamp: "00:12" },
    { severity: "INFO", message: "Load balancer redistributed tasks", timestamp: "00:18" },
  ];
  const items = (events && events.length > 0) ? events : demo;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
      {items.slice(0, 7).map((e, i) => {
        const color = e.severity === "CRITICAL" ? T.danger : e.severity === "HIGH" ? T.warning : e.severity === "MEDIUM" ? T.accent : T.textDim;
        return (
          <div key={i} style={{
            padding: "9px 12px", borderRadius: "4px",
            background: "rgba(0,0,0,0.25)",
            borderLeft: `2px solid ${color}`,
            fontSize: "11px", color: T.text,
            fontFamily: "'Share Tech Mono', monospace",
            animation: `slideIn ${0.3 + i * 0.08}s ease-out`,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
              <span style={{ fontWeight: 700, color, fontSize: "10px" }}>{e.severity}</span>
              <span style={{ fontSize: "9px", color: T.textDim }}>{e.timestamp || "NOW"}</span>
            </div>
            <div style={{ color: T.textMuted, fontSize: "10px" }}>{e.message}</div>
          </div>
        );
      })}
    </div>
  );
};

/* ── DATA STREAM BAR ──────────────────────────────────────── */
const DataBar = ({ value, color, label, max = 100 }) => {
  const pct = Math.min(100, (value / max) * 100);
  const isHigh = pct > 75;
  const barColor = isHigh ? T.danger : pct > 50 ? T.warning : color;
  return (
    <div style={{ marginBottom: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", fontFamily: "'Share Tech Mono', monospace", marginBottom: "5px" }}>
        <span style={{ color: T.textMuted }}>{label}</span>
        <span style={{ color: barColor, fontWeight: 700 }}>{value.toFixed(1)}%</span>
      </div>
      <div style={{ height: "7px", borderRadius: "2px", background: "rgba(0,0,0,0.5)", overflow: "hidden", position: "relative" }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: `linear-gradient(90deg, ${color}99, ${barColor})`,
          boxShadow: `0 0 12px ${barColor}70`,
          transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)",
          borderRadius: "2px",
        }} />
        {/* tick marks at 25/50/75% */}
        {[25, 50, 75].map(tick => (
          <div key={tick} style={{
            position: "absolute", top: 0, left: `${tick}%`,
            width: "1px", height: "100%",
            background: "rgba(255,255,255,0.06)",
          }} />
        ))}
      </div>
    </div>
  );
};

/* ── UPTIME INDICATOR ─────────────────────────────────────── */
const UptimeDots = ({ count = 30, health }) => {
  const dots = Array.from({ length: count }, (_, i) => {
    const isRecent = i >= count - 3;
    const rand = Math.random();
    const ok = isRecent ? health > 70 : rand > 0.08;
    return ok;
  });
  return (
    <div style={{ display: "flex", gap: "3px", flexWrap: "wrap" }}>
      {dots.map((ok, i) => (
        <div key={i} style={{
          width: "7px", height: "18px", borderRadius: "1px",
          background: ok ? T.success : T.danger,
          opacity: ok ? (0.4 + (i / count) * 0.6) : 0.8,
          boxShadow: ok ? `0 0 4px ${T.success}40` : `0 0 4px ${T.danger}60`,
        }} />
      ))}
    </div>
  );
};

/* ── MAIN DASHBOARD ──────────────────────────────────────── */
export default function Dashboard() {
  const [data, setData] = useState({});
  const [history, setHistory] = useState([]);
  const [manualAction, setManualAction] = useState(null);
  const prevLevel = useRef("OPTIMAL");

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("http://localhost:8000/os/status");
        const json = await res.json();
        console.log("[AIOps] Backend response:", json);
        setData(json);
        const newPoint = {
          time: Date.now(),
          label: new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          cpu: json.cpu_percent || 0,
          memory: json.memory || 0,
          // ✅ Clean fallback: flat field first, then nested (already %-scaled), else default
          disk: json.disk_percent ?? (json.intelligence?.features?.disk ?? 0.28) * 100,
          network: json.network_percent ?? (json.intelligence?.features?.network ?? 0.32) * 100,
          anomaly: Math.min(100, (json.anomaly_score ?? json.intelligence?.anomaly_score ?? 0) * 100),
          health: json.health_score || 100,
        };
        console.log("[AIOps] Last history point:", newPoint);
        setHistory(prev => [...prev.slice(-39), newPoint]);
      } catch {
        // Demo mode: realistic simulated data
        const t = Date.now() / 1000;
        const newPoint = {
          time: Date.now(),
          label: new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          cpu: Math.max(5, Math.min(95, 35 + Math.sin(t * 0.3) * 18 + Math.random() * 10)),
          memory: Math.max(10, Math.min(90, 48 + Math.cos(t * 0.2) * 12 + Math.random() * 6)),
          disk: Math.max(5, Math.min(80, 28 + Math.sin(t * 0.15) * 8 + Math.random() * 4)),
          network: Math.max(2, Math.min(70, 32 + Math.cos(t * 0.4) * 10 + Math.random() * 5)),
          anomaly: Math.max(0, Math.min(100, Math.sin(t * 0.5) * 18 + Math.random() * 8 + 5)),
          health: Math.max(60, Math.min(100, 90 + Math.sin(t * 0.1) * 6)),
        };
        setHistory(prev => [...prev.slice(-39), newPoint]);
      }
    };
    fetchData();
    // ✅ 500ms — fast enough to capture real CPU fluctuations
    const id = setInterval(fetchData, 500);
    return () => clearInterval(id);
  }, []);

  // ── Derived state ──
  const health = data.health_score || (history[history.length - 1]?.health ?? 92);
  // ✅ FIXED: read anomaly_score from top-level first, then fallback
  const anomaly = data.anomaly_score || data.intelligence?.anomaly_score || 0;
  const stability = data.intelligence?.stability || data.stability || 0.97;
  const decision = data.latest_decision || {};
  // ✅ Weighted risk: anomaly gets 70% weight, health degradation 30% — smoother, less spike-sensitive
  const risk = Math.min(1, anomaly * 0.7 + (100 - health) / 100 * 0.3);
  const level = risk > 0.75 ? "CRITICAL" : risk > 0.45 ? "WARNING" : "OPTIMAL";
  const color = level === "CRITICAL" ? T.danger : level === "WARNING" ? T.warning : T.success;
  const isCritical = level === "CRITICAL";
  const isWarning = level === "WARNING";

  useEffect(() => {
    if (level === "CRITICAL" && prevLevel.current !== "CRITICAL") {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [880, 660, 880].forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain); gain.connect(ctx.destination);
          osc.frequency.value = freq;
          gain.gain.value = 0.07;
          osc.start(ctx.currentTime + i * 0.18);
          osc.stop(ctx.currentTime + i * 0.18 + 0.14);
        });
      } catch {}
    }
    prevLevel.current = level;
  }, [level]);

  const lastHistory = history[history.length - 1] || { cpu: 0, memory: 0, disk: 28, network: 32 };

  const radarData = [
    { subject: "CPU", value: lastHistory.cpu || 30 },
    { subject: "Memory", value: lastHistory.memory || 45 },
    { subject: "Disk", value: lastHistory.disk || 28 },
    { subject: "Network", value: lastHistory.network || 32 },
    // ✅ FIXED: anomaly already scaled 0-100
    { subject: "Anomaly", value: lastHistory.anomaly || 5 },
    { subject: "Stability", value: stability * 100 },
  ];

  const learnedPatterns = data.patterns || [
    { type: "CPU Spike Pattern", severity: "HIGH", frequency: "Every 15min" },
    { type: "Memory Leak Pattern", severity: "MEDIUM", frequency: "Daily" },
    { type: "Network Congestion", severity: "LOW", frequency: "Peak hours" },
    { type: "Disk I/O Saturation", severity: "MEDIUM", frequency: "Batch jobs" },
  ];

  // Sparkline history slices
  const cpuSpark = history.slice(-20).map(h => h.cpu);
  const memSpark = history.slice(-20).map(h => h.memory);
  const anomalySpark = history.slice(-20).map(h => h.anomaly);

  return (
    <>
      <style>{STYLES}</style>
      <CircuitBg isCritical={isCritical} isWarning={isWarning} />

      {/* CRT scanline sweep */}
      <div style={{
        position: "fixed", left: 0, width: "100%", height: "3px", zIndex: 999, pointerEvents: "none",
        background: "linear-gradient(transparent, rgba(0,212,255,0.04) 50%, transparent)",
        animation: "scanline 6s linear infinite",
      }} />

      <div style={{
        position: "relative", zIndex: 1, minHeight: "100vh", padding: "28px 32px",
        color: T.text, fontFamily: "'Rajdhani', sans-serif",
        filter: isCritical ? "brightness(1.06)" : "brightness(1)",
        transition: "filter 0.5s ease",
      }}>

        {/* HEADER */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px", animation: "slideIn 0.4s ease-out" }}>
          <div>
            <div style={{
              fontSize: "26px", fontWeight: 700, letterSpacing: "0.06em",
              fontFamily: "'Rajdhani', sans-serif",
              color: T.accent,
              textShadow: `0 0 30px ${T.accentGlow}`,
              marginBottom: "3px",
            }}>
              ◈ COGNITIVE AIOPS ENGINE
            </div>
            <div style={{ fontSize: "11px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", letterSpacing: "0.08em" }}>
              REAL-TIME AUTONOMOUS SYSTEM INTELLIGENCE v2.4.1
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
            {/* Live indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "10px", fontFamily: "'Share Tech Mono', monospace", color: T.textDim }}>
              <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: T.success, animation: "pulse 1.5s infinite", boxShadow: `0 0 6px ${T.success}` }} />
              LIVE
            </div>
            <div style={{ fontSize: "10px", fontFamily: "'Share Tech Mono', monospace", color: T.textDim, textAlign: "right" }}>
              <div>{new Date().toLocaleDateString()}</div>
              <div style={{ color: T.accent }}>{new Date().toLocaleTimeString()}</div>
            </div>
            <StatusBadge level={level} color={color} />
          </div>
        </div>

        {/* TICKER */}
        <TickerBar history={history} color={color} />

        {/* SYSTEM CORE ORB */}
        <SystemCore risk={risk} level={level} color={color} health={health} />

        {/* METRICS */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px", marginBottom: "24px" }}>
          <MetricCard
            label="System Health"
            value={`${health.toFixed(1)}%`}
            subtitle="Composite operational status"
            icon="♥"
            tooltip="Composite of CPU, memory, disk, network health"
            alert={health < 80}
            sparkData={history.slice(-20).map(h => h.health)}
            sparkColor={health < 80 ? T.danger : T.success}
          />
          <MetricCard
            label="Anomaly Score"
            value={anomaly.toFixed(3)}
            subtitle={`Risk: ${(risk * 100).toFixed(0)}%`}
            icon="⚠"
            tooltip="ML deviation from baseline behavioral patterns"
            alert={risk > 0.5}
            sparkData={anomalySpark}
            sparkColor={risk > 0.5 ? T.danger : T.warning}
          />
          <MetricCard
            label="System Stability"
            value={`${(stability * 100).toFixed(1)}%`}
            subtitle="Predictive confidence index"
            icon="◈"
            tooltip="Statistical measure of system predictability"
            sparkData={history.slice(-20).map(() => stability * 100 + (Math.random() - 0.5) * 2)}
            sparkColor={T.primary}
          />
          <MetricCard
            label="AI Decision"
            value={decision?.action || "MONITORING"}
            subtitle={`Confidence: ${((decision?.confidence || 0) * 100).toFixed(0)}%`}
            icon="▸"
            tooltip="Latest autonomous action by cognitive engine"
          />
        </div>

        {/* MAIN GRID */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 380px", gap: "20px", alignItems: "start" }}>

          {/* LEFT COLUMN */}
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

            <Section title="Performance Timeline" subtitle="40-point rolling window · 500ms resolution">
              <div style={{ height: "200px" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history} margin={{ left: 0, right: 8, top: 10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="gCpu" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="#00d4ff" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="gMem" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={T.primary} stopOpacity={0.4} />
                        <stop offset="100%" stopColor={T.primary} stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="gAno" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                        <stop offset="100%" stopColor={color} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#0f2a44" vertical={false} />
                    <XAxis
                      dataKey="time"
                      type="number"
                      scale="time"
                      domain={["auto", "auto"]}
                      tickFormatter={t => new Date(t).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      stroke={T.textDim}
                      fontSize={9}
                      tick={{ fontFamily: "'Share Tech Mono', monospace" }}
                      tickCount={5}
                    />
                    <YAxis stroke={T.textDim} fontSize={9} tick={{ fontFamily: "'Share Tech Mono', monospace" }} domain={[0, 100]} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="cpu" stroke={T.accent} fill="url(#gCpu)" strokeWidth={2} dot={false} isAnimationActive={true} animationDuration={400} />
                    <Area type="monotone" dataKey="memory" stroke={T.primary} fill="url(#gMem)" strokeWidth={1.5} dot={false} isAnimationActive={true} animationDuration={400} />
                    <Area type="monotone" dataKey="anomaly" stroke={color} fill="url(#gAno)" strokeWidth={2} dot={false} isAnimationActive={true} animationDuration={400} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div style={{ marginTop: "12px", display: "flex", gap: "20px", fontSize: "10px", fontFamily: "'Share Tech Mono', monospace" }}>
                {[{ color: T.accent, label: "CPU LOAD" }, { color: T.primary, label: "MEMORY" }, { color, label: "ANOMALY" }].map((l, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <div style={{ width: "16px", height: "2.5px", background: l.color, borderRadius: "1px", boxShadow: `0 0 6px ${l.color}` }} />
                    <span style={{ color: T.textMuted }}>{l.label}</span>
                  </div>
                ))}
              </div>
            </Section>

            {/* Uptime History */}
            <Section title="Uptime History" subtitle="Last 30 check intervals">
              <UptimeDots count={30} health={health} />
              <div style={{ marginTop: "10px", display: "flex", justifyContent: "space-between", fontSize: "10px", fontFamily: "'Share Tech Mono', monospace", color: T.textDim }}>
                <span>30 intervals ago</span>
                <span style={{ color: T.success }}>99.7% uptime</span>
                <span>now</span>
              </div>
            </Section>

            {/* Future State Projection */}
            <Section title="Future State Projection" subtitle="AI temporal simulation · next 60s" alert={risk > 0.6}>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "11px", fontFamily: "'Share Tech Mono', monospace" }}>
                {[
                  { label: risk > 0.6 ? "⚠ CPU SPIKE PREDICTED ~12s" : "✓ CPU STABLE PROJECTION", ok: risk <= 0.6 },
                  { label: risk > 0.5 ? "⚠ STABILITY DEGRADATION EXPECTED" : "✓ STABILITY MAINTAINED", ok: risk <= 0.5 },
                  { label: `◈ FAILURE PROBABILITY: ${(risk * 120).toFixed(0)}%`, highlight: true },
                ].map((item, i) => (
                  <div key={i} style={{
                    padding: "10px 12px", borderRadius: "4px",
                    background: item.highlight ? "rgba(0,212,255,0.05)" : item.ok ? "rgba(0,255,157,0.04)" : "rgba(255,51,102,0.06)",
                    border: `1px solid ${item.highlight ? T.accent + "30" : item.ok ? T.success + "30" : T.danger + "30"}`,
                    color: item.highlight ? T.accent : item.ok ? T.success : T.danger,
                    fontWeight: item.highlight ? 700 : 400,
                  }}>
                    {item.label}
                  </div>
                ))}
              </div>
            </Section>

            {/* Signal Radar */}
            <Section title="System Signal Map" subtitle="Multimodal state radar">
              <div style={{ height: "210px" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke={T.border} />
                    <PolarAngleAxis dataKey="subject" stroke={T.textMuted} fontSize={10} tick={{ fontFamily: "'Share Tech Mono', monospace" }} />
                    <Radar dataKey="value" stroke={color} fill={color} fillOpacity={0.18} strokeWidth={2} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <div style={{ marginTop: "8px", fontSize: "10px", color: T.textDim, textAlign: "center", fontFamily: "'Share Tech Mono', monospace" }}>
                IMBALANCE: {risk > 0.5 ? "HIGH VARIANCE DETECTED" : "BALANCED STATE"}
              </div>
            </Section>
          </div>

          {/* MIDDLE COLUMN */}
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>

            {/* Resource Monitor */}
            <Section title="Resource Monitor" subtitle="Live subsystem utilization">
              <DataBar value={lastHistory.cpu || 35} color={T.accent} label="CPU CORES" />
              <DataBar value={lastHistory.memory || 48} color={T.primary} label="MEMORY" />
              <DataBar value={lastHistory.disk || 28} color={T.success} label="DISK I/O" />
              <DataBar value={lastHistory.network || 32} color={T.warning} label="NETWORK" />
              <div style={{ marginTop: "14px" }}>
                <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginBottom: "6px", display: "flex", justifyContent: "space-between" }}>
                  <span>RISK FIELD</span>
                  <span style={{ color }}>LEVEL: {level}</span>
                </div>
                <div style={{ height: "10px", borderRadius: "2px", background: "rgba(0,0,0,0.4)", overflow: "hidden", position: "relative" }}>
                  <div style={{
                    width: `${risk * 100}%`, height: "100%",
                    background: `linear-gradient(90deg, ${T.success}, ${T.warning}, ${color})`,
                    boxShadow: `0 0 16px ${color}80`,
                    transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)",
                  }} />
                  {[25, 50, 75].map(tick => (
                    <div key={tick} style={{ position: "absolute", top: 0, left: `${tick}%`, width: "1px", height: "100%", background: "rgba(255,255,255,0.1)" }} />
                  ))}
                </div>
                <div style={{ fontSize: "10px", color, fontFamily: "'Share Tech Mono', monospace", marginTop: "4px" }}>
                  {(risk * 100).toFixed(1)}%
                </div>
              </div>
            </Section>

            {/* AI Reasoning */}
            <Section title="AI Reasoning Engine" subtitle="Autonomous decision core" alert={risk > 0.7} accentColor={color}>
              <div style={{ background: "rgba(0,0,0,0.35)", padding: "14px", borderRadius: "4px", marginBottom: "14px", border: `1px solid ${T.border}` }}>
                <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginBottom: "6px" }}>ACTIVE DECISION</div>
                <div style={{ fontSize: "22px", fontWeight: 700, color: T.accent, marginBottom: "10px", fontFamily: "'Rajdhani', sans-serif", letterSpacing: "0.05em" }}>
                  {decision?.action || "SYSTEM MONITORING"}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "11px", fontFamily: "'Share Tech Mono', monospace" }}>
                  <div><div style={{ color: T.textDim, marginBottom: "3px" }}>CONFIDENCE</div><div style={{ color: T.success, fontWeight: 700 }}>{((decision?.confidence || 0) * 100).toFixed(1)}%</div></div>
                  <div><div style={{ color: T.textDim, marginBottom: "3px" }}>PRIORITY</div><div style={{ color: T.warning, fontWeight: 700 }}>{decision?.priority || "NORMAL"}</div></div>
                </div>
              </div>
              <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginBottom: "6px" }}>CONFIDENCE FIELD</div>
              <div style={{ height: "8px", borderRadius: "2px", background: "rgba(0,0,0,0.4)", overflow: "hidden", marginBottom: "14px" }}>
                <div style={{ width: `${(decision?.confidence || 0) * 100}%`, height: "100%", background: `linear-gradient(90deg, ${T.success}, ${T.accent})`, boxShadow: `0 0 12px ${T.success}80`, transition: "width 0.8s ease", borderRadius: "2px" }} />
              </div>
              <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginBottom: "6px" }}>ROOT CAUSE ANALYSIS</div>
              <div style={{ background: "rgba(0,0,0,0.25)", padding: "12px", borderRadius: "4px", fontSize: "11px", color: T.text, lineHeight: "1.7", fontFamily: "'Share Tech Mono', monospace", borderLeft: `2px solid ${color}` }}>
                {data.intelligence?.fusion?.cause || "No anomalies detected — system operating within baseline parameters."}
              </div>
            </Section>

            {/* Causal Chain */}
            <Section title="Causal Correlation" subtitle="Signal dependency chain">
              <div style={{ fontSize: "11px", fontFamily: "'Share Tech Mono', monospace" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
                  {[{ label: "CPU ↑", color: T.accent }, { label: "→", color: T.textDim }, { label: "MEM ↑", color: T.warning }, { label: "→", color: T.textDim }, { label: "ANOMALY ↑", color: T.danger }].map((s, i) => (
                    <span key={i} style={{ color: s.color, fontWeight: 700 }}>{s.label}</span>
                  ))}
                </div>
                <div style={{ padding: "10px 12px", background: "rgba(0,0,0,0.3)", borderRadius: "4px", borderLeft: `2px solid ${T.accent}` }}>
                  → DECISION: <span style={{ color: T.accent, fontWeight: 700 }}>{decision?.action || "MONITOR"}</span>
                </div>
              </div>
            </Section>

            {/* Learned Patterns */}
            <Section title="Learned Patterns" subtitle="Historical intelligence database">
              <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
                {learnedPatterns.slice(0, 4).map((p, i) => {
                  const pc = p.severity === "HIGH" ? T.danger : p.severity === "MEDIUM" ? T.warning : T.accent;
                  return (
                    <div key={i} style={{ padding: "9px 12px", borderRadius: "4px", background: "rgba(0,0,0,0.2)", borderLeft: `2px solid ${pc}`, fontSize: "11px", fontFamily: "'Share Tech Mono', monospace" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                        <span style={{ color: T.text, fontWeight: 600 }}>{p.type}</span>
                        <span style={{ color: pc, fontSize: "10px" }}>{p.severity}</span>
                      </div>
                      <div style={{ fontSize: "10px", color: T.textDim }}>FREQ: {p.frequency}</div>
                    </div>
                  );
                })}
              </div>
            </Section>

            {/* Manual Override */}
            <Section title="Manual Override" subtitle="Operator intervention console">
              <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
                {[
                  { label: "EMERGENCY STABILIZE", color: T.danger, action: "Emergency Stabilize — INITIATED", icon: "⚡" },
                  { label: "RESOURCE REBALANCE", color: T.warning, action: "Resource Rebalance — EXECUTING", icon: "◈" },
                  { label: "ENABLE AUTO-PILOT", color: T.accent, action: "AI Auto-Pilot — ENABLED", icon: "▸" },
                ].map((btn, i) => (
                  <button
                    key={i}
                    onClick={() => setManualAction(btn.action)}
                    style={{
                      background: `${btn.color}15`,
                      border: `1px solid ${btn.color}60`,
                      borderRadius: "4px", padding: "11px 16px",
                      color: btn.color, fontSize: "12px", fontWeight: 700,
                      cursor: "pointer", fontFamily: "'Rajdhani', sans-serif",
                      letterSpacing: "0.1em", textAlign: "left",
                      transition: "all 0.2s cubic-bezier(0.4,0,0.2,1)",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.transform = "scale(1.02)"; e.currentTarget.style.background = `${btn.color}25`; e.currentTarget.style.boxShadow = `0 0 20px ${btn.color}30`; }}
                    onMouseLeave={e => { e.currentTarget.style.transform = "scale(1)"; e.currentTarget.style.background = `${btn.color}15`; e.currentTarget.style.boxShadow = "none"; }}
                  >
                    {btn.icon} {btn.label}
                  </button>
                ))}
                {manualAction && (
                  <div style={{
                    padding: "9px 12px", borderRadius: "4px",
                    background: "rgba(0,255,157,0.07)", border: `1px solid ${T.success}50`,
                    fontSize: "11px", color: T.success,
                    fontFamily: "'Share Tech Mono', monospace",
                    animation: "slideIn 0.3s ease-out",
                  }}>
                    ✓ {manualAction}
                  </div>
                )}
              </div>
            </Section>

            <Section title="System Events" subtitle="Chronological event log">
              <EventLog events={data.events} />
            </Section>
          </div>

          {/* RIGHT COLUMN — AI CHAT */}
          <div style={{ position: "sticky", top: "28px", height: "calc(100vh - 56px)" }}>
            <AIChat data={data} level={level} risk={risk} decision={decision} />
          </div>
        </div>
      </div>
    </>
  );
}
