export default function ExplanationPanel({ explanation }: { explanation: string }) {
  return (
    <div>
      <h3>🧠 System Insight</h3>

      <p style={{
        lineHeight: 1.6,
        fontSize: 15,
        opacity: 0.9
      }}>
        {explanation}
      </p>
    </div>
  );
}
