import { useEffect, useState, useRef, useCallback, type ReactNode } from "react";
import { api } from "../services/api";
import { fetchCognitivePredictions, acknowledgeCognitivePrediction, resolveCognitivePrediction } from "../services/api";
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
interface CircuitBgProps {
  isCritical: boolean;
  isWarning: boolean;
}

interface CircuitTrace {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface CircuitChip {
  cx: number;
  cy: number;
  w: number;
  h: number;
  pins: number;
}

interface CircuitPulse {
  trace: CircuitTrace;
  progress: number;
  speed: number;
  size: number;
  color: string;
}

const CircuitBg = ({ isCritical, isWarning }: CircuitBgProps) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

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
      const traces: CircuitTrace[] = [];
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
      const chips: CircuitChip[] = [];
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

    const pulses: CircuitPulse[] = [];
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
      if (animRef.current !== null) {
        cancelAnimationFrame(animRef.current);
      }
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
interface TickerBarProps {
  history: HistoryPoint[];
  color?: string;
}

const TickerBar = ({ history }: TickerBarProps) => {
  const last = history[history.length - 1] || {};
  const items = history.length > 0
    ? [
        `CPU ${last.cpu.toFixed(1)}%`,
        `MEM ${last.memory.toFixed(1)}%`,
        `DISK I/O ${last.disk.toFixed(1)}%`,
        `NET ${last.network.toFixed(1)}%`,
        `ANOMALY ${last.anomaly.toFixed(2)}`,
        `HEALTH ${last.health.toFixed(1)}%`,
      ]
    : [
        "CPU —",
        "MEM —",
        "DISK I/O —",
        "NET —",
        "ANOMALY —",
        "HEALTH —",
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
interface SparklineProps {
  data: number[];
  color: string;
  width?: number;
  height?: number;
}

const Sparkline = ({ data, color, width = 80, height = 28 }: SparklineProps) => {
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
      {(() => {
        const lastPoint = pts.split(" ").pop() ?? "0,0";
        const [lastX, lastY] = lastPoint.split(",");
        return <circle cx={lastX} cy={lastY} r="2.5" fill={color} />;
      })()}
    </svg>
  );
};

/* ── SYSTEM CORE ORB ──────────────────────────────────────── */
interface SystemCoreProps {
  risk: number;
  level: string;
  color: string;
  health: number;
}

const SystemCore = ({ risk, level, color, health }: SystemCoreProps) => {
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
interface StatusBadgeProps {
  level: string;
  color: string;
}

const StatusBadge = ({ level, color }: StatusBadgeProps) => (
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
interface MetricCardProps {
  label: string;
  value: string;
  subtitle: string;
  trend?: number;
  icon: string;
  tooltip: string;
  alert?: boolean;
  sparkData?: number[];
  sparkColor?: string;
}

const MetricCard = ({
  label,
  value,
  subtitle,
  trend,
  icon,
  tooltip,
  alert = false,
  sparkData = [],
  sparkColor = T.accent,
}: MetricCardProps) => {
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
interface SectionProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  alert?: boolean;
  accentColor?: string;
}

const Section = ({
  title,
  subtitle,
  children,
  alert = false,
  accentColor = T.accent,
}: SectionProps) => (
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
interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{
    name?: string;
    value?: number | string;
    stroke?: string;
    dataKey?: string;
  }>;
  label?: string | number;
}

const ChartTooltip = ({ active, payload, label }: ChartTooltipProps) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "rgba(5,9,22,0.95)", border: `1px solid ${T.borderActive}`,
      borderRadius: "4px", padding: "8px 12px", fontSize: "10px",
      fontFamily: "'Share Tech Mono', monospace", color: T.text,
    }}>
      <div style={{ color: T.textDim, marginBottom: "4px" }}>
        {label != null
          ? new Date(label).toLocaleTimeString("en-US", {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })
          : "--:--:--"}
      </div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.stroke, marginBottom: "2px" }}>
          {(p.dataKey ?? p.name ?? "value").toUpperCase()}: {typeof p.value === "number" ? p.value.toFixed(1) : p.value}%
        </div>
      ))}
    </div>
  );
};

