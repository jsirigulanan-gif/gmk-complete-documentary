from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

from .models import ImpactDisposition


@dataclass(frozen=True)
class DependencyPolicy:
    config_id: str
    version: str
    relation_defaults: dict[str, ImpactDisposition]
    critical_tags: dict[str, ImpactDisposition]
    path_tag_rules: tuple[tuple[str, str], ...]
    frozen_artifact_types: frozenset[str]
    frozen_object_rules: tuple[tuple[str, str, str], ...]
    non_impact_tags: frozenset[str]

    @classmethod
    def load(cls, path: Path) -> "DependencyPolicy":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        relation_defaults = {
            k: ImpactDisposition(v) for k, v in (data.get("relation_defaults") or {}).items()
        }
        critical_tags = {
            k: ImpactDisposition(v) for k, v in (data.get("critical_tag_overrides") or {}).items()
        }
        path_rules = tuple(
            (str(item["contains"]).lower(), str(item["tag"]).upper())
            for item in (data.get("path_tag_rules") or [])
        )
        frozen_artifacts = frozenset(data.get("frozen_artifact_types") or [])
        non_impact_tags = frozenset(str(x).upper() for x in (data.get('non_impact_tags') or []))
        frozen_objects = tuple(
            (str(item["object_type"]), str(item["field"]), str(item["equals"]))
            for item in (data.get("frozen_object_rules") or [])
        )
        return cls(
            config_id=str(data.get("config_id", "GMK_DEPENDENCY_POLICY")),
            version=str(data.get("version", "1.0.0")),
            relation_defaults=relation_defaults,
            critical_tags=critical_tags,
            path_tag_rules=path_rules,
            frozen_artifact_types=frozen_artifacts,
            frozen_object_rules=frozen_objects,
            non_impact_tags=non_impact_tags,
        )

    def disposition_for(self, relation: str, impact_tags: set[str]) -> ImpactDisposition:
        if impact_tags and impact_tags.issubset(self.non_impact_tags):
            return ImpactDisposition.UNAFFECTED
        result = self.relation_defaults.get(relation, ImpactDisposition.STALE)
        rank = {
            ImpactDisposition.UNAFFECTED: 0,
            ImpactDisposition.REVALIDATE: 1,
            ImpactDisposition.STALE: 2,
            ImpactDisposition.BLOCKED: 3,
        }
        for tag in impact_tags:
            override = self.critical_tags.get(tag)
            if override is not None and rank[override] > rank[result]:
                result = override
        return result

    def tags_for_paths(self, paths: list[str] | tuple[str, ...]) -> set[str]:
        tags: set[str] = set()
        for path in paths:
            low = path.lower()
            for token, tag in self.path_tag_rules:
                if token in low:
                    tags.add(tag)
        if not tags:
            tags.add("GENERAL")
        return tags

    def is_frozen_object(self, obj: dict[str, Any]) -> bool:
        if obj.get("lock_state") == "SYSTEM_FROZEN":
            return True
        for typ, field, expected in self.frozen_object_rules:
            if obj.get("object_type") == typ and str(obj.get(field)) == expected:
                return True
        return False

    def is_frozen_artifact(self, artifact: dict[str, Any]) -> bool:
        return str(artifact.get("artifact_type")) in self.frozen_artifact_types
