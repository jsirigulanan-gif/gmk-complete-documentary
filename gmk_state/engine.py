from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable
from gmk_semantics import SemanticValidator, StateView
from gmk_dependency import DependencyEngine, NodeKey, NodeKind
from gmk_gate import GateEngine
from .errors import ConcurrencyConflict, StateEngineError, ValidationFailure, StateEngineIssue
from .ids import IDAllocator
from .models import RuntimeState, TransactionAudit, RegistrySnapshot
from .artifact_registry import ArtifactRegistrySnapshot, build_artifact_registry, ARTIFACT_REGISTRY_ID
from .registry import build_registries, global_index, locator_for
from .resolver import Resolver
from .schema_validation import StructuralValidator
from gmk_incident.safety import derive_safety_decision

TransitionAuthorizer = Callable[[str, str, RuntimeState], bool]

class StateEngine:
    """Authoritative in-memory mutation foundation for frozen GMK Schema v1."""
    def __init__(self, root:Path, *, objects:Iterable[dict[str,Any]]=(), artifacts:Iterable[dict[str,Any]]=(), configs:Iterable[dict[str,Any]]=(), registries:dict[str,RegistrySnapshot]|None=None, artifact_registry:ArtifactRegistrySnapshot|None=None, manifest_version:int=1, project_state:str='BOOTSTRAPPED', project_state_entered_at:str|None=None, audit_log:Iterable[TransactionAudit|dict[str,Any]]=(), gate_evaluations:Iterable[dict[str,Any]]=(), clock:Callable[[],Any]|None=None, transition_authorizer:TransitionAuthorizer|None=None):
        self.root=Path(root); self.semantic=SemanticValidator(self.root); self.structural=StructuralValidator(self.root)
        self.dependency=DependencyEngine(self.root,self.semantic.catalog)
        self.gates=GateEngine(self.root)
        self._lock=RLock(); self._clock=clock or (lambda:datetime.now(timezone.utc)); self.transition_authorizer=transition_authorizer
        om={(o['id'],int(o['version'])):deepcopy(o) for o in objects}
        am={(a['artifact_id'],int(a['version'])):deepcopy(a) for a in artifacts}
        cm={(c['config_id'],str(c['version'])):deepcopy(c) for c in configs if 'config_id'in c and 'version'in c}
        core_regs={k:v.clone() for k,v in registries.items()} if registries is not None else build_registries(om,self.semantic.decision_hash)
        art_reg=artifact_registry.clone() if artifact_registry is not None else build_artifact_registry(am.values())
        audits=tuple(x if isinstance(x,TransactionAudit) else TransactionAudit.from_dict(x) for x in audit_log)
        self._state=RuntimeState(objects=om,artifacts=am,configs=cm,registries=core_regs,artifact_registry=art_reg,manifest_version=int(manifest_version),project_state=project_state,audit_log=audits,gate_evaluations=tuple(deepcopy(x) for x in gate_evaluations))
        issues=self.dependency.projection_issues(om.values())
        self._cold_start_dependency_summary={'drift_roots':0,'invalidations':0,'changed_objects':0}
        if issues:
            self._state.safety_mode='READ_ONLY'
            self._state.dependency_integrity_issues=tuple(deepcopy(x) for x in issues)
        else:
            summary=self.dependency.recompute_live_state(self._state,self.semantic,self.now())
            idx=global_index(self._state.registries)
            for key in summary['changed_objects']:
                obj=self._state.objects[key]; rid=idx.get(obj['id'])
                if rid:
                    dec=self.semantic.decision_hash(obj)
                    self._state.registries[rid].entries[obj['id']].versions[int(obj['version'])]=locator_for(obj,dec)
            self._cold_start_dependency_summary={'drift_roots':summary['drift_roots'],'invalidations':summary['invalidations'],'changed_objects':len(summary['changed_objects'])}
        if not self._state.dependency_integrity_issues:
            self._state.safety_mode=derive_safety_decision(self._state,self.root).mode
        self._state.project_state_entered_at=project_state_entered_at or self.now(); self._allocator=IDAllocator(k[0] for k in om); self._tx_counter=max([int(x.transaction_id.split('_')[-1]) for x in audits if x.transaction_id.startswith('TX_') and x.transaction_id.split('_')[-1].isdigit()] or [0])
    def now(self)->str:
        value=self._clock()
        if isinstance(value,str):return value
        if isinstance(value,datetime):
            if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
            return value.isoformat().replace('+00:00','Z')
        raise TypeError('clock must return RFC3339 string or datetime')
    def next_transaction_id(self)->str:
        with self._lock:self._tx_counter+=1; return f'TX_{self._tx_counter:06d}'
    def allocate_id(self,object_type:str,occupied:set[str])->str:return self._allocator.allocate(object_type,occupied)
    def snapshot(self)->RuntimeState:
        with self._lock:return self._state.clone()
    def resolver(self)->Resolver:return Resolver(self.snapshot())
    @property
    def manifest_version(self)->int:
        with self._lock:return self._state.manifest_version
    @property
    def project_state(self)->str:
        with self._lock:return self._state.project_state
    def registry_versions(self):
        with self._lock:
            out={rid:r.version for rid,r in self._state.registries.items()};out[ARTIFACT_REGISTRY_ID]=self._state.artifact_registry.version;return out
    def registry_snapshots(self):
        with self._lock:
            out={rid:r.to_dict() for rid,r in self._state.registries.items()};out[ARTIFACT_REGISTRY_ID]=self._state.artifact_registry.to_dict();return out
    def artifact_registry_snapshot(self):
        with self._lock:return self._state.artifact_registry.to_dict()
    def audit_log(self):
        with self._lock:return [x.to_dict() for x in self._state.audit_log]
    @property
    def safety_mode(self)->str:
        with self._lock:return self._state.safety_mode
    def dependency_integrity_issues(self):
        with self._lock:return [deepcopy(x) for x in self._state.dependency_integrity_issues]
    def cold_start_dependency_summary(self):
        with self._lock:return deepcopy(self._cold_start_dependency_summary)
    def dependency_graph(self):
        with self._lock:return self.dependency.build_graph(self._state.clone())
    def dependency_invalidation(self,node_id:str,version:int,*,artifact:bool=False):
        key=NodeKey(NodeKind.ARTIFACT if artifact else NodeKind.OBJECT,node_id,int(version))
        with self._lock:return deepcopy(self._state.dependency_invalidations.get(key))
    def evaluate_gate(self,gate_id:str):
        with self._lock:
            return self.gates.evaluate_gate(self._state.clone(),gate_id,self.now())
    def effective_gate(self,evaluation):
        with self._lock:
            return self.gates.effective(self._state.clone(),evaluation)
    def derive_blockers(self,*,gate_id:str|None=None,action_id:str|None=None):
        with self._lock:
            return [b.to_dict() for b in self.gates.derive_blockers(self._state.clone(),gate_id=gate_id,action_id=action_id)]
    def next_legal_action(self,*,actor_type:str='SYSTEM'):
        with self._lock:
            return self.gates.next_legal_action(self._state.clone(),self.now(),actor_type=actor_type)
    def gate_history(self):
        with self._lock:
            return [deepcopy(x) for x in self._state.gate_evaluations]
    def begin(self,*,expected_manifest_version:int|None=None,expected_registry_versions:dict[str,int]|None=None,recovery:bool=False):
        from .transaction import StateTransaction
        with self._lock:
            if self._state.dependency_integrity_issues:
                raise StateEngineError('DEPENDENCY_INTEGRITY_READ_ONLY','State Engine is READ_ONLY because cold-start dependency projection integrity failed.',details=list(self._state.dependency_integrity_issues))
            if self._state.safety_mode!='NORMAL' and not recovery:
                raise StateEngineError('INCIDENT_SAFETY_MODE_ACTIVE',f'State Engine mutation is blocked by incident safety mode {self._state.safety_mode}.',details=derive_safety_decision(self._state,self.root).to_dict())
            if expected_manifest_version is not None and expected_manifest_version!=self._state.manifest_version:
                raise ConcurrencyConflict('MANIFEST_VERSION_CONFLICT',f'Expected manifest version {expected_manifest_version}, current is {self._state.manifest_version}.')
            for rid,expected in (expected_registry_versions or {}).items():
                if rid==ARTIFACT_REGISTRY_ID:actual=self._state.artifact_registry.version
                else:actual=self._state.registries[rid].version if rid in self._state.registries else 0
                if int(expected)!=actual: raise ConcurrencyConflict('REGISTRY_VERSION_CONFLICT',f'Expected {rid} version {expected}, current is {actual}.')
            return StateTransaction(self,self._state.clone())
    def _validate_staged(self,staged:RuntimeState,changed_keys:set[tuple[str,int]],changed_artifact_keys:set[tuple[str,int]]|None=None):
        structural=[]
        for key in sorted(changed_keys):structural.extend(self.structural.validate_object(staged.objects[key]))
        for key in sorted(changed_artifact_keys or set()):structural.extend(self.structural.validate_artifact(staged.artifacts[key]))
        if structural:raise ValidationFailure(structural)
        dep_issues=self.dependency.projection_issues(staged.objects.values())
        if dep_issues:
            raise ValidationFailure([StateEngineIssue('DEPENDENCY_PROJECTION_MISMATCH',x['target'],target=x['target']) for x in dep_issues])
        view=StateView.build(staged.objects.values(),staged.artifacts.values(),staged.configs.values())
        semantic=[x for x in self.semantic.validate_state(view) if x.severity.upper() not in {'INFO','WARNING','WARN'}]
        if semantic:raise ValidationFailure(semantic)
    def _publish(self,tx)->int:
        with self._lock:
            current=self._state
            if current.manifest_version!=tx.base_manifest_version:raise ConcurrencyConflict('MANIFEST_VERSION_CONFLICT',f'Transaction began at manifest {tx.base_manifest_version}; current is {current.manifest_version}.')
            for rid in tx.dirty_registries:
                before=tx.base_registry_versions.get(rid,0); actual=current.registries[rid].version if rid in current.registries else 0
                if actual!=before:raise ConcurrencyConflict('REGISTRY_VERSION_CONFLICT',f'Transaction began with {rid}@{before}; current is {actual}.')
            if tx.dirty_artifact_registry and current.artifact_registry.version!=tx.base_artifact_registry_version:
                raise ConcurrencyConflict('REGISTRY_VERSION_CONFLICT',f'Transaction began with {ARTIFACT_REGISTRY_ID}@{tx.base_artifact_registry_version}; current is {current.artifact_registry.version}.')
            if not tx.actions:raise StateEngineError('EMPTY_TRANSACTION','Cannot commit a transaction with no actions.')
            staged=tx.staged
            for rid in tx.dirty_registries:staged.registries[rid].version=tx.base_registry_versions.get(rid,0)+1
            if tx.dirty_artifact_registry:staged.artifact_registry.version=tx.base_artifact_registry_version+1
            # Gate decisions are re-evaluated against the final staged transaction state.
            # This prevents an earlier gate PASS in the same transaction from authorizing
            # a transition after later staged mutations invalidate its evidence.
            for chk in getattr(tx,'transition_checks',[]):
                decision=self.gates.evaluate_transition(staged,chk['from'],chk['to'],self.now(),actor_type=chk['actor_type'],human_confirmed=chk['human_confirmed'])
                if not decision.allowed:
                    raise StateEngineError('PROJECT_STATE_TRANSITION_REVALIDATION_FAILED',f"Transition {chk['from']} -> {chk['to']} became ineligible before commit.",details=decision.to_dict())
            self._validate_staged(staged,tx.changed_keys,getattr(tx,'changed_artifact_keys',set()))
            before_manifest=current.manifest_version; before_regs={rid:(current.registries[rid].version if rid in current.registries else 0) for rid in tx.dirty_registries}
            if tx.dirty_artifact_registry:before_regs[ARTIFACT_REGISTRY_ID]=current.artifact_registry.version
            staged.manifest_version=before_manifest+1; after_regs={rid:staged.registries[rid].version for rid in tx.dirty_registries}
            if tx.dirty_artifact_registry:after_regs[ARTIFACT_REGISTRY_ID]=staged.artifact_registry.version
            audit=TransactionAudit(tx.transaction_id,self.now(),before_manifest,staged.manifest_version,before_regs,after_regs,tuple(tx.actions))
            staged.audit_log=tuple(current.audit_log)+(audit,)
            if staged.dependency_integrity_issues:
                staged.safety_mode='READ_ONLY'
            else:
                staged.safety_mode=derive_safety_decision(staged,self.root).mode
            self._state=staged.clone(); return self._state.manifest_version
