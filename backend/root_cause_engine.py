class RootCauseEngine:

    def analyze(self, nodes):
        if not nodes:
            return {}

        # pick most loaded node
        worst_node = max(nodes, key=lambda n: n.get("cpu", 0))

        processes = worst_node.get("processes", [])

        if not processes:
            return {
                "node": worst_node.get("node_id"),
                "cause": "No process data available"
            }

        # 🔥 find top CPU process
        top_process = max(processes, key=lambda p: p.get("cpu_percent", 0))

        return {
            "node": worst_node.get("node_id"),
            "process": top_process.get("name"),
            "cpu": top_process.get("cpu_percent"),
            "explanation": f"{top_process.get('name')} is consuming {top_process.get('cpu_percent')}% CPU"
        }
