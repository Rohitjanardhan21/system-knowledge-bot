export default function AgentPanel({ data }: any) {
  if (!data) return null;

  const cpu = data.cpu;
  const memory = data.memory;

  const cpuAgent =
    cpu > 80
      ? "CPU Agent: System is under heavy load."
      : "CPU Agent: Load is normal.";

  const memAgent =
    memory > 80
      ? "Memory Agent: Memory pressure detected."
      : "Memory Agent: Memory stable.";

  const verdict =
    cpu > 80 || memory > 80
      ? "⚠️ Consensus: Intervention required."
      : "✅ Consensus: System stable.";

  return (
    <div className="glass-card p-4 space-y-2">
      <h2 className="text-lg font-semibold">🤖 Agent Debate</h2>
      <p>{cpuAgent}</p>
      <p>{memAgent}</p>
      <p className="font-bold">{verdict}</p>
    </div>
  );
}
