import { useState } from "react";

interface Action {
id: string;
action: string;
target?: string;
confidence?: number;
risk?: string;
description?: string;
}

interface Props {
actions: Action[];
onResolved?: (id: string) => void;
}

export default function ActionApproval({ actions, onResolved }: Props) {

const [loadingId, setLoadingId] = useState<string | null>(null);

// --------------------------------------------------
// API CALLS
// --------------------------------------------------
const approveAction = async (id: string) => {
setLoadingId(id);

```
try {
  const res = await fetch(`http://localhost:8000/actions/approve/${id}`, {
    method: "POST"
  });

  await res.json();

  onResolved?.(id);
} catch (err) {
  console.error("Approve failed:", err);
}

setLoadingId(null);
```

};

const rejectAction = async (id: string) => {
setLoadingId(id);

```
try {
  const res = await fetch(`http://localhost:8000/actions/reject/${id}`, {
    method: "POST"
  });

  await res.json();

  onResolved?.(id);
} catch (err) {
  console.error("Reject failed:", err);
}

setLoadingId(null);
```

};

// --------------------------------------------------
// UI HELPERS
// --------------------------------------------------
const getRiskColor = (risk?: string) => {
switch (risk) {
case "CRITICAL":
return "text-red-400 bg-red-500/10 border-red-500/30";
case "HIGH":
return "text-orange-400 bg-orange-500/10 border-orange-500/30";
case "MEDIUM":
return "text-yellow-400 bg-yellow-500/10 border-yellow-500/30";
default:
return "text-green-400 bg-green-500/10 border-green-500/30";
}
};

if (!actions || actions.length === 0) return null;

// --------------------------------------------------
// COMPONENT
// --------------------------------------------------
return ( <div className="fixed bottom-24 right-6 w-[350px] space-y-4 z-50">

```
  {actions.map((a) => (
    <div
      key={a.id}
      className="rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-900 to-black p-4 shadow-2xl"
    >

      {/* HEADER */}
      <div className="flex justify-between items-center mb-2">
        <div className="text-sm font-semibold">
          ⚙️ Action Required
        </div>

        <div className={`text-xs px-2 py-1 rounded border ${getRiskColor(a.risk)}`}>
          {a.risk || "LOW"}
        </div>
      </div>

      {/* DESCRIPTION */}
      <div className="text-sm text-zinc-300">
        {a.description || `${a.action} → ${a.target || "system"}`}
      </div>

      {/* CONFIDENCE */}
      {a.confidence !== undefined && (
        <div className="mt-2 text-xs text-zinc-500">
          Confidence: {(a.confidence * 100).toFixed(0)}%
        </div>
      )}

      {/* SAFETY NOTICE */}
      <div className="mt-3 text-xs text-yellow-500">
        ⚠️ Requires human validation before execution
      </div>

      {/* ACTION BUTTONS */}
      <div className="flex gap-2 mt-4">

        <button
          onClick={() => approveAction(a.id)}
          disabled={loadingId === a.id}
          className="flex-1 bg-green-600 hover:bg-green-700 px-3 py-2 rounded-lg text-sm transition"
        >
          {loadingId === a.id ? "Processing..." : "Approve"}
        </button>

        <button
          onClick={() => rejectAction(a.id)}
          disabled={loadingId === a.id}
          className="flex-1 bg-red-600 hover:bg-red-700 px-3 py-2 rounded-lg text-sm transition"
        >
          Reject
        </button>

      </div>

    </div>
  ))}

</div>
```

);
}