/* ── AI COGNITIVE CORE CHAT ───────────────────────────────── */
const AIChat = () => {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "COGNITIVE CORE ONLINE — Systems nominal. I monitor all subsystems in real-time. Query: status | anomaly | predict | recommend | why" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const chatRef = useRef<HTMLDivElement | null>(null);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || loading) return;

    const origInput = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: origInput }]);
    setLoading(true);

    try {
      const response = await api.post("/chat", { query: origInput });
      const result = response.data;

      let content = "Analysis unavailable.";

      if (result.mode === "status") {
        content =
          `SYSTEM STATUS: CPU ${result.cpu ?? "—"}% · ` +
          `MEM ${result.memory ?? "—"}% · ` +
          `DISK ${result.disk ?? "—"}%\n` +
          `Decision: ${result.decision ?? "None"}\n` +
          `Root cause: ${result.root_cause ?? "Unknown"}`;
      } else if (result.mode === "confirm") {
        content = result.message ?? "The backend requires confirmation before execution.";
      } else if (result.mode === "executed") {
        content = result.message ?? "Action execution completed.";
      } else if (result.mode === "cancelled") {
        content = result.message ?? "Action cancelled.";
      } else if (result.mode === "info") {
        content = result.message ?? "No additional information available.";
      } else if (result.mode === "explain" && result.structured) {
        const structured = result.structured;
        content =
          `SUMMARY: ${structured.summary ?? "—"}\n\n` +
          `ROOT CAUSE: ${structured.root_cause ?? "—"}\n\n` +
          `EXPLANATION: ${structured.explanation ?? "—"}\n\n` +
          `RECOMMENDED ACTION: ${structured.recommended_action ?? "—"}\n` +
          `CONFIDENCE: ${
            structured.confidence !== undefined
              ? `${(structured.confidence * 100).toFixed(0)}%`
              : "—"
          }`;
      } else if (result.mode === "fallback") {
        content = result.response ?? "Analysis unavailable.";
      } else if (result.message) {
        content = result.message;
      }

      setMessages(prev => [
        ...prev,
        { role: "assistant", content }
      ]);
    } catch (error) {
      console.error("[AIOps] Cognitive chat request failed:", error);
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: "COGNITIVE CORE ERROR — Backend chat service unavailable."
        }
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading]);


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
interface SystemEvent {
  type?: string;
  event?: string;
  message?: string;
  severity?: string;
  timestamp?: string | number;
  time?: string | number;
  [key: string]: unknown;
}

interface EventLogProps {
  events?: SystemEvent[];
}

