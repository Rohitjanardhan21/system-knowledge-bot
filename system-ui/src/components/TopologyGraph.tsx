import ForceGraph2D from "react-force-graph-2d";

export default function TopologyGraph({ nodes }: { nodes: any[] }) {

  const graphData = {
    nodes: nodes.map(n => ({ id: n.node_id, cpu: n.cpu })),
    links: generateLinks(nodes)
  };

  function generateLinks(nodes:any[]){
    const links:any[]=[];
    for(let i=0;i<nodes.length;i++){
      for(let j=i+1;j<nodes.length;j++){
        links.push({source:nodes[i].node_id,target:nodes[j].node_id});
      }
    }
    return links;
  }

  return (
    <div className="bg-black rounded-2xl p-4">
      <ForceGraph2D
        graphData={graphData}
        nodeCanvasObject={(node:any, ctx)=>{
          ctx.fillStyle = node.cpu>80?"red":"green";
          ctx.beginPath();
          ctx.arc(node.x,node.y,10,0,2*Math.PI);
          ctx.fill();
          ctx.fillText(node.id,node.x+12,node.y);
        }}
        onNodeClick={(node:any)=>alert(`${node.id} CPU:${node.cpu}`)}
      />
    </div>
  );
}
