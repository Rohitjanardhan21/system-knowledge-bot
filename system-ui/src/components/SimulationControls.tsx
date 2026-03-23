import { useState, useEffect } from "react";

export default function SimulationControls({ onChange }: any) {
  const [cpu, setCpu] = useState(40);
  const [memory, setMemory] = useState(50);

  useEffect(() => {
    onChange({ cpu, memory });
  }, [cpu, memory]);

  return (
    <div style={{
      background: "#111827",
      padding: 20,
      borderRadius: 12,
      marginTop: 20,
      border: "1px solid #374151"
    }}>
      <h3>🎛️ Simulation Controls</h3>

      <div style={{ marginTop: 10 }}>
        <p>CPU: {cpu}%</p>
        <input
          type="range"
          min="0"
          max="100"
          value={cpu}
          onChange={(e) => setCpu(Number(e.target.value))}
        />
      </div>

      <div style={{ marginTop: 10 }}>
        <p>Memory: {memory}%</p>
        <input
          type="range"
          min="0"
          max="100"
          value={memory}
          onChange={(e) => setMemory(Number(e.target.value))}
        />
      </div>
    </div>
  );
}