const EventLog = ({ events }: EventLogProps) => {
  const items = events ?? [];

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
interface DataBarProps {
  value: number;
  color: string;
  label: string;
  max?: number;
}

const DataBar = ({ value, color, label, max = 100 }: DataBarProps) => {
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

/* ── HEALTH CHECK HISTORY ─────────────────────────────────── */
interface UptimeDotsProps {
  history: HistoryPoint[];
}

const UptimeDots = ({ history }: UptimeDotsProps) => {
  const points = history.slice(-30);

  return (
    <div style={{ display: "flex", gap: "3px", flexWrap: "wrap" }}>
      {points.map((point, i) => {
        const health = point.health ?? 0;
        const ok = health > 70;

        return (
          <div key={i} style={{
            width: "7px", height: "18px", borderRadius: "1px",
            background: ok ? T.success : T.danger,
            opacity: 0.4 + ((i + 1) / Math.max(points.length, 1)) * 0.6,
            boxShadow: ok ? `0 0 4px ${T.success}40` : `0 0 4px ${T.danger}60`,
          }} />
        );
      })}
    </div>
  );
};

/* ── BACKEND TELEMETRY TYPES ─────────────────────────────── */
interface PipelineData {
  decision?: {
    action?: string;
    risk_level?: string;
    confidence?: number;
    auto_execute?: boolean;
    requires_confirmation?: boolean;
    executable?: boolean;
    timestamp?: string;
    root_cause?: {
      type?: string;
      process?: string | null;
      confidence?: number;
      severity?: number;
      evidence?: string[];
      recommended_action?: string;
    } | null;
  };
  system_risk?: number;
  root_cause?: string | null;
  causal?: {
    primary_cause?: string | null;
  };
  prediction?: {
    type?: string;
    confidence?: number;
  };
}

interface ForecastData {
  summary?: string;
  direction?: string;
  peak_risk?: string;
  first_risk_at?: number | null;
  confidence?: number;
  confidence_label?: string;
  trustworthy?: boolean;
  trend_insights?: Array<{
    metric?: string;
    direction?: string;
    rate?: string;
    concern?: boolean;
    detail?: string;
  }>;
  what_to_watch?: string[];
  data_age_minutes?: number;
  points?: Array<{
    t?: number;
    cpu?: number;
    memory?: number;
    anomaly?: number;
    risk?: string;
    label?: string;
    explanation?: string;
  }>;
}

interface SystemStatus {
  cpu_percent?: number;
  memory?: number;
  disk_percent?: number;
  network_percent?: number;
  anomaly_score?: number;
  health_score?: number;
  severity?: string;
  reason?: string;
  latest_decision?: {
    action?: string;
    confidence?: number;
    priority?: string;
  };
  intelligence?: {
    anomaly_score?: number;
    stability?: number;
    features?: {
      disk?: number;
      network?: number;
    };
    fusion?: {
      cause?: string;
    };
  };
  patterns?: Array<{
    type?: string;
    severity?: string;
    frequency?: string;
    [key: string]: unknown;
  }>;
  events?: SystemEvent[];
  stability?: number;
  [key: string]: unknown;
}

interface CognitivePattern {
  type?: string;
  seen?: number;
  prevented?: number;
  accuracy?: number;
  lead_time?: number;
  confidence?: number;
  data_quality?: string;
  trustworthy?: boolean;
}

interface DnaData {
  patterns?: number;
  pattern_list?: CognitivePattern[];
  total_failures?: number;
  prevented?: number;
}

interface BackendAction {
  id: string;
  label: string;
  description: string;
  safe?: boolean;
  targets?: string[];
}

interface BackendActionResult {
  success?: boolean;
  action_id?: string;
  process_count?: number;
  details?: string[];
  risk?: string;
  remediation_candidate?: boolean;
  primary_process?: {
    pid?: number;
    name?: string;
    cpu_percent?: number;
    memory_percent?: number;
    risk_level?: string;
    confidence?: number;
    classification?: string;
  } | null;
  processes?: Array<{
    pid?: number;
    name?: string;
    cpu_percent?: number;
    memory_percent?: number;
    risk_level?: string;
    confidence?: number;
    classification?: string;
  }>;
  policy?: {
    automatic_termination?: boolean;
    protected_pid_1?: boolean;
    protected_backend_pid?: boolean;
    identity_required?: boolean;
    creation_time_required?: boolean;
    review_required_for_uncertain_processes?: boolean;
  };
  note?: string;
  error?: string;
  blocked?: boolean;
  reason?: string;
}


interface HistoryPoint {
  time: number;
  label: string;
  cpu: number;
  memory: number;
  disk: number;
  network: number;
  anomaly: number;
  health: number;
  stability: number;
}

/* ── MAIN DASHBOARD ──────────────────────────────────────── */
export default function Dashboard() {

  const [cognitivePredictions, setCognitivePredictions] = useState<any[]>([]);
  const [predictionBusy, setPredictionBusy] = useState<string | null>(null);

  const [data, setData] = useState<SystemStatus>({});
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [forecast, setForecast] = useState<ForecastData>({});
  const [alertEvents, setAlertEvents] = useState<SystemEvent[]>([]);
  const [dna, setDna] = useState<DnaData>({});
  const [pipeline, setPipeline] = useState<PipelineData>({});
  const [availableActions, setAvailableActions] = useState<BackendAction[]>([]);
  const [manualAction, setManualAction] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<BackendActionResult | null>(null);
  const prevLevel = useRef("OPTIMAL");

  const fetchAvailableActions = useCallback(async () => {
    try {
      const response = await api.get<BackendAction[]>("/actions/available");
      setAvailableActions(response.data);
      setActionError(null);
    } catch (error) {
      console.error("[AIOps] Failed to load available actions:", error);
      setActionError("ACTION REGISTRY UNAVAILABLE");
    }
  }, []);

  const executeManualAction = useCallback(async (action: BackendAction) => {
    if (actionLoading) return;

    setActionLoading(action.id);
    setManualAction(null);
    setActionError(null);
    setActionResult(null);

    try {
      const response = await api.post(
        "/actions/execute",
        null,
        { params: { action_id: action.id } }
      );

      const result = response.data;

      if (result.success) {
        setActionResult(result);
        setManualAction(`${action.label} — COMPLETED`);
      } else if (result.blocked) {
        setActionError(
          `${action.label} — BLOCKED: ${result.reason ?? "backend safety policy"}`
        );
      } else {
        setActionError(
          `${action.label} — FAILED: ${
            result.error ?? result.details?.[0] ?? "unknown error"
          }`
        );
      }
    } catch (error) {
      console.error("[AIOps] Action execution failed:", error);
      setActionError(`${action.label} — REQUEST FAILED`);
    } finally {
      setActionLoading(null);
    }
  }, [actionLoading]);

  useEffect(() => {
    fetchAvailableActions();
  }, [fetchAvailableActions]);

  useEffect(() => {
    let cancelled = false;

    const fetchTelemetry = async () => {
      try {
        const response = await api.get<SystemStatus>("/os/status");
        const json = response.data;

        if (cancelled) return;

        console.log("[AIOps] Backend response:", json);
        setData(json);

        const newPoint: HistoryPoint = {
          time: Date.now(),
          label: new Date().toLocaleTimeString("en-US", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
          cpu: json.cpu_percent ?? 0,
          memory: json.memory ?? 0,
          disk: json.disk_percent
            ?? ((json.intelligence?.features?.disk ?? 0) * 100),
          network: json.network_percent
            ?? ((json.intelligence?.features?.network ?? 0) * 100),
          anomaly: Math.min(
            100,
            (json.anomaly_score ?? json.intelligence?.anomaly_score ?? 0) * 100
          ),
          health: json.health_score ?? 0,
          stability: json.stability ?? 0,
        };

        setHistory(prev => [...prev.slice(-39), newPoint]);
      } catch (error) {
        if (cancelled) return;

        console.error("[AIOps] Backend telemetry unavailable:", error);

        // IMPORTANT: no synthetic telemetry fallback.
        // Keep the last verified backend values on screen.
      }
    };

    const fetchPipeline = async () => {
      try {
        const pipelineResponse = await api.get<PipelineData>("/cognitive/pipeline");

        if (cancelled) return;

        setPipeline(pipelineResponse.data);
      } catch (error) {
        if (cancelled) return;

        console.error("Cognitive pipeline fetch failed:", error);
      }
    };

    const fetchForecast = async () => {
      try {
        const forecastResponse = await api.get<ForecastData>("/cognitive/forecast");

        if (cancelled) return;

        setForecast(forecastResponse.data);
      } catch (error) {
        if (cancelled) return;

        console.error("Forecast fetch failed:", error);
      }
    };

    const fetchAlertHistory = async () => {
      try {
        const alertsResponse = await api.get<SystemEvent[]>("/alerts/history?limit=10");

        if (cancelled) return;

        setAlertEvents(
          (alertsResponse.data ?? []).map((alert) => ({
            ...alert,
            message:
              alert.message ??
              alert.event ??
              alert.type ??
              "Alert recorded",
            timestamp: alert.timestamp ?? alert.time ?? "NOW",
            severity: alert.severity ?? "INFO",
          }))
        );
      } catch (error) {
        if (cancelled) return;

        console.error("Alert history fetch failed:", error);
      }
    };

    const fetchDna = async () => {
      try {
        const dnaResponse = await api.get<DnaData>("/cognitive/dna");

        if (cancelled) return;

        setDna(dnaResponse.data);
      } catch (error) {
        if (cancelled) return;

        console.error("Cognitive DNA fetch failed:", error);
      }
    };

    // Initial load.
    fetchTelemetry();
    fetchPipeline();
    fetchForecast();
    fetchAlertHistory();
    fetchDna();

    // Telemetry is lightweight and remains responsive.
    const telemetryId = setInterval(fetchTelemetry, 500);

    // Cognitive pipeline performs DQN simulation/training, so poll less often.
    const pipelineId = setInterval(fetchPipeline, 2000);

    // Forecast has its own backend cache and changes much more slowly.
    const forecastId = setInterval(fetchForecast, 10000);
    const alertId = setInterval(fetchAlertHistory, 5000);
    const dnaId = setInterval(fetchDna, 30000);

    return () => {
      cancelled = true;
      clearInterval(telemetryId);
      clearInterval(pipelineId);
      clearInterval(forecastId);
      clearInterval(alertId);
      clearInterval(dnaId);
    };
  }, []);

  // ── Derived state ──
  const health = data.health_score ?? history[history.length - 1]?.health ?? 0;
  const anomaly = data.anomaly_score ?? data.intelligence?.anomaly_score ?? 0;
  const stability = data.stability ?? history[history.length - 1]?.stability ?? 0;
  const decision = {
    ...(data.latest_decision ?? {}),
    ...(pipeline.decision ?? {}),
  };
  const decisionRootCause =
    pipeline.decision?.root_cause?.type ||
    pipeline.causal?.primary_cause ||
    data.intelligence?.fusion?.cause ||
    null;

  // ── Forecast-backed risk ──
  // TP-140: live cognitive prediction polling
  useEffect(() => {
    let cancelled = false;

    const loadPredictions = async () => {
      try {
        const data = await fetchCognitivePredictions();
        if (!cancelled) {
          setCognitivePredictions(Array.isArray(data) ? data : []);
        }
      } catch (error) {
        console.error("Cognitive predictions fetch failed:", error);
      }
    };

    loadPredictions();
    const timer = window.setInterval(loadPredictions, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // Current system risk comes from the live cognitive pipeline.
  // Forecast peak risk remains a future-risk indicator.
  const risk =
    pipeline.system_risk !== undefined
      ? pipeline.system_risk
      : Math.min(
          1,
          anomaly * 0.7 + ((100 - health) / 100) * 0.3
        );

  const level =
    risk > 0.75 ? "CRITICAL" :
    risk > 0.45 ? "WARNING" :
    "OPTIMAL";

  const color =
    level === "CRITICAL" ? T.danger :
    level === "WARNING" ? T.warning :
    T.success;

  const isCritical = level === "CRITICAL";
  const isWarning = level === "WARNING";

  useEffect(() => {
    if (level === "CRITICAL" && prevLevel.current !== "CRITICAL") {
      try {
        const AudioContextClass =
          window.AudioContext ||
          (window as typeof window & {
            webkitAudioContext?: typeof AudioContext;
          }).webkitAudioContext;

        if (!AudioContextClass) return;

        const ctx = new AudioContextClass();

        [880, 660, 880].forEach((freq, i) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.frequency.value = freq;
          gain.gain.value = 0.07;

          osc.start(ctx.currentTime + i * 0.18);
          osc.stop(ctx.currentTime + i * 0.18 + 0.14);
        });
      } catch {}
    }

    prevLevel.current = level;
  }, [level]);

  const lastHistory: HistoryPoint =
    history[history.length - 1] ?? {
      time: 0,
      label: "--:--:--",
      cpu: 0,
      memory: 0,
      disk: 0,
      network: 0,
      anomaly: 0,
      health: 0,
    };

  const radarData = [
    { subject: "CPU", value: lastHistory.cpu },
    { subject: "Memory", value: lastHistory.memory },
    { subject: "Disk", value: lastHistory.disk },
    { subject: "Network", value: lastHistory.network },
    // ✅ FIXED: anomaly already scaled 0-100
    { subject: "Anomaly", value: lastHistory.anomaly },
    { subject: "Stability", value: stability * 100 },
  ];

  const learnedPatterns = Array.isArray(dna.pattern_list)
    ? dna.pattern_list
    : [];

  // Sparkline history slices
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
            subtitle="Resource stability index"
            icon="◈"
            tooltip="Derived from CPU, memory, disk pressure, anomaly pressure, and recent volatility"
            sparkData={history.slice(-20).map(point => point.stability * 100)}
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

            {/* Health Check History */}
            <Section title="Health Check History" subtitle="Last 30 check intervals">
              <UptimeDots history={history} />
              <div style={{ marginTop: "10px", display: "flex", justifyContent: "space-between", fontSize: "10px", fontFamily: "'Share Tech Mono', monospace", color: T.textDim }}>
                <span>30 intervals ago</span>
                <span style={{ color: T.success }}>CURRENT HEALTH {health.toFixed(1)}%</span>
                <span>now</span>
              </div>
            </Section>

            {/* Future State Projection */}
            <Section
              title="Future State Projection"
              subtitle={`AI forecast · next ${forecast.points?.length ? Math.max(...forecast.points.map(p => p.t ?? 0)) : 60} min`}
              alert={forecast.peak_risk?.toUpperCase() === "CRITICAL"}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "11px", fontFamily: "'Share Tech Mono', monospace" }}>
                {[
                  {
                    label: forecast.points?.length
                      ? `✓ CPU FORECAST: ${forecast.points[forecast.points.length - 1]?.cpu?.toFixed(1) ?? "—"}% AT +${forecast.points[forecast.points.length - 1]?.t ?? "—"} MIN`
                      : "… WAITING FOR FORECAST DATA",
                    ok: forecast.peak_risk?.toUpperCase() !== "CRITICAL",
                  },
                  {
                    label: forecast.direction
                      ? `◈ TREND: ${forecast.direction}`
                      : "◈ TREND: —",
                    ok: forecast.direction?.toUpperCase() !== "DECLINING",
                  },
                  {
                    label: forecast.peak_risk
                      ? `◈ PEAK RISK: ${forecast.peak_risk.toUpperCase()} · CONFIDENCE: ${forecast.confidence !== undefined ? (forecast.confidence * 100).toFixed(0) : "—"}%`
                      : "◈ PEAK RISK: —",
                    highlight: true,
                  },
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


            {/* Live Cognitive Predictions */}
            <Section
              title="Predicted Events"
              subtitle="Live cognitive failure forecast"
              alert={cognitivePredictions.some((p) => String(p.severity).toUpperCase() === "CRITICAL")}
              accentColor={T.accent}
            >
              {cognitivePredictions.length === 0 ? (
                <div style={{
                  padding: "14px",
                  borderRadius: "4px",
                  background: "rgba(0,0,0,0.25)",
                  border: `1px solid ${T.border}`,
                  color: T.textDim,
                  fontSize: "11px",
                  fontFamily: "'Share Tech Mono', monospace",
                }}>
                  NO ACTIVE PREDICTIONS
                </div>
              ) : (
                <div style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  fontFamily: "'Share Tech Mono', monospace",
                }}>
                  {cognitivePredictions.map((prediction) => {
                    const severity = String(prediction.severity || "LOW").toUpperCase();
                    const severityColor =
                      severity === "CRITICAL" ? T.danger :
                      severity === "MEDIUM" ? T.warning :
                      T.accent;

                    const busy = predictionBusy === prediction.id;

                    return (
                      <div
                        key={prediction.id}
                        style={{
                          padding: "11px 12px",
                          borderRadius: "4px",
                          background: "rgba(0,0,0,0.28)",
                          border: `1px solid ${severityColor}35`,
                          borderLeft: `3px solid ${severityColor}`,
                        }}
                      >
                        <div style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "8px",
                          marginBottom: "6px",
                        }}>
                          <span style={{
                            color: severityColor,
                            fontWeight: 700,
                            fontSize: "11px",
                          }}>
                            {String(prediction.type || "EVENT")}
                          </span>

                          <span style={{
                            color: T.textDim,
                            fontSize: "10px",
                          }}>
                            ETA {Number(prediction.eta_minutes || 0).toFixed(0)} MIN
                          </span>
                        </div>

                        <div style={{
                          color: T.text,
                          fontSize: "11px",
                          lineHeight: "1.5",
                          marginBottom: "7px",
                        }}>
                          {prediction.message || "Predicted system event"}
                        </div>

                        <div style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "8px",
                          marginBottom: "8px",
                        }}>
                          <span style={{
                            color: prediction.trustworthy === false ? T.warning : T.success,
                            fontSize: "10px",
                            fontWeight: 700,
                          }}>
                            CONFIDENCE: {Number(prediction.confidence || 0).toFixed(0)}%
                          </span>

                          <span style={{
                            color: T.textDim,
                            fontSize: "9px",
                          }}>
                            {prediction.trustworthy === false ? "LEARNING SIGNAL" : "TRUSTED"}
                          </span>
                        </div>

                        {prediction.action && (
                          <div style={{
                            color: T.textDim,
                            fontSize: "10px",
                            lineHeight: "1.5",
                            marginBottom: "8px",
                          }}>
                            ACTION: {prediction.action}
                          </div>
                        )}

                        <div style={{
                          display: "flex",
                          gap: "6px",
                        }}>
                          {!prediction.acknowledged && (
                            <button
                              disabled={busy}
                              onClick={async () => {
                                try {
                                  setPredictionBusy(prediction.id);
                                  await acknowledgeCognitivePrediction(prediction.id);
                                  const data = await fetchCognitivePredictions();
                                  setCognitivePredictions(Array.isArray(data) ? data : []);
                                } catch (error) {
                                  console.error("Prediction acknowledge failed:", error);
                                } finally {
                                  setPredictionBusy(null);
                                }
                              }}
                              style={{
                                flex: 1,
                                padding: "6px 8px",
                                borderRadius: "3px",
                                border: `1px solid ${T.accent}50`,
                                background: "transparent",
                                color: T.accent,
                                cursor: busy ? "wait" : "pointer",
                                fontFamily: "'Share Tech Mono', monospace",
                                fontSize: "9px",
                              }}
                            >
                              ACKNOWLEDGE
                            </button>
                          )}

                          <button
                            disabled={busy}
                            onClick={async () => {
                              try {
                                setPredictionBusy(prediction.id);
                                await resolveCognitivePrediction(prediction.id, true);
                                const data = await fetchCognitivePredictions();
                                setCognitivePredictions(Array.isArray(data) ? data : []);
                              } catch (error) {
                                console.error("Prediction resolve failed:", error);
                              } finally {
                                setPredictionBusy(null);
                              }
                            }}
                            style={{
                              flex: 1,
                              padding: "6px 8px",
                              borderRadius: "3px",
                              border: `1px solid ${T.success}50`,
                              background: "transparent",
                              color: T.success,
                              cursor: busy ? "wait" : "pointer",
                              fontFamily: "'Share Tech Mono', monospace",
                              fontSize: "9px",
                            }}
                          >
                            CORRECT
                          </button>

                          <button
                            disabled={busy}
                            onClick={async () => {
                              try {
                                setPredictionBusy(prediction.id);
                                await resolveCognitivePrediction(prediction.id, false);
                                const data = await fetchCognitivePredictions();
                                setCognitivePredictions(Array.isArray(data) ? data : []);
                              } catch (error) {
                                console.error("Prediction resolve failed:", error);
                              } finally {
                                setPredictionBusy(null);
                              }
                            }}
                            style={{
                              flex: 1,
                              padding: "6px 8px",
                              borderRadius: "3px",
                              border: `1px solid ${T.danger}50`,
                              background: "transparent",
                              color: T.danger,
                              cursor: busy ? "wait" : "pointer",
                              fontFamily: "'Share Tech Mono', monospace",
                              fontSize: "9px",
                            }}
                          >
                            INCORRECT
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
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
              <DataBar value={lastHistory.cpu} color={T.accent} label="CPU CORES" />
              <DataBar value={lastHistory.memory} color={T.primary} label="MEMORY" />
              <DataBar value={lastHistory.disk} color={T.success} label="DISK I/O" />
              <DataBar value={lastHistory.network} color={T.warning} label="NETWORK" />
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
                  <div><div style={{ color: T.textDim, marginBottom: "3px" }}>PRIORITY</div><div style={{ color: T.warning, fontWeight: 700 }}>{decision?.risk_level || decision?.priority || "NORMAL"}</div></div>
                </div>
              </div>
              <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginBottom: "6px" }}>CONFIDENCE FIELD</div>
              <div style={{ height: "8px", borderRadius: "2px", background: "rgba(0,0,0,0.4)", overflow: "hidden", marginBottom: "14px" }}>
                <div style={{ width: `${(decision?.confidence || 0) * 100}%`, height: "100%", background: `linear-gradient(90deg, ${T.success}, ${T.accent})`, boxShadow: `0 0 12px ${T.success}80`, transition: "width 0.8s ease", borderRadius: "2px" }} />
              </div>
              <div style={{ fontSize: "10px", color: T.textDim, fontFamily: "'Share Tech Mono', monospace", marginBottom: "6px" }}>ROOT CAUSE ANALYSIS</div>
              <div style={{ background: "rgba(0,0,0,0.25)", padding: "12px", borderRadius: "4px", fontSize: "11px", color: T.text, lineHeight: "1.7", fontFamily: "'Share Tech Mono', monospace", borderLeft: `2px solid ${color}` }}>
                {decisionRootCause || "No anomalies detected — system operating within baseline parameters."}
              </div>
            </Section>

            {/* Causal Chain */}
            <Section title="Causal Correlation" subtitle="Backend causal analysis">
              <div style={{ fontSize: "11px", fontFamily: "'Share Tech Mono', monospace" }}>
                <div style={{
                  padding: "10px 12px",
                  background: "rgba(0,0,0,0.3)",
                  borderRadius: "4px",
                  borderLeft: `2px solid ${decisionRootCause ? T.warning : T.textDim}`,
                  marginBottom: "10px",
                }}>
                  <div style={{ color: T.textDim, marginBottom: "5px" }}>
                    PRIMARY CAUSE
                  </div>
                  <div style={{ color: decisionRootCause ? T.warning : T.text, fontWeight: 700 }}>
                    {pipeline.causal?.primary_cause ||
                      pipeline.decision?.root_cause?.type ||
                      "NO CAUSAL RELATIONSHIP IDENTIFIED"}
                  </div>
                </div>

                <div style={{
                  padding: "10px 12px",
                  background: "rgba(0,0,0,0.3)",
                  borderRadius: "4px",
                  borderLeft: `2px solid ${T.accent}`,
                }}>
                  → DECISION: <span style={{ color: T.accent, fontWeight: 700 }}>
                    {decision?.action || "MONITOR"}
                  </span>
                </div>
              </div>
            </Section>

            {/* Learned Patterns */}
            <Section title="Learned Patterns" subtitle="Historical intelligence database">
              <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
                {learnedPatterns.slice(0, 4).map((p, i) => {
                  const pc = p.trustworthy === false
                    ? T.warning
                    : (p.confidence ?? 0) >= 80
                      ? T.success
                      : T.accent;

                  return (
                    <div key={i} style={{
                      padding: "9px 12px",
                      borderRadius: "4px",
                      background: "rgba(0,0,0,0.2)",
                      borderLeft: `2px solid ${pc}`,
                      fontSize: "11px",
                      fontFamily: "'Share Tech Mono', monospace"
                    }}>
                      <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "3px"
                      }}>
                        <span style={{ color: T.text, fontWeight: 600 }}>
                          {p.type ?? "UNKNOWN"}
                        </span>
                        <span style={{ color: pc, fontSize: "10px" }}>
                          {p.confidence != null ? `${p.confidence.toFixed(0)}% CONF.` : "NO CONF."}
                        </span>
                      </div>

                      <div style={{
                        display: "flex",
                        gap: "12px",
                        flexWrap: "wrap",
                        fontSize: "10px",
                        color: T.textDim
                      }}>
                        <span>SEEN: {p.seen ?? 0}</span>
                        <span>PREVENTED: {p.prevented ?? 0}</span>
                        <span>ACCURACY: {p.accuracy != null ? `${p.accuracy.toFixed(1)}%` : "—"}</span>
                        <span>LEAD: {p.lead_time != null ? `${p.lead_time.toFixed(1)}s` : "—"}</span>
                      </div>

                      {p.data_quality && (
                        <div style={{
                          marginTop: "3px",
                          fontSize: "9px",
                          color: T.textDim
                        }}>
                          DATA QUALITY: {p.data_quality.toUpperCase()}
                        </div>
                      )}
                    </div>
                  );
                })}

                {learnedPatterns.length === 0 && (
                  <div style={{
                    padding: "10px 12px",
                    color: T.textDim,
                    fontSize: "10px",
                    fontFamily: "'Share Tech Mono', monospace"
                  }}>
                    NO LEARNED PATTERNS AVAILABLE
                  </div>
                )}
              </div>
            </Section>

            {/* Operator Actions */}
            <Section title="Operator Actions" subtitle="Authenticated backend actions">
              <div style={{ display: "flex", flexDirection: "column", gap: "9px" }}>
                {availableActions.map((action) => (
                  <button
                    key={action.id}
                    onClick={() => executeManualAction(action)}
                    disabled={actionLoading !== null}
                    style={{
                      background: actionLoading === action.id
                        ? `${T.accent}20`
                        : `${T.accent}08`,
                      border: `1px solid ${T.accent}40`,
                      borderRadius: "4px",
                      padding: "11px 16px",
                      color: T.accent,
                      fontSize: "12px",
                      fontWeight: 700,
                      cursor: actionLoading !== null ? "wait" : "pointer",
                      fontFamily: "'Rajdhani', sans-serif",
                      letterSpacing: "0.08em",
                      textAlign: "left",
                      opacity: actionLoading !== null && actionLoading !== action.id ? 0.5 : 1,
                      transition: "all 0.2s cubic-bezier(0.4,0,0.2,1)",
                    }}
                  >
                    {actionLoading === action.id ? "◌ EXECUTING..." : `▸ ${action.label}`}
                    <div style={{
                      marginTop: "4px",
                      fontSize: "9px",
                      fontWeight: 400,
                      letterSpacing: "0.02em",
                      color: T.textMuted,
                    }}>
                      {action.description}
                    </div>
                  </button>
                ))}

                {availableActions.length === 0 && !actionError && (
                  <div style={{
                    padding: "10px 12px",
                    color: T.textDim,
                    fontSize: "10px",
                    fontFamily: "'Share Tech Mono', monospace",
                  }}>
                    LOADING ACTION REGISTRY...
                  </div>
                )}

                {actionError && (
                  <div style={{
                    padding: "9px 12px",
                    borderRadius: "4px",
                    background: "rgba(255,51,102,0.07)",
                    border: `1px solid ${T.danger}50`,
                    fontSize: "10px",
                    color: T.danger,
                    fontFamily: "'Share Tech Mono', monospace",
                  }}>
                    ⚠ {actionError}
                  </div>
                )}

                {actionResult && (
                  <div style={{
                    padding: "10px 12px",
                    borderRadius: "4px",
                    background: "rgba(0,212,255,0.05)",
                    border: `1px solid ${T.accent}35`,
                    fontFamily: "'Share Tech Mono', monospace",
                    fontSize: "9px",
                    color: T.textMuted,
                  }}>
                    <div style={{
                      color: T.accent,
                      fontSize: "10px",
                      marginBottom: "7px",
                      letterSpacing: "0.08em",
                    }}>
                      DIAGNOSTIC RESULT · {actionResult.process_count ?? 0} PROCESSES INSPECTED
                    </div>

                    {actionResult.processes?.slice(0, 5).map((process, index) => (
                      <div key={`${process.pid ?? "process"}-${index}`} style={{
                        padding: "5px 0",
                        borderTop: index === 0 ? "none" : `1px solid ${T.border}`,
                      }}>
                        <span style={{ color: T.text }}>
                          {process.name ?? "unknown"}
                        </span>
                        <span> · PID {process.pid ?? "—"}</span>
                        <span> · CPU {process.cpu_percent?.toFixed(1) ?? "—"}%</span>
                        <span> · MEM {process.memory_percent?.toFixed(1) ?? "—"}%</span>
                        <span> · {process.classification ?? "—"}</span>
                      </div>
                    ))}

                    {actionResult.risk && (
                      <div style={{
                        marginTop: "7px",
                        color: T.warning,
                        lineHeight: 1.5,
                      }}>
                        {actionResult.risk}
                      </div>
                    )}

                    {actionResult.note && (
                      <div style={{
                        marginTop: "7px",
                        color: T.success,
                        lineHeight: 1.5,
                      }}>
                        {actionResult.note}
                      </div>
                    )}
                  </div>
                )}

                {manualAction && !actionError && (
                  <div style={{
                    padding: "9px 12px",
                    borderRadius: "4px",
                    background: "rgba(0,255,157,0.07)",
                    border: `1px solid ${T.success}50`,
                    fontSize: "11px",
                    color: T.success,
                    fontFamily: "'Share Tech Mono', monospace",
                    animation: "slideIn 0.3s ease-out",
                  }}>
                    ✓ {manualAction}
                  </div>
                )}
              </div>
            </Section>

            <Section title="System Events" subtitle="Chronological event log">
              <EventLog events={alertEvents} />
            </Section>
          </div>

          {/* RIGHT COLUMN — AI CHAT */}
          <div style={{ position: "sticky", top: "28px", height: "calc(100vh - 56px)" }}>
            <AIChat />
          </div>
        </div>
      </div>
    </>
  );
}
