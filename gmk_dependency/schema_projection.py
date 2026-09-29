from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from copy import deepcopy
import json

from gmk_semantics.catalog import SchemaCatalog
from .models import NodeKey, NodeKind, DependencyEdge


def _json_pointer_get(doc: Any, fragment: str) -> Any:
    if not fragment or fragment == "#":
        return doc
    if fragment.startswith("#"):
        fragment = fragment[1:]
    if not fragment:
        return doc
    if not fragment.startswith("/"):
        raise KeyError(fragment)
    cur = doc
    for raw in fragment.split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, list):
            cur = cur[int(key)]
        else:
            cur = cur[key]
    return cur


def _looks_like_target(value: Any) -> bool:
    return isinstance(value, dict) and "version" in value and ("id" in value or "artifact_id" in value)


def _node_from_ref(ref: dict[str, Any]) -> NodeKey:
    if "artifact_id" in ref:
        return NodeKey(NodeKind.ARTIFACT, str(ref["artifact_id"]), int(ref["version"]))
    return NodeKey(NodeKind.OBJECT, str(ref["id"]), int(ref["version"]))


@dataclass(frozen=True)
class ProjectionEntry:
    target: dict[str, Any]
    relation: str
    source_path: str

    def dependency_ref(self) -> dict[str, Any]:
        return {"target": deepcopy(self.target), "relation": self.relation}


class SchemaDependencyCompiler:
    """Compile normalized dependencies from schema-annotated authoritative refs.

    The annotations are implementation metadata on the frozen v1 schemas:
    `x-gmk-dependency-relation`.  The stored BaseObject.dependencies[] remains a
    derived projection and is never treated as the authoritative source.
    """

    def __init__(self, root: Path, catalog: SchemaCatalog | None = None):
        self.root = Path(root)
        self.catalog = catalog or SchemaCatalog(self.root)
        registry = json.loads((self.root / "schema/schema-registry.json").read_text(encoding="utf-8"))
        self.by_id: dict[str, dict[str, Any]] = {}
        for sid, rel in registry["schemas"].items():
            self.by_id[sid] = json.loads((self.root / rel).read_text(encoding="utf-8"))

    def schema_for_artifact(self, artifact: dict[str, Any]) -> dict[str, Any] | None:
        sid = ((artifact.get("schema_header") or {}).get("schema_id"))
        if sid:
            return self.by_id.get(str(sid))
        typ = str(artifact.get("artifact_type", ""))
        for doc in self.by_id.values():
            for part in doc.get("allOf", []):
                props = part.get("properties", {}) if isinstance(part, dict) else {}
                if props.get("artifact_type", {}).get("const") == typ:
                    return doc
        return None

    def _resolve_ref(self, ref: str, current_schema: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        if ref.startswith("#"):
            return current_schema, _json_pointer_get(current_schema, ref)
        base, sep, frag = ref.partition("#")
        target_doc = self.by_id.get(base)
        if target_doc is None:
            raise KeyError(f"Unresolved schema ref: {ref}")
        return target_doc, _json_pointer_get(target_doc, "#" + frag if sep else "#")

    def _walk(self, schema: Any, value: Any, current_doc: dict[str, Any], path: str, seen: set[tuple[int, int, str]], out: list[ProjectionEntry]):
        if not isinstance(schema, dict):
            return
        marker = (id(schema), id(value), path)
        if marker in seen:
            return
        seen.add(marker)

        relation = schema.get("x-gmk-dependency-relation")
        if relation and _looks_like_target(value):
            out.append(ProjectionEntry(deepcopy(value), str(relation), path or "/"))

        ref = schema.get("$ref")
        if ref:
            try:
                doc, resolved = self._resolve_ref(str(ref), current_doc)
                self._walk(resolved, value, doc, path, seen, out)
            except KeyError:
                pass

        for part in schema.get("allOf", []) or []:
            self._walk(part, value, current_doc, path, seen, out)
        # oneOf/anyOf are walked conservatively; duplicate edges are normalized later.
        for key in ("oneOf", "anyOf"):
            for part in schema.get(key, []) or []:
                self._walk(part, value, current_doc, path, seen, out)

        props = schema.get("properties") or {}
        if isinstance(value, dict):
            for name, child_schema in props.items():
                if name in value:
                    child_path = f"{path}/{name}" if path else f"/{name}"
                    self._walk(child_schema, value[name], current_doc, child_path, seen, out)

        items = schema.get("items")
        if items is not None and isinstance(value, list):
            for idx, item in enumerate(value):
                child_path = f"{path}/{idx}" if path else f"/{idx}"
                self._walk(items, item, current_doc, child_path, seen, out)

    def project_entries(self, record: dict[str, Any], *, artifact: bool = False) -> list[ProjectionEntry]:
        schema = self.schema_for_artifact(record) if artifact else self.catalog.schema_for_object_type(str(record.get("object_type", "")))
        if not schema:
            return []
        entries: list[ProjectionEntry] = []
        self._walk(schema, record, schema, "", set(), entries)
        # Stable de-duplication ignores display-only source_path differences caused by shared refs.
        dedup: dict[tuple[str, str, int, str], ProjectionEntry] = {}
        for e in entries:
            if "artifact_id" in e.target:
                key = ("ARTIFACT", str(e.target["artifact_id"]), int(e.target["version"]), e.relation)
            else:
                key = ("OBJECT", str(e.target["id"]), int(e.target["version"]), e.relation)
            dedup.setdefault(key, e)
        return sorted(dedup.values(), key=lambda e: (
            0 if "id" in e.target else 1,
            str(e.target.get("id") or e.target.get("artifact_id")),
            int(e.target["version"]), e.relation
        ))

    def project_object(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        return [entry.dependency_ref() for entry in self.project_entries(obj, artifact=False)]

    def object_edges(self, obj: dict[str, Any]) -> list[DependencyEdge]:
        dep = NodeKey(NodeKind.OBJECT, str(obj["id"]), int(obj["version"]))
        return [DependencyEdge(dep, _node_from_ref(e.target), e.relation, e.source_path) for e in self.project_entries(obj, artifact=False)]

    def artifact_edges(self, artifact: dict[str, Any]) -> list[DependencyEdge]:
        dep = NodeKey(NodeKind.ARTIFACT, str(artifact["artifact_id"]), int(artifact["version"]))
        return [DependencyEdge(dep, _node_from_ref(e.target), e.relation, e.source_path) for e in self.project_entries(artifact, artifact=True)]
