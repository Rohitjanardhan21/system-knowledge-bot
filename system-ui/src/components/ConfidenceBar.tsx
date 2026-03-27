type Props = {
  value?: number;
};

export default function ConfidenceBar({ value = 0 }: Props) {

  // 🔥 Clamp value safely between 0–1
  const safeValue = Math.max(0, Math.min(1, value || 0));
  const percentage = Math.round(safeValue * 100);

  // 🎨 Color based on confidence
  const getColor = () => {
    if (safeValue >= 0.8) return "bg-green-500";
    if (safeValue >= 0.5) return "bg-yellow-400";
    return "bg-red-500";
  };

  // 🧠 Label for interpretation
  const getLabel = () => {
    if (safeValue >= 0.8) return "High Confidence";
    if (safeValue >= 0.5) return "Moderate Confidence";
    return "Low Confidence";
  };

  return (
    <div className="w-full space-y-1">

      {/* Header */}
      <div className="flex justify-between text-xs text-gray-300">
        <span>Confidence</span>
        <span>{percentage}%</span>
      </div>

      {/* Bar */}
      <div className="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
        <div
          className={`${getColor()} h-2 rounded-full transition-all duration-500 ease-in-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Label */}
      <div className="text-xs text-gray-400">
        {getLabel()}
      </div>

    </div>
  );
}
