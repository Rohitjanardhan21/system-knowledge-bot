export default function ReasoningGraph({ agents }: any) {

  if (!agents) return null;

  const order = ["observer", "analyzer", "predictor", "decision", "action"];

  const format = (o: any) => {
    if (o.cpu !== undefined) return `CPU ${o.cpu.toFixed(1)}%`;
    if (o.root_cause) return o.root_cause;
    if (o.trend !== undefined) return `Trend ${o.trend.toFixed(2)}`;
    if (o.action) return `${o.action}`;
    if (o.auto_execute !== undefined)
      return o.auto_execute ? "Executing" : "Pending";
    return "";
  };

  return (
    <div className="flex gap-4 overflow-x-auto">

      {order.map((k, i) => {
        const a = agents[k];
        if (!a) return null;

        return (
          <div key={k} className="flex items-center">

            <div className={`p-4 rounded-xl border min-w-[160px]
              ${a.status === "active"
                ? "border-green-500 animate-pulse"
                : a.status === "pending"
                ? "border-yellow-500"
                : "border-zinc-700"}
              bg-zinc-900`}>

              <div className="text-xs text-zinc-400">{k}</div>
              <div className="text-sm mt-1">{format(a.output)}</div>
              <div className="text-[10px] text-zinc-500 mt-2">{a.status}</div>

            </div>

            {i < order.length - 1 && (
              <div className="mx-2 text-zinc-600">→</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
