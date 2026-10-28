import { useEffect } from "react";

type Alert = {
id: string;
message: string;
level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
time?: string;
};

type Props = {
alerts: Alert[];
removeAlert: (id: string) => void;
};

const getDuration = (level: Alert["level"]) => {
  switch (level) {
    case "HIGH": return 6000;
    case "MEDIUM": return 4000;
    default: return 3000;
  }
};

export default function AlertToast({ alerts, removeAlert }: Props) {

// --------------------------------------------------
// AUTO DISMISS (SMART)
// --------------------------------------------------
useEffect(() => {
  const timeouts = alerts
    .filter((alert) => alert.level !== "CRITICAL")
    .map((alert) => window.setTimeout(
      () => removeAlert(alert.id),
      getDuration(alert.level),
    ));

  return () => timeouts.forEach((timeout) => window.clearTimeout(timeout));
}, [alerts, removeAlert]);

// --------------------------------------------------
// STYLE MAPPING
// --------------------------------------------------
const getStyle = (level: string) => {
switch (level) {
case "CRITICAL":
return "bg-red-600/90 border-red-400 text-red-100";
case "HIGH":
return "bg-orange-500/90 border-orange-300 text-orange-100";
case "MEDIUM":
return "bg-yellow-500/90 border-yellow-300 text-yellow-900";
default:
return "bg-green-600/90 border-green-300 text-green-100";
}
};

const getIcon = (level: string) => {
switch (level) {
case "CRITICAL": return "🚨";
case "HIGH": return "⚠️";
case "MEDIUM": return "⚡";
default: return "✅";
}
};

// --------------------------------------------------
// UI
// --------------------------------------------------
return ( <div className="fixed top-6 right-6 z-50 space-y-3 w-[320px]">

  {alerts.map((alert) => (
    <div
      key={alert.id}
      className={`
        border rounded-xl px-4 py-3 shadow-2xl backdrop-blur
        transition-all duration-300 ease-in-out
        animate-slideIn
        ${getStyle(alert.level)}
      `}
    >
      {/* HEADER */}
      <div className="flex justify-between items-start">

        <div className="flex gap-2 items-center">
          <span className="text-lg">{getIcon(alert.level)}</span>
          <span className="font-semibold text-sm">
            {alert.level}
          </span>
        </div>

        <button
          onClick={() => removeAlert(alert.id)}
          className="text-xs opacity-70 hover:opacity-100"
        >
          ✕
        </button>
      </div>

      {/* MESSAGE */}
      <div className="mt-2 text-sm leading-relaxed">
        {alert.message}
      </div>

      {/* FOOTER */}
      <div className="mt-2 flex justify-between text-[10px] opacity-70">
        <span>{alert.time || "now"}</span>

        {/* HUMAN SAFETY NOTE */}
        {alert.level === "CRITICAL" && (
          <span className="text-red-200">
            human attention required
          </span>
        )}
      </div>
    </div>
  ))}

  {/* ANIMATION */}
  <style>{`
    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateX(40px);
      }
      to {
        opacity: 1;
        transform: translateX(0);
      }
    }
    .animate-slideIn {
      animation: slideIn 0.3s ease-out;
    }
  `}</style>

</div>

);
}
