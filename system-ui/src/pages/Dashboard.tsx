import { useEffect, useState } from "react";
import { fetchSystemData } from "../services/api";
import type { SystemData } from "../types/system";

import MetricCard from "../components/MetricCard";
import StatusBar from "../components/StatusBar";
import TemporalPanel from "../components/TemporalPanel";
import CausalPanel from "../components/CausalPanel";
import DecisionPanel from "../components/DecisionPanel";
import ExplanationPanel from "../components/ExplanationPanel";
import CpuChart from "../components/CpuChart";
import SystemStoryPanel from "../components/SystemStoryPanel";
import AlertBanner from "../components/AlertBanner";
import DigitalTwinPanel from "../components/DigitalTwinPanel";
import SimulationControls from "../components/SimulationControls";

export default function Dashboard() {
  const [data, setData] = useState<SystemData | null>(null);
  const [simulation, setSimulation] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await fetchSystemData();
      setData(res);
      setLoading(false);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Failed to connect to backend");
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 1000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div style={styles.center}>
        <h2>⚡ Initializing System Intelligence...</h2>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.center}>
        <h2 style={{ color: "red" }}>{error}</h2>
      </div>
    );
  }

  if (!data) return null;

  // 🔥 Simulation override
  const displayData = simulation
    ? {
        ...data,
        cpu: simulation.cpu,
        memory: simulation.memory,
      }
    : data;

  return (
    <div style={styles.container}>
      
      {/* HEADER */}
      <div style={styles.header}>
        <h1>⚡ System Intelligence</h1>
        <p style={styles.subHeader}>
          Real-time OS reasoning engine
        </p>
      </div>

      {/* METRICS */}
      <div style={styles.metricsRow}>
        <MetricCard label="CPU" value={displayData.cpu} />
        <MetricCard label="Memory" value={displayData.memory} />
        <MetricCard label="Disk" value={displayData.disk} />
      </div>

      {/* STATUS */}
      <StatusBar posture={displayData.posture} />

      {/* 🧠 SYSTEM STORY */}
      <SystemStoryPanel data={displayData} />

      {/* 🎛️ SIMULATION CONTROLS */}
      <SimulationControls onChange={setSimulation} />

      {/* ⚠️ ALERT */}
      <AlertBanner decision={displayData.decision} />

      {/* 🔮 DIGITAL TWIN */}
      <DigitalTwinPanel data={displayData} />

      {/* 📊 CHART */}
      <div style={styles.card}>
        <CpuChart cpu={displayData.cpu} />
      </div>

      {/* 📦 GRID */}
      <div style={styles.grid}>
        <div style={styles.card}>
          <TemporalPanel temporal={displayData.temporal} />
        </div>

        <div style={styles.card}>
          <CausalPanel causal={displayData.causal} />
        </div>

        <div style={styles.card}>
          <DecisionPanel decision={displayData.decision} />
        </div>

        <div style={styles.card}>
          <ExplanationPanel explanation={displayData.explanation} />
        </div>
      </div>

    </div>
  );
}

const styles = {
  container: {
    padding: 30,
    minHeight: "100vh",
  },

  header: {
    marginBottom: 20
  },

  subHeader: {
    opacity: 0.6,
    fontSize: 14
  },

  metricsRow: {
    display: "flex",
    gap: 20,
    marginBottom: 25
  },

  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 20,
    marginTop: 20
  },

  card: {
    padding: 18,
    borderRadius: 16,
    background: "rgba(30,41,59,0.6)",
    backdropFilter: "blur(12px)",
    border: "1px solid rgba(255,255,255,0.05)",
    boxShadow: "0 8px 30px rgba(0,0,0,0.3)"
  },

  center: {
    height: "100vh",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    color: "white"
  }
};
