export default function AlertBanner({ decision }: any) {
  if (!decision || decision.urgency === "low") return null;

  const color =
    decision.urgency === "critical"
      ? "red"
      : decision.urgency === "high"
      ? "orange"
      : "yellow";

  return (
    <div style={{
      background: color,
      color: "black",
      padding: 12,
      borderRadius: 10,
      marginTop: 15,
      animation: "slideDown 0.4s ease",
      fontWeight: "bold"
    }}>
      ⚠️ {decision.reason}

      <style>
        {`
          @keyframes slideDown {
            from { transform: translateY(-10px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
          }
        `}
      </style>
    </div>
  );
}
