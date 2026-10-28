import type { ReactNode } from "react";

export default function GlassCard({ children }: { children: ReactNode }) {
  return (
    <div className="
      bg-white/5
      backdrop-blur-xl
      border border-white/10
      rounded-2xl
      p-4
      shadow-lg
    ">
      {children}
    </div>
  );
}
