import { useEffect, useState } from "react";
import { connectWebSocket } from "../services/wsClient";
import CausalGraph from "../components/CausalGraph";

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer
} from "recharts";

const safe = (v: any, d = 0) => (typeof v === "number" ? v : d);

export default function Dashboard() {

  const [data, setData] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [rewards, setRewards] = useState<number[]>([]);
  const [selectedSim, setSelectedSim] = useState<any>(null);

  useEffect(() => {
    const ws = connectWebSocket((incoming: any) => {

      setData(incoming);

      setHistory(prev => [
        ...prev.slice(-50),
        {
          time: new Date().toLocaleTimeString(),
          cpu: safe(incoming.cpu),
          memory: safe(incoming.memory)
        }
      ]);

      if (incoming.execution?.reward !== undefined) {
        setRewards(prev => [
          ...prev.slice(-50),
          incoming.execution.reward
        ]);
      }
    });

    return () => ws?.close();
  }, []);

  if (!data) return <div className="p-6 text-white">Connecting...</div>;

  const decision = data.decision_data || {};
  const exec = data.execution || {};
  const causal = data.causal || {};
  const temporal = data.temporal || {};
  const prediction = data.prediction;
  const diagnosis = data.diagnosis;

  const cpu = safe(data.cpu);
  const memory = safe(data.memory);
  const disk = safe(data.disk);
  const systemRisk = safe(data.system_risk);

  const primaryCause = causal.primary_cause || {};

  // ---------------- ACTIONS ----------------
  const triggerProcessAction = async (action: string, pid: number, name: string) => {
    await fetch("http://127.0.0.1:8000/system/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        target_pid: pid,
        target_name: name,
        executable: true
      })
    });
  };

  const triggerAction = async (action: string) => {
    await fetch("http://127.0.0.1:8000/system/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, executable: true })
    });
  };

  const setMode = async (mode: string) => {
    await fetch("http://127.0.0.1:8000/system/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode })
    });
  };

  return (
    <div className="min-h-screen bg-black text-white p-6 space-y-6">

      <h1 className="text-2xl text-green-400">AI Ops Console</h1>

      {/* 🧠 SYSTEM INSIGHT */}
      <Card title="🧠 System Insight">
        {diagnosis ? (
          <div className="space-y-2">
            <p className="text-green-400 text-lg font-semibold">
              {diagnosis.summary}
            </p>
            <p className="text-sm text-gray-400">
              {diagnosis.details}
            </p>
            <p className="text-yellow-400 text-sm">
              💡 {diagnosis.suggestion}
            </p>

            {data.autonomous_action && (
              <button
                className="bg-green-600 px-3 py-2 rounded mt-2"
                onClick={() => triggerAction(data.autonomous_action.action)}
              >
                ⚡ Fix Automatically
              </button>
            )}
          </div>
        ) : (
          <p className="text-gray-400">No insights</p>
        )}
      </Card>

      {/* KPI */}
      <div className="grid grid-cols-6 gap-4">
        <KPI title="CPU" value={`${cpu.toFixed(1)}%`} />
        <KPI title="Memory" value={`${memory.toFixed(1)}%`} />
        <KPI title="Disk" value={`${disk.toFixed(1)}%`} />
        <KPI title="Nodes" value={data.node_count} />
        <KPI title="Mode" value={data.mode || "unknown"} />
        <KPI title="Risk" value={`${(systemRisk * 100).toFixed(1)}%`} highlight={systemRisk > 0.7} />
      </div>

      {/* MODE */}
      <Card title="⚙️ Mode">
        {["manual", "assist", "autonomous"].map(m => (
          <button key={m}
            className="bg-gray-700 px-2 py-1 m-1 rounded"
            onClick={() => setMode(m)}>
            {m}
          </button>
        ))}
      </Card>

      {/* MAIN GRID */}
      <div className="grid grid-cols-3 gap-6">

        {/* LEFT */}
        <div className="col-span-2 space-y-6">

          <Card title="System Metrics">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={history}>
                <XAxis dataKey="time" />
                <YAxis />
                <Tooltip />
                <Line dataKey="cpu" stroke="#22c55e" />
                <Line dataKey="memory" stroke="#3b82f6" />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <Card title="🚨 Main Issue">
            <p className="text-red-400 text-xl">
              {primaryCause.type || "No issue"}
            </p>
          </Card>

          <Card title="🌐 Causal Graph">
            <CausalGraph graph={data.causal_graph || {}} />
          </Card>

        </div>

        {/* RIGHT */}
        <div className="space-y-6">

          <Card title="Execution">
            <p>Status: {exec.status}</p>
            <p>Reward: {safe(exec.reward).toFixed(2)}</p>
          </Card>

          <Card title="🧠 Explanation">
            {exec.explanation ? (
              <div className="text-xs">
                <p>Cause: {exec.explanation.cause}</p>
                <p>Improvement: {exec.explanation.improvement}</p>
                <p>Status: {exec.explanation.result}</p>
              </div>
            ) : <p>No explanation</p>}
          </Card>

          <Card title="🚨 Alerts">
            {data.alerts?.map((a: any, i: number) => (
              <p key={i}>{a.type}</p>
            ))}
          </Card>

          <Card title="📜 Logs">
            {data.logs?.slice(-10).map((l: any, i: number) => (
              <p key={i}>[{l.level}] {l.message}</p>
            ))}
          </Card>

        </div>
      </div>
    </div>
  );
}

function KPI({ title, value, highlight = false }: any) {
  return (
    <div className={`p-4 rounded ${highlight ? "bg-red-900" : "bg-gray-900"}`}>
      <p className="text-xs">{title}</p>
      <p className="text-lg">{value}</p>
    </div>
  );
}

function Card({ title, children }: any) {
  return (
    <div className="bg-gray-900 p-4 rounded-xl border border-gray-800">
      <h3 className="text-sm text-gray-400 mb-2">{title}</h3>
      {children}
    </div>
  );
}
