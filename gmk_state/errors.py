from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable

@dataclass(frozen=True)
class StateEngineIssue:
    code: str
    message: str
    path: str | None = None
    target: str | None = None
    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "path": self.path, "target": self.target}

class StateEngineError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Any = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.details = code, message, details

class ConcurrencyConflict(StateEngineError):
    pass

class ValidationFailure(StateEngineError):
    def __init__(self, issues: Iterable[Any]):
        items = list(issues)
        super().__init__("STATE_VALIDATION_FAILED", f"Staged state failed validation with {len(items)} issue(s).", details=items)
        self.issues = items
