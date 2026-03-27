import { motion } from "framer-motion";
import GlassCard from "./GlassCard";

export default function MetricCard({ label, value }: any) {
  return (
    <GlassCard>
      <motion.div
        key={value}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <p className="text-gray-400 text-sm">{label}</p>
        <p className="text-2xl font-bold">{value}%</p>
      </motion.div>
    </GlassCard>
  );
}
