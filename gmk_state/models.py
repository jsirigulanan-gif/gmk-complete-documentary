from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
from copy import deepcopy
from gmk_semantics.model import sha256_json
from .artifact_registry import ArtifactRegistrySnapshot

@dataclass(frozen=True)
class VersionLocator:
    version: int
    uri: str
    decision_sha256: str
    record_sha256: str
    created_at: str
    updated_at: str
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,data):
        return cls(int(data['version']),str(data['uri']),str(data['decision_sha256']),str(data['record_sha256']),str(data['created_at']),str(data['updated_at']))

@dataclass
class RegistryEntry:
    object_id: str
    object_type: str
    head_version: int
    active_version: int | None
    versions: dict[int, VersionLocator] = field(default_factory=dict)
    def clone(self):
        return RegistryEntry(self.object_id, self.object_type, self.head_version, self.active_version, dict(self.versions))
    def to_dict(self):
        return {"object_id": self.object_id, "object_type": self.object_type, "head_version": self.head_version,
                "active_version": self.active_version, "versions": {str(k): v.to_dict() for k,v in sorted(self.versions.items())}}
    @classmethod
    def from_dict(cls,data):
        return cls(str(data['object_id']),str(data['object_type']),int(data['head_version']),None if data.get('active_version') is None else int(data['active_version']),{int(k):VersionLocator.from_dict(v) for k,v in (data.get('versions') or {}).items()})

@dataclass
class RegistrySnapshot:
    registry_id: str
    version: int = 1
    entries: dict[str, RegistryEntry] = field(default_factory=dict)
    def clone(self): return RegistrySnapshot(self.registry_id, self.version, {k:v.clone() for k,v in self.entries.items()})
    def body(self): return {"registry_id": self.registry_id, "version": self.version, "entries": {k:v.to_dict() for k,v in sorted(self.entries.items())}}
    @property
    def sha256(self): return sha256_json(self.body())
    def to_dict(self):
        d=self.body(); d["sha256"]=self.sha256; return d
    @classmethod
    def from_dict(cls,data):
        return cls(str(data['registry_id']),int(data['version']),{k:RegistryEntry.from_dict(v) for k,v in (data.get('entries') or {}).items()})

@dataclass(frozen=True)
class ActionAudit:
    action_type: str
    result_refs: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)
    def to_dict(self): return {"action_type": self.action_type, "result_refs": list(self.result_refs), "detail": deepcopy(self.detail)}
    @classmethod
    def from_dict(cls,data):return cls(str(data['action_type']),tuple(data.get('result_refs') or ()),deepcopy(data.get('detail') or {}))

@dataclass(frozen=True)
class TransactionAudit:
    transaction_id: str
    committed_at: str
    manifest_version_before: int
    manifest_version_after: int
    registry_versions_before: dict[str,int]
    registry_versions_after: dict[str,int]
    actions: tuple[ActionAudit,...]
    def to_dict(self):
        return {"transaction_id":self.transaction_id,"committed_at":self.committed_at,
                "manifest_version_before":self.manifest_version_before,"manifest_version_after":self.manifest_version_after,
                "registry_versions_before":dict(self.registry_versions_before),"registry_versions_after":dict(self.registry_versions_after),
                "actions":[a.to_dict() for a in self.actions]}
    @classmethod
    def from_dict(cls,data):
        return cls(str(data['transaction_id']),str(data['committed_at']),int(data['manifest_version_before']),int(data['manifest_version_after']),{str(k):int(v) for k,v in (data.get('registry_versions_before') or {}).items()},{str(k):int(v) for k,v in (data.get('registry_versions_after') or {}).items()},tuple(ActionAudit.from_dict(x) for x in (data.get('actions') or [])))

@dataclass
class RuntimeState:
    objects: dict[tuple[str,int],dict[str,Any]] = field(default_factory=dict)
    artifacts: dict[tuple[str,int],dict[str,Any]] = field(default_factory=dict)
    configs: dict[tuple[str,str],dict[str,Any]] = field(default_factory=dict)
    registries: dict[str,RegistrySnapshot] = field(default_factory=dict)
    artifact_registry: ArtifactRegistrySnapshot = field(default_factory=ArtifactRegistrySnapshot)
    manifest_version: int = 1
    project_state: str = "BOOTSTRAPPED"
    project_state_entered_at: str | None = None
    audit_log: tuple[TransactionAudit,...] = ()
    dependency_invalidations: dict[Any,dict[str,Any]] = field(default_factory=dict)
    safety_mode: str = "NORMAL"
    dependency_integrity_issues: tuple[dict[str,Any], ...] = ()
    gate_evaluations: tuple[dict[str,Any], ...] = ()
    def clone(self):
        return RuntimeState(
            objects={k:deepcopy(v) for k,v in self.objects.items()}, artifacts={k:deepcopy(v) for k,v in self.artifacts.items()},
            configs={k:deepcopy(v) for k,v in self.configs.items()}, registries={k:v.clone() for k,v in self.registries.items()}, artifact_registry=self.artifact_registry.clone(),
            manifest_version=self.manifest_version, project_state=self.project_state, project_state_entered_at=self.project_state_entered_at,
            audit_log=tuple(self.audit_log), dependency_invalidations=deepcopy(self.dependency_invalidations),
            safety_mode=self.safety_mode, dependency_integrity_issues=tuple(deepcopy(x) for x in self.dependency_integrity_issues),
            gate_evaluations=tuple(deepcopy(x) for x in self.gate_evaluations))
