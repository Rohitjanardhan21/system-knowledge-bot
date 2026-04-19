class CounterfactualEngine:
    def __init__(self, causal_graph):
        self.graph = causal_graph

    # -----------------------------------------
    # Apply hypothetical change
    # -----------------------------------------
    def simulate(self, current_metrics, change):
        """
        change = {"cpu": -20}
        """

        simulated = current_metrics.copy()

        # Apply direct change
        for k, v in change.items():
            if k in simulated:
                simulated[k] = max(0, simulated[k] + v)

        # Propagate through graph
        for src, edges in self.graph.items():
            if src in change:
                delta = change[src]

                for target, weight in edges.items():
                    if target in simulated:
                        simulated[target] += delta * weight * 0.5

        return self._normalize(simulated)

    def _normalize(self, metrics):
        for k in metrics:
            metrics[k] = round(max(0, min(100, metrics[k])), 2)
        return metrics
