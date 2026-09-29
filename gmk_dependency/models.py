from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
from copy import deepcopy


class NodeKind(str, Enum):
    OBJECT = "OBJECT"
    ARTIFACT = "ARTIFACT"


class ImpactDisposition(str, Enum):
    UNAFFECTED = "UNAFFECTED"
    REVALIDATE = "REVALIDATE"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


_DISPOSITION_RANK = {
    ImpactDisposition.UNAFFECTED: 0,
    ImpactDisposition.REVALIDATE: 1,
    ImpactDisposition.STALE: 2,
    ImpactDisposition.BLOCKED: 3,
}


def max_disposition(a: ImpactDisposition, b: ImpactDisposition) -> ImpactDisposition:
    return a if _DISPOSITION_RANK[a] >= _DISPOSITION_RANK[b] else b


@dataclass(frozen=True, order=True)
class NodeKey:
    kind: NodeKind
    node_id: str
    version: int

    def to_ref(self) -> dict[str, Any]:
        if self.kind == NodeKind.OBJECT:
            return {"id": self.node_id, "version": self.version}
        return {"artifact_id": self.node_id, "version": self.version}

    def label(self) -> str:
        prefix = "OBJ" if self.kind == NodeKind.OBJECT else "ART"
        return f"{prefix}:{self.node_id}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "ref": self.to_ref()}


@dataclass(frozen=True)
class DependencyEdge:
    dependent: NodeKey
    target: NodeKey
    relation: str
    source_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependent": self.dependent.to_dict(),
            "target": self.target.to_dict(),
            "relation": self.relation,
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class ChangeSet:
    object_id: str
    previous_version: int
    new_version: int
    changed_paths: tuple[str, ...]
    impact_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "previous_version": self.previous_version,
            "new_version": self.new_version,
            "changed_paths": list(self.changed_paths),
            "impact_tags": list(self.impact_tags),
        }


@dataclass(frozen=True)
class ImpactRecord:
    node: NodeKey
    disposition: ImpactDisposition
    relation: str
    depth: int
    immediate_dependency: NodeKey
    root_previous: NodeKey
    root_new: NodeKey
    reason_code: str
    message: str
    blast_radius: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "node": self.node.to_dict(),
            "disposition": self.disposition.value,
            "relation": self.relation,
            "depth": self.depth,
            "immediate_dependency": self.immediate_dependency.to_dict(),
            "root_previous": self.root_previous.to_dict(),
            "root_new": self.root_new.to_dict(),
            "reason_code": self.reason_code,
            "message": self.message,
            "blast_radius": self.blast_radius,
        }
        if self.path is not None:
            out["path"] = self.path
        return out


@dataclass
class DependencyImpactReport:
    root_previous: NodeKey
    root_new: NodeKey
    change_set: ChangeSet
    impacts: list[ImpactRecord] = field(default_factory=list)
    frozen_stops: list[NodeKey] = field(default_factory=list)
    policy_ref: dict[str, Any] | None = None

    @property
    def blast_radius(self) -> str:
        values = [x.blast_radius for x in self.impacts]
        order = {"LOCAL": 0, "SCENE": 1, "ACT": 2, "PROJECT": 3}
        return max(values, key=lambda x: order.get(x, 0)) if values else "LOCAL"

    def to_payload(self) -> dict[str, Any]:
        return {
            "root_change": {
                "previous": self.root_previous.to_dict(),
                "new": self.root_new.to_dict(),
            },
            "change_set": self.change_set.to_dict(),
            "impacts": [x.to_dict() for x in self.impacts],
            "frozen_stops": [x.to_dict() for x in self.frozen_stops],
            "blast_radius": self.blast_radius,
            "policy_ref": deepcopy(self.policy_ref),
        }
