"""Prerequisite graph: cycle rejection and topological ordering (NetworkX)."""
import networkx as nx

class CycleError(ValueError):
    pass

class PrereqGraph:
    def __init__(self):
        self.g = nx.DiGraph()

    def add_topic(self, name):
        self.g.add_node(name)

    def add_dependency(self, prerequisite, topic):
        """Edge prerequisite -> topic. Rejected (with explanation) if it creates a cycle."""
        self.g.add_edge(prerequisite, topic)
        if not nx.is_directed_acyclic_graph(self.g):
            cycle = [u for u, _ in nx.find_cycle(self.g)]
            self.g.remove_edge(prerequisite, topic)
            raise CycleError("Rejected: circular dependency " + " -> ".join(map(str, cycle + [cycle[0]])))

    def order(self):
        return list(nx.topological_sort(self.g))

    def prerequisites(self, topic):
        return set(self.g.predecessors(topic))

    def dependents(self, topic):
        return set(self.g.successors(topic))
