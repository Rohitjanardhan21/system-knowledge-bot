import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip } from "recharts";

export default function CpuChart({ cpu }: { cpu: number }) {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    setData((prev) => [
      ...prev.slice(-20),
      { time: Date.now(), cpu }
    ]);
  }, [cpu]);

  return (
    <div style={{ marginTop: 20 }}>
      <h3>CPU Trend</h3>
      <LineChart width={500} height={200} data={data}>
        <XAxis dataKey="time" hide />
        <YAxis domain={[0, 100]} />
        <Tooltip />
        <Line type="monotone" dataKey="cpu" />
      </LineChart>
    </div>
  );
}
