from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable


def ref_key(ref: dict[str, Any]) -> tuple[str, int] | None:
    if "id" in ref and "version" in ref:
        return ref["id"], int(ref["version"])
    return None


def artifact_key(ref: dict[str, Any]) -> tuple[str, int] | None:
    if "artifact_id" in ref and "version" in ref:
        return ref["artifact_id"], int(ref["version"])
    return None


@dataclass
class StateView:
    objects: dict[tuple[str, int], dict[str, Any]]
    artifacts: dict[tuple[str, int], dict[str, Any]]
    configs: dict[tuple[str, str], dict[str, Any]]

    @classmethod
    def build(
        cls,
        objects: Iterable[dict[str, Any]] = (),
        artifacts: Iterable[dict[str, Any]] = (),
        configs: Iterable[dict[str, Any]] = (),
    ) -> "StateView":
        om = {(o["id"], int(o["version"])): o for o in objects}
        am = {(a["artifact_id"], int(a["version"])): a for a in artifacts}
        cm = {(c["config_id"], str(c["version"])): c for c in configs if "config_id" in c and "version" in c}
        return cls(om, am, cm)

    def resolve_object(self, ref: dict[str, Any] | None) -> dict[str, Any] | None:
        if not ref:
            return None
        key = ref_key(ref)
        return self.objects.get(key) if key else None

    def resolve_artifact(self, ref: dict[str, Any] | None) -> dict[str, Any] | None:
        if not ref:
            return None
        key = artifact_key(ref)
        return self.artifacts.get(key) if key else None

    def resolve_target(self, ref: dict[str, Any] | None) -> dict[str, Any] | None:
        if not ref:
            return None
        if "artifact_id" in ref:
            return self.resolve_artifact(ref)
        return self.resolve_object(ref)

    def versions(self, object_id: str) -> list[dict[str, Any]]:
        return sorted((o for (oid, _), o in self.objects.items() if oid == object_id), key=lambda x: x["version"])

    def object_type(self, ref: dict[str, Any]) -> str | None:
        obj = self.resolve_object(ref)
        return obj.get("object_type") if obj else None
