import GlassCard from "./GlassCard";

export default function StoryPanel({ story }: any) {
  return (
    <GlassCard>
      <h2 className="text-lg font-semibold mb-2">System Intelligence</h2>
      <p className="text-gray-300 leading-relaxed italic">
        {story}
      </p>
    </GlassCard>
  );
}
