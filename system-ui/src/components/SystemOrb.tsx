import { motion } from "framer-motion";

export default function SystemOrb({ cpu }: { cpu: number }) {

  const scale = 0.9 + cpu / 120;
  const glow = cpu > 70 ? "shadow-red-500/50" : "shadow-blue-500/40";

  return (
    <motion.div
      animate={{
        scale,
      }}
      transition={{ type: "spring", stiffness: 120 }}
      className={`
        w-48 h-48 rounded-full
        bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500
        ${glow}
        shadow-2xl
        flex items-center justify-center
      `}
    >
      <span className="text-2xl font-bold">{cpu}%</span>
    </motion.div>
  );
}
