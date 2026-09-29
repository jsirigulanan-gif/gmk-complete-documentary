from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

from .catalog import SchemaCatalog
from .model import ValidationIssue, decision_hash
from .state import StateView

Rule = Callable[[dict[str, Any], StateView, SchemaCatalog], list[ValidationIssue]]


class SemanticValidator:
    def __init__(self, root: Path):
        self.root = root
        self.catalog = SchemaCatalog(root)
        from .rules import OBJECT_RULES, ARTIFACT_RULES, GLOBAL_RULES
        self.object_rules = OBJECT_RULES
        self.artifact_rules = ARTIFACT_RULES
        self.global_rules = GLOBAL_RULES

    def decision_hash(self, obj: dict[str, Any]) -> str:
        return decision_hash(obj, self.catalog.derived_root_fields(obj.get("object_type", "")))

    def validate_object(self, obj: dict[str, Any], state: StateView) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for rule in self.object_rules.get("*", []):
            issues.extend(rule(obj, state, self.catalog))
        for rule in self.object_rules.get(obj.get("object_type"), []):
            issues.extend(rule(obj, state, self.catalog))
        return issues

    def validate_artifact(self, artifact: dict[str, Any], state: StateView) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for rule in self.artifact_rules.get("*", []):
            issues.extend(rule(artifact, state, self.catalog))
        for rule in self.artifact_rules.get(artifact.get("artifact_type"), []):
            issues.extend(rule(artifact, state, self.catalog))
        return issues

    def validate_state(self, state: StateView) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for obj in state.objects.values():
            issues.extend(self.validate_object(obj, state))
        for artifact in state.artifacts.values():
            issues.extend(self.validate_artifact(artifact, state))
        for rule in self.global_rules:
            issues.extend(rule(state, self.catalog))
        return issues
