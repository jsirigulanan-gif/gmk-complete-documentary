from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

MODE_ORDER = {"NORMAL": 0, "SAFE_MODE": 1, "READ_ONLY": 2, "EMERGENCY_STOP": 3}
CLOSED_STATES = {"RESOLVED", "CLOSED"}

@dataclass(frozen=True)
class SafetyDecision:
    mode: str
    active_incident_refs: tuple[dict[str, Any], ...]
    actions: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "active_incident_refs": [dict(x) for x in self.active_incident_refs],
            "actions": list(self.actions),
            "reasons": list(self.reasons),
        }


def _active_incidents(state) -> list[dict[str, Any]]:
    out=[]
    reg=(getattr(state, "registries", {}) or {}).get("INCIDENT_REGISTRY")
    if reg is None:
        return out
    for entry in reg.entries.values():
        if entry.object_type != "INCIDENT" or entry.active_version is None:
            continue
        obj=state.objects.get((entry.object_id, int(entry.active_version)))
        if obj and obj.get("workflow_state") not in CLOSED_STATES:
            out.append(obj)
    return out


def derive_safety_decision(state, root: Path | None = None) -> SafetyDecision:
    """Derive global safety mode from ACTIVE, non-resolved incidents.

    INCIDENT records supply containment facts. Policy determines the effective mode;
    the Incident object itself is never global safety-mode authority.
    """
    actions=set(); refs=[]; reasons=[]
    incidents=_active_incidents(state)
    for inc in incidents:
        refs.append({"id":inc["id"],"version":int(inc["version"])})
        ia=set((inc.get("containment") or {}).get("actions") or [])
        actions.update(ia)
        reasons.append(f"{inc['id']}@{inc['version']} {inc.get('severity','')} {inc.get('incident_type','')}")

    # Policy defaults are deliberately conservative.  The YAML policy may turn
    # specific combinations into stronger modes, but cannot weaken these floors.
    mode="NORMAL"
    if "BLOCK_EXTERNAL_OPERATIONS" in actions or "PAUSE_RENDERING" in actions or "QUARANTINE_ARTIFACTS" in actions or "ISOLATE_REGISTRY" in actions:
        mode="SAFE_MODE"
    if "FREEZE_MUTATIONS" in actions:
        mode="READ_ONLY"
    if "FREEZE_MUTATIONS" in actions and "BLOCK_EXTERNAL_OPERATIONS" in actions:
        mode="EMERGENCY_STOP"

    if root is not None:
        path=Path(root)/"config"/"incidents_policies.yaml"
        if path.exists():
            raw=yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for rule in raw.get("mode_rules") or []:
                need=set(rule.get("requires_actions") or [])
                min_sev=rule.get("minimum_severity")
                severity_order={"INFO":0,"MINOR":1,"MAJOR":2,"CRITICAL":3}
                qualifying=incidents
                if min_sev:
                    qualifying=[x for x in incidents if severity_order.get(x.get("severity"),-1)>=severity_order.get(min_sev,99)]
                if qualifying and need.issubset(actions):
                    candidate=rule.get("mode","NORMAL")
                    if MODE_ORDER.get(candidate,-1)>MODE_ORDER.get(mode,-1):
                        mode=candidate

    return SafetyDecision(mode, tuple(refs), tuple(sorted(actions)), tuple(reasons))


class IncidentSafetyController:
    def __init__(self, engine):
        self.engine=engine

    def decision(self) -> SafetyDecision:
        return derive_safety_decision(self.engine.snapshot(), self.engine.root)

    @property
    def mode(self) -> str:
        return self.decision().mode

    def assert_external_allowed(self, operation_type: str, *, recovery: bool=False) -> None:
        d=self.decision()
        if recovery:
            return
        if d.mode in {"SAFE_MODE","EMERGENCY_STOP"} or "BLOCK_EXTERNAL_OPERATIONS" in d.actions:
            from gmk_state.errors import StateEngineError
            raise StateEngineError("INCIDENT_EXTERNAL_OPERATION_BLOCKED", f"External operation {operation_type} is blocked by incident safety mode {d.mode}.", details=d.to_dict())

    def assert_render_allowed(self, *, final: bool=False) -> None:
        d=self.decision()
        if d.mode=="EMERGENCY_STOP" or "PAUSE_RENDERING" in d.actions:
            from gmk_state.errors import StateEngineError
            raise StateEngineError("INCIDENT_RENDERING_BLOCKED", "Rendering is paused by incident containment.", details=d.to_dict())
