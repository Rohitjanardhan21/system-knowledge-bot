import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import { connectWebSocket } from "../services/wsClient";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer
} from "recharts";

const safe = (v: any, d = 0) => (typeof v === "number" ? v : d);

export default function Dashboard() {

  const [data, setData] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [expanded, setExpanded] = useState(false);

  const prevRef = useRef<any>(null);

  useEffect(() => {
    const ws = connectWebSocket((incoming: any) => {
      prevRef.current = data;
      setData(incoming);

      setHistory(prev => [
        ...prev.slice(-60),
        {
          time: new Date().toLocaleTimeString(),
          cpu: Number.isFinite(incoming.cpu) ? incoming.cpu : 0,
          memory: Number.isFinite(incoming.memory) ? incoming.memory : 0
        }
      ]);
    });

    return () => ws?.close();
  }, [data]);

  if (!data) return <div className="p-6 text-white">Connecting...</div>;

  const cpu = safe(data.cpu);
  const memory = safe(data.memory);
  const disk = safe(data.disk);
  const risk = safe(data.system_risk);

  const diagnosis = data.diagnosis || {};
  const prediction = data.prediction || {};
  const causal = data.causal || {};
  const action = data.autonomous_action;

  // 🔥 FIXED CONTEXT HANDLING
  const context = data.context?.type || data.context || "general";

  // 🔥 FIXED CAUSE HANDLING
  const cause = causal?.primary_cause;

  const causeText = cause
    ? cause.reason || `${cause.process || "system"} (${cause.type})`
    : "background activity";

  const contributors = cause?.contributors || [];

  const status =
    risk > 0.7 ? "⚠ Critical" :
    risk > 0.4 ? "⚡ Under Load" :
    "✅ Stable";

  return (
    <div className="min-h-screen bg-black text-white px-10 py-8 space-y-8">

      {/* HEADER */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl text-green-400">AI System Agent</h1>
        <p className="text-xs text-gray-400">
          Context: <span className="text-blue-400">{context}</span>
        </p>
      </div>

      {/* 🧠 SYSTEM STORY */}
      <Card title="🧠 System Understanding">
        <p className="text-lg">
          System is <span className="text-green-400">{status}</span>
        </p>

        <p className="text-sm mt-2 text-gray-300">
          CPU at {cpu.toFixed(0)}% primarily due to{" "}
          <span className="text-yellow-400">{causeText}</span>
        </p>

        {/* 🔥 CONTRIBUTORS */}
        {contributors.length > 0 && (
          <div className="mt-3 text-xs text-gray-400">
            Top contributors:
            {contributors.slice(0, 3).map((c: any, i: number) => (
              <div key={i}>
                • {c.name} ({c.cpu || 0}%)
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-gray-500 mt-2">
          {diagnosis.details}
        </p>
      </Card>

      {/* KPI */}
      <div className="grid grid-cols-4 gap-4">
        <KPI title="CPU" value={`${cpu.toFixed(1)}%`} />
        <KPI title="Memory" value={`${memory.toFixed(1)}%`} />
        <KPI title="Disk" value={`${disk.toFixed(1)}%`} />
        <KPI title="Risk" value={`${(risk * 100).toFixed(1)}%`} highlight={risk > 0.7} />
      </div>

      {/* 📊 GRAPH */}
      <Card title="📈 System Behavior">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={history}>
            <XAxis dataKey="time" />
            <YAxis />
            <Tooltip />

            <Line
              dataKey="cpu"
              stroke="#22c55e"
              strokeWidth={2}
              connectNulls
            />

            <Line
              dataKey="memory"
              stroke="#3b82f6"
              strokeWidth={2}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>

        <p className="text-xs text-gray-500 mt-2">
          Real-time system load trends.
        </p>
      </Card>

      {/* 🔮 FUTURE + IMPACT */}
      <div className="grid grid-cols-2 gap-6">

        <Card title="🔮 Prediction">
          <p className="text-blue-400">{prediction.type || "Stable"}</p>

          <div className="w-full bg-gray-800 h-2 mt-2 rounded">
            <div
              className="bg-green-500 h-2 rounded"
              style={{ width: `${(prediction.confidence || 0) * 100}%` }}
            />
          </div>

          <p className="text-xs text-gray-400 mt-1">
            Confidence: {(prediction.confidence * 100 || 0).toFixed(0)}%
          </p>
        </Card>

        <Card title="🔥 Impact">
          <p className="text-sm text-gray-300">
            Current system load may impact responsiveness.
          </p>

          <p className="text-xs text-gray-500 mt-2">
            Risk Level: {(risk * 100).toFixed(0)}%
          </p>
        </Card>

      </div>

      {/* ⚡ ACTION */}
      {action && (
        <Card title="⚡ Recommended Action">
          <p className="text-white">{action.action?.type}</p>

          <p className="text-yellow-400 text-sm mt-1">
            {action.reason}
          </p>

          <p className="text-xs text-gray-400 mt-2">
            Confidence: {(action.confidence * 100 || 0).toFixed(0)}%
          </p>

          <div className="flex gap-3 mt-3">
            {action.requires_user && (
              <button className="bg-blue-600 px-4 py-2 rounded hover:bg-blue-700">
                Approve
              </button>
            )}
            <button className="bg-gray-700 px-4 py-2 rounded hover:bg-gray-600">
              Ignore
            </button>
          </div>
        </Card>
      )}

      {/* 🔍 DETAILS */}
      <Card title="🔍 Deep Analysis">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-blue-400 text-xs"
        >
          {expanded ? "Hide details" : "Show details"}
        </button>

        {expanded && (
          <div className="mt-3 space-y-2">
            {data.decision_trace?.map((d: string, i: number) => (
              <p key={i} className="text-xs text-gray-400">
                • {d}
              </p>
            ))}
          </div>
        )}
      </Card>

    </div>
  );
}

/* ---------- COMPONENTS ---------- */

function KPI({ title, value, highlight = false }: any) {
  return (
    <motion.div whileHover={{ scale: 1.05 }}
      className={`p-4 rounded-xl ${highlight ? "bg-red-900" : "bg-gray-900"}`}>
      <p className="text-xs text-gray-400">{title}</p>
      <p className="text-lg font-semibold">{value}</p>
    </motion.div>
  );
}

function Card({ title, children }: any) {
  return (
    <motion.div whileHover={{ y: -2 }}
      className="bg-gray-900 p-4 rounded-xl border border-gray-800">
      <p className="text-xs text-gray-400 mb-2">{title}</p>
      {children}
    </motion.div>
  );
}
