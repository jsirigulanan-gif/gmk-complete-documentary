from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Iterable

from .models import NodeKey, NodeKind, DependencyEdge


@dataclass
class DependencyGraph:
    forward: dict[NodeKey, tuple[DependencyEdge, ...]]
    reverse: dict[NodeKey, tuple[DependencyEdge, ...]]

    @classmethod
    def build(cls, edges: Iterable[DependencyEdge]) -> "DependencyGraph":
        f: dict[NodeKey, list[DependencyEdge]] = defaultdict(list)
        r: dict[NodeKey, list[DependencyEdge]] = defaultdict(list)
        for edge in edges:
            f[edge.dependent].append(edge)
            r[edge.target].append(edge)
        return cls(
            {k: tuple(sorted(v, key=lambda x:(x.target.label(), x.relation, x.source_path))) for k,v in f.items()},
            {k: tuple(sorted(v, key=lambda x:(x.dependent.label(), x.relation, x.source_path))) for k,v in r.items()},
        )

    def dependencies_of(self, node: NodeKey) -> tuple[DependencyEdge, ...]:
        return self.forward.get(node, ())

    def dependents_of(self, node: NodeKey) -> tuple[DependencyEdge, ...]:
        return self.reverse.get(node, ())

    def detect_cycles(self) -> list[list[NodeKey]]:
        # Exact-version graph cycles are not always illegal (e.g. audit cross-links),
        # but the engine exposes them so semantic policy can decide. Tarjan SCC.
        index = 0
        stack: list[NodeKey] = []
        on_stack: set[NodeKey] = set()
        indices: dict[NodeKey,int] = {}
        low: dict[NodeKey,int] = {}
        cycles: list[list[NodeKey]] = []

        nodes = set(self.forward) | set(self.reverse)
        def strong(v: NodeKey):
            nonlocal index
            indices[v] = low[v] = index; index += 1
            stack.append(v); on_stack.add(v)
            for e in self.forward.get(v, ()):
                w = e.target
                if w not in indices:
                    strong(w); low[v] = min(low[v], low[w])
                elif w in on_stack:
                    low[v] = min(low[v], indices[w])
            if low[v] == indices[v]:
                comp=[]
                while True:
                    w=stack.pop(); on_stack.remove(w); comp.append(w)
                    if w==v: break
                if len(comp)>1 or any(e.target==v for e in self.forward.get(v,())):
                    cycles.append(sorted(comp))
        for n in sorted(nodes):
            if n not in indices: strong(n)
        return cycles
