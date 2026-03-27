type Graph = {
  [key: string]: {
    [key: string]: number;
  };
};

export default function CausalGraph({ graph }: { graph: Graph }) {

  if (!graph || Object.keys(graph).length === 0) {
    return <p className="text-xs text-gray-400">No learned relationships yet</p>;
  }

  return (
    <div className="space-y-2 text-sm">
      {Object.entries(graph).map(([src, targets]) => (
        <div key={src}>
          {Object.entries(targets).map(([tgt, weight]) => (
            <div key={tgt} className="flex items-center space-x-2">
              <span className="text-blue-400">{src}</span>
              <span className="text-gray-500">→</span>
              <span className="text-green-400">{tgt}</span>
              <span className="text-xs text-gray-400">
                ({(weight * 100).toFixed(0)}%)
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
