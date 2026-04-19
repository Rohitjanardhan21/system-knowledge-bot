# ---------------------------------------------------------
# 🧠 DYNAMIC CAUSAL GRAPH (LEARNING-BASED)
# ---------------------------------------------------------

"""
Learns causal relationships between metrics using:
- Correlation
- Temporal co-movement
- Incremental updates

Future:
- Granger causality
- Bayesian networks
"""

import numpy as np
from collections import defaultdict, deque


class DynamicCausalGraph:

    def __init__(self, max_history=50):
        self.history = defaultdict(lambda: deque(maxlen=max_history))
        self.graph = defaultdict(dict)  # {source: {target: weight}}

        self.metrics = ["cpu", "memory", "disk"]

    # -----------------------------------------------------
    # 📊 UPDATE HISTORY
    # -----------------------------------------------------
    def update(self, state: dict):

        for m in self.metrics:
            value = state.get(m, 0)
            self.history[m].append(value)

    # -----------------------------------------------------
    # 🔗 COMPUTE RELATIONSHIPS
    # -----------------------------------------------------
    def compute_graph(self):

        for src in self.metrics:
            for tgt in self.metrics:

                if src == tgt:
                    continue

                if len(self.history[src]) < 5:
                    continue

                x = np.array(self.history[src])
                y = np.array(self.history[tgt])

                if np.std(x) == 0 or np.std(y) == 0:
                    continue

                corr = np.corrcoef(x, y)[0, 1]

                # Only keep meaningful relationships
                if abs(corr) > 0.5:
                    self.graph[src][tgt] = round(float(corr), 2)

    # -----------------------------------------------------
    # 🔍 GET CAUSAL CHAIN (LEARNED)
    # -----------------------------------------------------
    def get_chain(self, start_metric):

        chain = [start_metric]
        visited = set()

        current = start_metric

        while current in self.graph:

            if current in visited:
                break

            visited.add(current)

            # pick strongest relation
            next_nodes = self.graph[current]

            if not next_nodes:
                break

            next_metric = max(next_nodes, key=next_nodes.get)

            chain.append(next_metric)
            current = next_metric

        return chain

    # -----------------------------------------------------
    # 🔥 GET ROOT CANDIDATES
    # -----------------------------------------------------
    def get_root_candidates(self):

        incoming = defaultdict(int)

        for src in self.graph:
            for tgt in self.graph[src]:
                incoming[tgt] += 1

        roots = []

        for m in self.metrics:
            if incoming[m] == 0:
                roots.append(m)

        return roots

    # -----------------------------------------------------
    # 📊 EXPORT GRAPH
    # -----------------------------------------------------
    def export(self):
        return dict(self.graph)
