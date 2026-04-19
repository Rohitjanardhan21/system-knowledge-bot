from collections import defaultdict


class MultiNodeEngine:

    def analyze(self, nodes):

        if not nodes:
            return {}

        node_count = len(nodes)

        cpu_values = []
        process_map = defaultdict(list)

        # -----------------------------------------
        # COLLECT DATA
        # -----------------------------------------
        for node in nodes:

            metrics = node.get("metrics", {})
            cpu = metrics.get("cpu", 0)

            cpu_values.append(cpu)

            for p in metrics.get("processes", []):
                name = p.get("name", "unknown")
                process_map[name].append({
                    "node": node.get("node"),
                    "cpu": p.get("cpu", 0)
                })

        # -----------------------------------------
        # CLUSTER LOAD
        # -----------------------------------------
        avg_cpu = sum(cpu_values) / max(node_count, 1)

        cluster_status = "healthy"
        if avg_cpu > 75:
            cluster_status = "high_load"
        if avg_cpu > 90:
            cluster_status = "critical"

        # -----------------------------------------
        # DISTRIBUTED CAUSE DETECTION
        # -----------------------------------------
        distributed_causes = []

        for name, instances in process_map.items():

            if len(instances) >= max(2, node_count // 2):

                total_cpu = sum(i["cpu"] for i in instances)

                distributed_causes.append({
                    "process": name,
                    "nodes": [i["node"] for i in instances],
                    "total_cpu": round(total_cpu, 2),
                    "spread": len(instances)
                })

        distributed_causes.sort(
            key=lambda x: x["total_cpu"], reverse=True
        )

        # -----------------------------------------
        # PROPAGATION DETECTION
        # -----------------------------------------
        propagation = None

        if distributed_causes:
            top = distributed_causes[0]

            if top["spread"] > 1:
                propagation = {
                    "type": "distributed_load",
                    "process": top["process"],
                    "affected_nodes": top["nodes"]
                }

        return {
            "cluster_status": cluster_status,
            "average_cpu": round(avg_cpu, 2),
            "distributed_causes": distributed_causes[:3],
            "propagation": propagation
        }
