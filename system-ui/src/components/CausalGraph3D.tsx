import ForceGraph3D from "react-force-graph-3d";

export default function CausalGraph3D({ causal_graph }: any) {
  if (!causal_graph) return null;

  const nodes: any[] = [];
  const links: any[] = [];

  Object.keys(causal_graph).forEach((key) => {
    const [src, tgt] = key.split("->");

    nodes.push({ id: src });
    nodes.push({ id: tgt });

    links.push({
      source: src,
      target: tgt,
      value: causal_graph[key].confidence || 0.5,
    });
  });

  return (
    <div className="h-[400px] w-full">
      <ForceGraph3D
        graphData={{ nodes, links }}
        linkWidth={(link: any) => link.value * 5}
        nodeAutoColorBy="id"
      />
    </div>
  );
}
