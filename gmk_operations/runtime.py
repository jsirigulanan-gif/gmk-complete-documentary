from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
import yaml

from gmk_state.errors import StateEngineError
from gmk_incident.safety import IncidentSafetyController

TERMINAL={"SUCCEEDED","PARTIALLY_SUCCEEDED","FAILED","CANCELED","UNKNOWN_EXTERNAL_STATE"}

@dataclass(frozen=True)
class OperationExecutionResult:
    outcome: str
    result: str = ""
    details: dict[str,Any] | None = None

    def __post_init__(self):
        if self.outcome not in {"SUCCEEDED","PARTIALLY_SUCCEEDED","FAILED","UNKNOWN_EXTERNAL_STATE"}:
            raise ValueError(f"Unsupported operation outcome {self.outcome}")

class ExternalStateUnknown(RuntimeError):
    pass

class OperationRuntime:
    """Exactly-once-intent wrapper around OPERATION Core Objects.

    The runtime does not pretend external systems are transactional. It records a
    RUNNING version before side effects, terminalizes only after a known outcome,
    and requires reconciliation for UNKNOWN_EXTERNAL_STATE.
    """
    def __init__(self, engine):
        self.engine=engine
        self.safety=IncidentSafetyController(engine)
        path=Path(engine.root)/"config"/"operations_policies.yaml"
        self.policy=yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _operation_heads(self):
        state=self.engine.snapshot();reg=state.registries.get("OPERATION_REGISTRY")
        if not reg:return []
        out=[]
        for e in reg.entries.values():
            obj=state.objects.get((e.object_id,int(e.head_version)))
            if obj:out.append(obj)
        return out

    @staticmethod
    def _intent_signature(*,operation_type,subject,external_target,request):
        return {"operation_type":operation_type,"subject":deepcopy(subject),"external_target":deepcopy(external_target),"request":deepcopy(request)}

    def _same_intent(self,obj,sig):
        return all(obj.get(k)==v for k,v in sig.items())

    def _policy_for(self, operation_type):
        for rule in self.policy.get("operation_rules") or []:
            if operation_type in set(rule.get("operation_types") or []):return rule
        return {}

    def _resolve_checkpoint(self,ref):
        if not ref:return None
        obj=self.engine.snapshot().objects.get((ref.get("id"),int(ref.get("version",0))))
        if not obj or obj.get("object_type")!="CHECKPOINT":return None
        return obj

    def plan(self, *, operation_type:str, subject:dict[str,Any], provider:str, action:str, input_fingerprint:str, idempotency_key:str, destination:str|None=None, human_confirmed:bool=False, checkpoint_ref:dict[str,Any]|None=None, compensation:dict[str,Any]|None=None) -> dict[str,Any]:
        self.safety.assert_external_allowed(operation_type)
        target={"provider":provider}
        if destination is not None:target["destination"]=destination
        request={"action":action,"input_fingerprint":input_fingerprint}
        sig=self._intent_signature(operation_type=operation_type,subject=subject,external_target=target,request=request)
        for obj in self._operation_heads():
            if obj.get("idempotency_key")!=idempotency_key:continue
            if not self._same_intent(obj,sig):
                raise StateEngineError("OPERATION_IDEMPOTENCY_COLLISION","Idempotency key already belongs to a different external intent.",details={"existing":{"id":obj["id"],"version":obj["version"]}})
            return {"operation_ref":{"id":obj["id"],"version":obj["version"]},"idempotent_replay":True,"workflow_state":obj.get("workflow_state")}

        rule=self._policy_for(operation_type)
        if rule.get("human_confirmation_required") and not human_confirmed:
            raise StateEngineError("DESTRUCTIVE_OPERATION_NOT_AUTHORIZED",f"{operation_type} requires explicit Human confirmation.")
        cp=None
        if rule.get("checkpoint_required"):
            cp=self._resolve_checkpoint(checkpoint_ref)
            if cp is None or cp.get("integrity_summary")!="PASS":
                raise StateEngineError("OPERATION_CHECKPOINT_REQUIRED",f"{operation_type} requires a verified Checkpoint.")

        authorization={"human_confirmed":bool(human_confirmed)}
        if human_confirmed:authorization["confirmed_at"]=self.engine.now()
        if checkpoint_ref:authorization["checkpoint_ref"]=deepcopy(checkpoint_ref)
        payload={
            **sig,
            "idempotency_key":idempotency_key,
            "workflow_state":"PLANNED",
            "attempts":[],
            "authorization":authorization,
        }
        if compensation is not None:payload["compensation"]=deepcopy(compensation)
        tx=self.engine.begin();ref=tx.create_object("OPERATION",payload,activate=True);tx.commit()
        return {"operation_ref":ref,"idempotent_replay":False,"workflow_state":"PLANNED"}

    def _head(self, operation_ref):
        obj=self.engine.resolver().resolve(operation_ref["id"],mode="HEAD")
        if not obj or obj.get("object_type")!="OPERATION":raise StateEngineError("OPERATION_NOT_FOUND","Operation does not exist.")
        return obj

    def _new_version(self,cur,patch,*,recovery=False):
        tx=self.engine.begin(recovery=recovery)
        ref=tx.create_version(cur["id"],base_version=cur["version"],patch=patch)
        tx.promote_active_version(cur["id"],ref["version"],confirm_locked_impact=True)
        tx.commit();return self._head(ref)

    def execute(self, operation_ref:dict[str,Any], executor:Callable[[dict[str,Any]],OperationExecutionResult]) -> dict[str,Any]:
        cur=self._head(operation_ref)
        self.safety.assert_external_allowed(cur["operation_type"])
        state=cur.get("workflow_state")
        if state in {"SUCCEEDED","PARTIALLY_SUCCEEDED"}:
            return {"operation_ref":{"id":cur["id"],"version":cur["version"]},"idempotent_replay":True,"workflow_state":state}
        if state=="UNKNOWN_EXTERNAL_STATE":
            raise StateEngineError("OPERATION_RECONCILIATION_REQUIRED","Operation external state is unknown; reconcile before any retry.")
        if state not in {"PLANNED","FAILED"}:
            raise StateEngineError("OPERATION_EXECUTION_STATE_INVALID",f"Cannot execute operation in state {state}.")
        attempts=deepcopy(cur.get("attempts") or [])
        n=len(attempts)+1
        attempts.append({"attempt":n,"started_at":self.engine.now()})
        running=self._new_version(cur,{"workflow_state":"RUNNING","attempts":attempts})
        try:
            result=executor(deepcopy(running))
            if not isinstance(result,OperationExecutionResult):
                raise TypeError("executor must return OperationExecutionResult")
        except ExternalStateUnknown as exc:
            attempts=deepcopy(running["attempts"]);attempts[-1]["finished_at"]=self.engine.now();attempts[-1]["result"]=str(exc) or "External outcome unknown"
            final=self._new_version(running,{"workflow_state":"UNKNOWN_EXTERNAL_STATE","attempts":attempts},recovery=True)
            return {"operation_ref":{"id":final["id"],"version":final["version"]},"idempotent_replay":False,"workflow_state":"UNKNOWN_EXTERNAL_STATE"}
        except Exception as exc:
            # A normal executor exception is a known invocation failure. Code that
            # cannot know whether the remote side effect happened must raise
            # ExternalStateUnknown instead.
            attempts=deepcopy(running["attempts"]);attempts[-1]["finished_at"]=self.engine.now();attempts[-1]["result"]=f"FAILED: {type(exc).__name__}: {exc}"
            final=self._new_version(running,{"workflow_state":"FAILED","attempts":attempts},recovery=True)
            return {"operation_ref":{"id":final["id"],"version":final["version"]},"idempotent_replay":False,"workflow_state":"FAILED","error":str(exc)}

        attempts=deepcopy(running["attempts"]);attempts[-1]["finished_at"]=self.engine.now();attempts[-1]["result"]=result.result or result.outcome
        try:
            final=self._new_version(running,{"workflow_state":result.outcome,"attempts":attempts})
        except Exception as commit_exc:
            # The remote call completed but local terminal recording did not. Never
            # retry the side effect blindly; quarantine it as unknown when possible.
            uncertain=deepcopy(running["attempts"]);uncertain[-1]["finished_at"]=self.engine.now();uncertain[-1]["result"]=f"REMOTE OUTCOME {result.outcome}; LOCAL TERMINAL COMMIT FAILED: {type(commit_exc).__name__}: {commit_exc}"
            try:
                final=self._new_version(running,{"workflow_state":"UNKNOWN_EXTERNAL_STATE","attempts":uncertain},recovery=True)
                return {"operation_ref":{"id":final["id"],"version":final["version"]},"idempotent_replay":False,"workflow_state":"UNKNOWN_EXTERNAL_STATE","local_commit_error":str(commit_exc)}
            except Exception:
                raise commit_exc
        return {"operation_ref":{"id":final["id"],"version":final["version"]},"idempotent_replay":False,"workflow_state":final["workflow_state"],"details":deepcopy(result.details or {})}

    def reconcile(self, operation_ref:dict[str,Any], *, outcome:str, evidence:str) -> dict[str,Any]:
        cur=self._head(operation_ref)
        if cur.get("workflow_state")!="UNKNOWN_EXTERNAL_STATE":
            raise StateEngineError("OPERATION_RECONCILIATION_STATE_INVALID","Only UNKNOWN_EXTERNAL_STATE can be reconciled.")
        if outcome not in {"SUCCEEDED","PARTIALLY_SUCCEEDED","FAILED","CANCELED"}:
            raise StateEngineError("OPERATION_RECONCILIATION_OUTCOME_INVALID",f"Invalid reconciliation outcome {outcome}.")
        attempts=deepcopy(cur.get("attempts") or [])
        if attempts:
            attempts[-1]["result"]=f"RECONCILED {outcome}: {evidence}"
            attempts[-1].setdefault("finished_at",self.engine.now())
        final=self._new_version(cur,{"workflow_state":outcome,"attempts":attempts},recovery=True)
        return {"operation_ref":{"id":final["id"],"version":final["version"]},"workflow_state":outcome}

    def reconcile_inflight_after_restart(self) -> list[dict[str,Any]]:
        changed=[]
        for obj in list(self._operation_heads()):
            if obj.get("workflow_state")!="RUNNING":continue
            attempts=deepcopy(obj.get("attempts") or [])
            if attempts:
                attempts[-1]["finished_at"]=self.engine.now();attempts[-1]["result"]="Runtime restart observed before terminal outcome; reconciliation required."
            final=self._new_version(obj,{"workflow_state":"UNKNOWN_EXTERNAL_STATE","attempts":attempts},recovery=True)
            changed.append({"id":final["id"],"version":final["version"]})
        return changed
