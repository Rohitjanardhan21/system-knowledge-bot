import { useEffect, useState } from "react";

export default function ProcessModal({ process, onClose }: any) {

const [history, setHistory] = useState<any[]>([]);

useEffect(() => {
if (!process) return;

```
// simple simulated trend (can connect backend later)
setHistory(prev => [
  ...prev.slice(-20),
  {
    cpu: process.cpu,
    memory: process.memory,
    time: new Date().toLocaleTimeString()
  }
]);
```

}, [process]);

if (!process) return null;

return ( <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">

```
  <div className="bg-zinc-900 rounded-2xl p-6 w-[500px] space-y-4">

    {/* HEADER */}
    <div className="flex justify-between">
      <h2 className="text-xl font-semibold">
        {process.name}
      </h2>
      <button onClick={onClose}>✕</button>
    </div>

    {/* METRICS */}
    <div className="space-y-2">
      <div>CPU: {process.cpu}%</div>
      <div>Memory: {process.memory}%</div>
      <div>Nodes: {process.nodes?.join(", ")}</div>
    </div>

    {/* AI INSIGHT */}
    <div className="bg-zinc-800 p-3 rounded-lg text-sm">
      This process is contributing significantly to system load.
      Monitor for sustained usage before taking action.

      ⚠️ Human validation recommended.
    </div>

  </div>

</div>
```

);
}
