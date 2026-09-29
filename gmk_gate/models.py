from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
from copy import deepcopy

@dataclass(frozen=True)
class GateRequirementResult:
    requirement_id: str
    result: str
    code: str
    message: str
    evidence: tuple[dict[str,Any], ...] = ()
    warning_codes: tuple[str, ...] = ()
    non_overridable: bool = False
    def to_dict(self):
        return {
            'requirement_id': self.requirement_id,
            'result': self.result,
            'code': self.code,
            'message': self.message,
            'evidence': [deepcopy(x) for x in self.evidence],
            'warning_codes': list(self.warning_codes),
            'non_overridable': self.non_overridable,
        }

@dataclass(frozen=True)
class GateEvaluation:
    evaluation_id: str
    gate_id: str
    result: str
    evaluated_at: str
    policy_ref: dict[str,Any]
    requirement_results: tuple[GateRequirementResult,...] = ()
    evidence: tuple[dict[str,Any], ...] = ()
    warning_codes: tuple[str,...] = ()
    blocker_refs: tuple[str,...] = ()
    def to_dict(self):
        return {
            'evaluation_id': self.evaluation_id,
            'gate_id': self.gate_id,
            'result': self.result,
            'evaluated_at': self.evaluated_at,
            'policy_ref': deepcopy(self.policy_ref),
            'requirement_results': [x.to_dict() for x in self.requirement_results],
            'evidence': [deepcopy(x) for x in self.evidence],
            'warning_codes': list(self.warning_codes),
            'blocker_refs': list(self.blocker_refs),
        }

@dataclass(frozen=True)
class EffectiveGateResult:
    evaluation: GateEvaluation
    validity: str = 'VALID'
    invalidation_reasons: tuple[str,...] = ()
    def to_dict(self):
        out=self.evaluation.to_dict()
        out['validity']=self.validity
        out['invalidation_reasons']=list(self.invalidation_reasons)
        return out

@dataclass(frozen=True)
class DerivedBlocker:
    blocker_id: str
    code: str
    severity: str
    message: str
    gate_ids: tuple[str,...] = ()
    action_ids: tuple[str,...] = ()
    target: dict[str,Any] | None = None
    source_ref: dict[str,Any] | None = None
    non_overridable: bool = False
    def to_dict(self):
        out={
            'blocker_id':self.blocker_id,'code':self.code,'severity':self.severity,'message':self.message,
            'gate_ids':list(self.gate_ids),'action_ids':list(self.action_ids),'non_overridable':self.non_overridable,
        }
        if self.target is not None: out['target']=deepcopy(self.target)
        if self.source_ref is not None: out['source_ref']=deepcopy(self.source_ref)
        return out

@dataclass(frozen=True)
class TransitionDecision:
    from_state: str
    to_state: str
    allowed: bool
    permission_class: str
    gate_results: tuple[EffectiveGateResult,...] = ()
    blockers: tuple[DerivedBlocker,...] = ()
    predicate_failures: tuple[str,...] = ()
    warning_requires_acceptance: bool = False
    reason_codes: tuple[str,...] = ()
    def to_dict(self):
        return {
            'from_state':self.from_state,'to_state':self.to_state,'allowed':self.allowed,
            'permission_class':self.permission_class,
            'gate_results':[x.to_dict() for x in self.gate_results],
            'blockers':[x.to_dict() for x in self.blockers],
            'predicate_failures':list(self.predicate_failures),
            'warning_requires_acceptance':self.warning_requires_acceptance,
            'reason_codes':list(self.reason_codes),
        }

@dataclass(frozen=True)
class NextLegalAction:
    action: str
    project_state: str
    target_state: str | None = None
    gate_ids: tuple[str,...] = ()
    permission_class: str | None = None
    blockers: tuple[str,...] = ()
    missing_requirements: tuple[str,...] = ()
    message: str = ''
    def to_dict(self): return asdict(self)
