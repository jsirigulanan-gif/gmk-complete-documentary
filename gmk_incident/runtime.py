from __future__ import annotations
from copy import deepcopy
from typing import Any
from gmk_state.errors import StateEngineError

INCIDENT_FLOW={
    "OPEN":{"CONTAINED","INVESTIGATING"},
    "CONTAINED":{"INVESTIGATING","RECOVERY_READY"},
    "INVESTIGATING":{"CONTAINED","RECOVERY_READY"},
    "RECOVERY_READY":{"RESOLVED"},
    "RESOLVED":{"CLOSED"},
    "CLOSED":set(),
}

class IncidentRuntime:
    def __init__(self, engine):
        self.engine=engine

    def open(self, *, incident_type:str, severity:str, summary:str, affected_scope:dict[str,Any], containment_actions=(), related_refs=()) -> dict[str,Any]:
        payload={
            "incident_type":incident_type,
            "severity":severity,
            "detected_at":self.engine.now(),
            "summary":summary,
            "affected_scope":deepcopy(affected_scope),
            "related_refs":deepcopy(list(related_refs)),
            "containment":{"actions":list(dict.fromkeys(containment_actions))},
            "workflow_state":"OPEN",
            "verification_refs":[],
        }
        tx=self.engine.begin(recovery=True)
        ref=tx.create_object("INCIDENT",payload,activate=True)
        tx.commit()
        return ref

    def transition(self, incident_ref:dict[str,Any], to_state:str, *, containment_actions=None, verification_refs=None) -> dict[str,Any]:
        cur=self.engine.resolver().resolve(incident_ref["id"], mode="HEAD")
        if cur is None or cur.get("object_type")!="INCIDENT":
            raise StateEngineError("INCIDENT_NOT_FOUND","Incident does not exist.")
        fr=cur.get("workflow_state")
        if to_state not in INCIDENT_FLOW.get(fr,set()):
            raise StateEngineError("INCIDENT_STATE_TRANSITION_INVALID",f"Incident transition {fr} -> {to_state} is not allowed.")
        patch={"workflow_state":to_state}
        if containment_actions is not None:
            patch["containment"]={"actions":list(dict.fromkeys(containment_actions))}
        if verification_refs is not None:
            patch["verification_refs"]=deepcopy(list(verification_refs))
        if to_state in {"RESOLVED","CLOSED"} and not (patch.get("verification_refs") or cur.get("verification_refs")):
            raise StateEngineError("INCIDENT_RESOLVED_WITHOUT_VERIFICATION","Resolved/closed incident requires verification evidence.")
        tx=self.engine.begin(recovery=True)
        new=tx.create_version(cur["id"],base_version=cur["version"],patch=patch)
        tx.promote_active_version(cur["id"],new["version"],confirm_locked_impact=True)
        tx.commit()
        return new
