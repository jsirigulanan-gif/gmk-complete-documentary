from __future__ import annotations
from pathlib import Path
from typing import Any
import json


class SchemaCatalog:
    def __init__(self, root: Path):
        self.root = root
        self.by_id: dict[str, dict[str, Any]] = {}
        for p in list((root / "schema").rglob("*.schema.json")) + list((root / "artifacts/contracts").rglob("*.schema.json")):
            doc = json.loads(p.read_text(encoding="utf-8"))
            if "$id" in doc:
                self.by_id[doc["$id"]] = doc

    def schema_for_object_type(self, object_type: str) -> dict[str, Any] | None:
        wanted = object_type.upper()
        for doc in self.by_id.values():
            for part in doc.get("allOf", []):
                props = part.get("properties", {}) if isinstance(part, dict) else {}
                if props.get("object_type", {}).get("const") == wanted:
                    return doc
        return None


    def schema_for_artifact_type(self, artifact_type: str) -> dict[str, Any] | None:
        wanted = artifact_type.upper()
        for doc in self.by_id.values():
            for part in doc.get("allOf", []):
                props = part.get("properties", {}) if isinstance(part, dict) else {}
                if props.get("artifact_type", {}).get("const") == wanted:
                    return doc
        return None

    @staticmethod
    def root_properties(schema: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out.update(schema.get("properties", {}))
        for part in schema.get("allOf", []):
            if isinstance(part, dict):
                out.update(part.get("properties", {}))
        return out

    def derived_root_fields(self, object_type: str) -> set[str]:
        schema = self.schema_for_object_type(object_type)
        if not schema:
            return set()
        return {
            name for name, spec in self.root_properties(schema).items()
            if isinstance(spec, dict) and spec.get("x-gmk-field-class") == "DERIVED"
        }
