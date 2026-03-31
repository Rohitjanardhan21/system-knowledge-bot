import React, { useEffect, useState, useMemo, useCallback, useRef } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid
} from "recharts";
import {
  Brain, Terminal, X, Sun, Moon, Activity, ShieldCheck, Zap,
  TrendingUp, Info, Clock, Layers, AlertTriangle, Cpu, Send,
  ChevronRight, Radio, Loader, Database
} from "lucide-react";

/* ═══════════════════════════════════════════════
   THEME CONFIGURATION
═══════════════════════════════════════════════ */
const T = {
  dark: {
    bg: "#07080f",
    surface: "rgba(16,18,32,0.95)",
    border: "rgba(99,102,241,0.18)",
    borderStrong: "rgba(99,102,241,0.35)",
    text: "#e8eaf6",
    muted: "#4b5563",
    accent: "#6366f1",
    accentGlow: "rgba(99,102,241,0.22)",
    green: "#10b981",
    greenGlow: "rgba(16,185,129,0.15)",
    red: "#ef4444",
    redGlow: "rgba(239,68,68,0.18)",
    amber: "#f59e0b",
    grid: "rgba(99,102,241,0.06)",
    input: "rgba(10,11,22,0.8)",
    tag: "rgba(99,102,241,0.12)",
  },
  light: {
    bg: "#f4f5fb",
    surface: "rgba(255,255,255,0.97)",
    border: "rgba(99,102,241,0.15)",
    borderStrong: "rgba(99,102,241,0.3)",
    text: "#0f1123",
    muted: "#6b7280",
    accent: "#4f46e5",
    accentGlow: "rgba(79,70,229,0.12)",
    green: "#059669",
    greenGlow: "rgba(5,150,105,0.1)",
    red: "#dc2626",
    redGlow: "rgba(220,38,38,0.1)",
    amber: "#d97706",
    grid: "#ede9fe",
    input: "#f8f9ff",
    tag: "rgba(79,70,229,0.08)",
  }
};

/* ═══════════════════════════════════════════════
   AI CHAT (Anthropic API)
═══════════════════════════════════════════════ */
async function askClaude(messages: any[], systemCtx: string): Promise<string> {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      system: systemCtx,
      messages,
    }),
  });
  const d = await res.json();
  return d.content?.[0]?.text ?? "No response received.";
}

