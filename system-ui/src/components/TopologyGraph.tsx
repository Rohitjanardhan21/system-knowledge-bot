import ForceGraph2D from "react-force-graph-2d";

interface TopologyNode {
  node_id: string;
  cpu: number;
}

export default function TopologyGraph({ nodes }: { nodes: TopologyNode[] }) {
  const graphData = {
    nodes: nodes.map((node) => ({ id: node.node_id, cpu: node.cpu })),
    links: generateLinks(nodes),
  };

  function generateLinks(graphNodes: TopologyNode[]) {
    const links: Array<{ source: string; target: string }> = [];
    for (let i = 0; i < graphNodes.length; i++) {
      for (let j = i + 1; j < graphNodes.length; j++) {
        links.push({ source: graphNodes[i].node_id, target: graphNodes[j].node_id });
      }
    }
    return links;
  }

  return (
    <div className="bg-black rounded-2xl p-4">
      <ForceGraph2D
        graphData={graphData}
        nodeCanvasObject={(node, ctx) => {
          const cpu = "cpu" in node && typeof node.cpu === "number" ? node.cpu : 0;
          const x = node.x ?? 0;
          const y = node.y ?? 0;
          const id = String(node.id ?? "");
          ctx.fillStyle = cpu > 80 ? "red" : "green";
          ctx.beginPath();
          ctx.arc(x, y, 10, 0, 2 * Math.PI);
          ctx.fill();
          ctx.fillText(id, x + 12, y);
        }}
        onNodeClick={(node) => {
          const cpu = "cpu" in node && typeof node.cpu === "number" ? node.cpu : 0;
          alert(`${node.id} CPU:${cpu}`);
        }}
      />
    </div>
  );
}
