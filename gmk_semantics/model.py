from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Iterable
import hashlib
import json


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "ERROR"
    target: str | None = None
    path: str | None = None
    related: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["related"] = list(self.related)
        return d


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# Fields deliberately excluded from decision hashes because they are identity,
# lineage, operational, or live-derived envelope state. The authoritative
# production payload remains in the projection.
_DECISION_EXCLUDE = {
    "schema_header", "id", "object_type", "version", "supersedes",
    "status", "lock_state", "created_at", "updated_at", "dependencies",
    "stale", "approval_summary",
}


def decision_projection(obj: dict[str, Any], derived_fields: Iterable[str] = ()) -> dict[str, Any]:
    excluded = _DECISION_EXCLUDE | set(derived_fields)
    return {k: v for k, v in obj.items() if k not in excluded}


def decision_hash(obj: dict[str, Any], derived_fields: Iterable[str] = ()) -> str:
    return sha256_json(decision_projection(obj, derived_fields))
