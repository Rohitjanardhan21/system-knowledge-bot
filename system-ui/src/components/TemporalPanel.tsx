export default function TemporalPanel({ temporal }: any) {
  const renderMetric = (name: string, metric: any) => {
    return (
      <div style={{ marginBottom: 10 }}>
        <strong>{name.toUpperCase()}</strong>
        <p>Pattern: {metric.pattern}</p>
        <p>Slope: {metric.slope.toFixed(2)}</p>
        <p>Confidence: {(metric.confidence * 100).toFixed(0)}%</p>
      </div>
    );
  };

  return (
    <div>
      <h3>📈 Temporal Behavior</h3>
      {renderMetric("cpu", temporal.cpu)}
      {renderMetric("memory", temporal.memory)}
      {renderMetric("disk", temporal.disk)}
    </div>
  );
}