export default function Dashboard() {
  // ── REAL BACKEND DATA STATE ──
  const [data, setData] = useState<any>({});
  const [isDark, setIsDark] = useState(true);
  const [history, setHistory] = useState<any[]>([]);

  // Chat state
  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const tk = isDark ? T.dark : T.light;
  const isCritical = data.cpu > 75;
  const isAnomaly = data.anomaly_score > 1.5;

  /* ─────────────────────────────────────────────
      REAL BACKEND POLLING (CRITICAL FIX)
  ───────────────────────────────────────────── */
  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("http://localhost:8000/system/summary");
        const json = await res.json();
        setData(json);
        
        // Update history for chart
        setHistory(prev => [
            ...prev.slice(-39),
            { t: Date.now(), cpu: json.cpu, upper: json.cpu + 7, lower: Math.max(0, json.cpu - 6) },
          ]);
      } catch (err) {
        console.error("Connection failed. Mode: Unverified.", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 1500);
    return () => clearInterval(interval);
  }, []);

  /* ─────────────────────────────────────────────
      LLM SAFETY & LOGIC (ANTI-HALLUCINATION)
  ───────────────────────────────────────────── */
  const systemPrompt = useMemo(() => `
    You are CogniOS. Currently monitoring LIVE telemetry.
    Context: CPU ${data.cpu}% | Risk ${data.risk?.level} | Verified: ${data.validated}
    Only answer based on the provided metrics. If uncertain, state you require further telemetry.
  `, [data]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || thinking) return;
    const newMsgs = [...messages, { role: "user", content: text }];
    setMessages(newMsgs);
    setInput("");
    setThinking(true);
    try {
      const rawReply = await askClaude(newMsgs, systemPrompt);
      
      // ADD 5: LLM SAFETY GUARD
      const safeReply = rawReply.includes("likely") || rawReply.includes("probably")
        ? "⚠ Unverified reasoning detected. Please cross-reference with 'Data Integrity' panel before acting."
        : rawReply;

      setMessages(prev => [...prev, { role: "assistant", content: safeReply }]);
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: "⚠ Error: Reasoning engine offline." }]);
    } finally {
      setThinking(false);
    }
  }, [input, messages, thinking, systemPrompt]);

  // AUTO-TRIGGER chat on anomaly
  useEffect(() => {
    if (isAnomaly && !chatOpen) setChatOpen(true);
  }, [isAnomaly]);

  /* ── Card wrapper ── */
  const Card = useCallback(({ title, children, icon: Icon, alert = false, onAsk }: any) => (
    <div style={{
      background: tk.surface, padding: "20px", borderRadius: 18, border: `1px solid ${alert ? tk.red : tk.border}`,
      boxShadow: alert ? `0 0 28px ${tk.redGlow}` : `0 4px 24px rgba(0,0,0,0.08)`, transition: "0.25s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {Icon && <Icon size={13} color={alert ? tk.red : tk.accent} />}
          <span style={{ fontSize: 10, fontWeight: 800, textTransform: "uppercase", color: tk.muted }}>{title}</span>
        </div>
        {onAsk && <button onClick={onAsk} style={{ fontSize: 10, color: tk.accent, background: "none", border: "none", cursor: "pointer" }}>Ask AI</button>}
      </div>
      {children}
    </div>
  ), [tk]);

  return (
    <div style={{ background: tk.bg, minHeight: "100vh", color: tk.text, fontFamily: "'Inter', sans-serif" }}>
      
      {/* ── HEADER (ADD 6: REAL-TIME SOURCE MODE) ── */}
      <div style={{ display: "flex", justifyContent: "space-between", padding: "18px 40px", borderBottom: `1px solid ${tk.border}`, background: tk.surface, backdropFilter: "blur(16px)", position: "sticky", top: 0, zIndex: 50 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <Brain size={22} color={tk.accent} />
          <div>
            <div style={{ fontSize: 18, fontWeight: 900 }}>CogniOS</div>
            <div style={{ fontSize: 10, color: tk.muted }}>
              Mode: {data.validated ? "Live Verified Data" : "Unverified / Simulation"}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 20 }}>
          <button onClick={() => setChatOpen(!chatOpen)} style={{ background: tk.accent, color: "#fff", padding: "8px 16px", borderRadius: 8, border: "none", cursor: "pointer", fontWeight: 700 }}>
            Neural Bridge
          </button>
          <button onClick={() => setIsDark(!isDark)} style={{ background: "none", color: tk.text, border: "none", cursor: "pointer" }}>
            {isDark ? <Sun size={18}/> : <Moon size={18}/>}
          </button>
        </div>
      </div>

      <div style={{ padding: "28px 40px", display: "grid", gridTemplateColumns: "1fr 340px", gap: 24, maxWidth: 1400, margin: "0 auto" }}>
        
        {/* LEFT COL */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 18 }}>
            <Card title="Compute Load" icon={Cpu} alert={isCritical}>
              <div style={{ fontSize: 44, fontWeight: 900 }}>{data.cpu || 0}%</div>
            </Card>
            
            <Card title="Memory" icon={Zap}>
              <div style={{ fontSize: 44, fontWeight: 900 }}>{data.memory || 0}%</div>
            </Card>

            <Card title="Anomaly Status" icon={Activity} alert={isAnomaly}>
              <div style={{ fontSize: 44, fontWeight: 900, color: isAnomaly ? tk.red : tk.green }}>
                {data.anomaly_score?.toFixed(2) || 0}
              </div>
              <div style={{ fontSize: 10, marginTop: 6, color: tk.muted }}>
                Confidence: {(data.decision?.confidence * 100 || 0).toFixed(0)}%
              </div>
            </Card>
          </div>

          <Card title="Telemetry Visualizer" icon={TrendingUp}>
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history}>
                  <Area type="monotone" dataKey="cpu" stroke={tk.accent} fill={tk.accent} fillOpacity={0.1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* ADD 2: EVIDENCE-BASED ROOT CAUSE */}
          <Card title="Root Cause Analysis" icon={Info}>
            <div style={{ fontSize: 14 }}>
               Target: <strong>{data.root_cause?.process || "N/A"}</strong>
               <div style={{ fontSize: 10, color: tk.muted, marginTop: 4 }}>
                 Source: {data.root_cause?.source || "kernel_model"}
               </div>
               <div style={{ marginTop: 12 }}>
                 <div style={{ fontSize: 11, color: tk.muted, fontWeight: 800 }}>Evidence Chain:</div>
                 {data.root_cause?.evidence?.length ? data.root_cause.evidence.map((e:string, i:number) => (
                   <div key={i} style={{ fontSize: 12, marginTop: 4 }}>• {e}</div>
                 )) : <div style={{ fontSize: 12, color: tk.muted }}>Awaiting causal verification...</div>}
               </div>
            </div>
          </Card>
        </div>

        {/* RIGHT COL */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          
          {/* ADD 1: DATA VALIDATION PANEL */}
          <Card title="Data Integrity" icon={ShieldCheck}>
             <div style={{ fontSize: 12, lineHeight: 1.7 }}>
               Status: <b style={{ color: data.validated ? tk.green : tk.red }}>{data.validated ? "Verified" : "Unverified"}</b>
               <br />
               Confidence: <b style={{ color: tk.accent }}>{(data.decision?.confidence * 100 || 0).toFixed(0)}%</b>
               
               {data.validation_issues?.length > 0 && (
                 <div style={{ marginTop: 10, padding: 10, background: tk.redGlow, borderRadius: 8, color: tk.red }}>
                   {data.validation_issues.map((i:string, idx:number) => <div key={idx}>• {i}</div>)}
                 </div>
               )}
             </div>
          </Card>

          <Card title="Action Operator" icon={Radio}>
            {/* ADD 4: AUTONOMOUS SIGNAL */}
            {data.recommendation?.auto_execute && (
              <div style={{ marginBottom: 10, padding: "6px 10px", background: tk.redGlow, borderRadius: 8, fontSize: 11, fontWeight: 700, color: tk.red }}>
                ⚡ Autonomous Action Ready
              </div>
            )}
            <div style={{ fontSize: 13, color: tk.text }}>{data.recommendation?.message || "Analyzing state..."}</div>
            <button disabled={!data.validated} style={{ width: "100%", marginTop: 16, padding: 12, borderRadius: 10, background: data.validated ? tk.accent : tk.muted, color: "#fff", border: "none", cursor: data.validated ? "pointer" : "not-allowed", fontWeight: 700 }}>
               Execute Mitigation
            </button>
          </Card>

          {/* ADD 5: EVENTS PANEL */}
          <Card title="Kernel Feed" icon={AlertTriangle}>
             <div style={{ fontSize: 11, color: tk.muted, display: "flex", flexDirection: "column", gap: 8 }}>
               {data.events?.slice(0, 5).map((e:string, i:number) => (
                 <div key={i}>• {e}</div>
               )) || "No recent events"}
             </div>
          </Card>
        </div>
      </div>

      {/* CHAT SIDEBAR */}
      {chatOpen && (
        <div style={{ position: "fixed", right: 0, top: 0, width: 400, height: "100vh", background: tk.surface, borderLeft: `1px solid ${tk.border}`, padding: 30, display: "flex", flexDirection: "column", zIndex: 100, animation: "slideIn 0.3s ease" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
            <b>Neural Assistant</b>
            <X size={18} cursor="pointer" onClick={() => setChatOpen(false)} />
          </div>
          <div style={{ flex: 1, overflowY: "auto", fontSize: 14 }}>
            {messages.map((m, i) => <div key={i} style={{ marginBottom: 15, padding: 10, background: m.role === 'user' ? tk.tag : 'none', borderRadius: 8 }}>{m.content}</div>)}
            {thinking && <Loader size={16} className="spin" />}
          </div>
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendMessage()} placeholder="Ask engine..." style={{ width: "100%", padding: 12, borderRadius: 8, background: tk.input, border: `1px solid ${tk.border}`, color: tk.text }} />
        </div>
      )}

      <style>{`
        @keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
        .spin { animation: rotate 2s linear infinite; }
        @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
