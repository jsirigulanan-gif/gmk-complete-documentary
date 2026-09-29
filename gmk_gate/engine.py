from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
import hashlib, json

from gmk_dependency import NodeKey, NodeKind
from gmk_semantics.model import sha256_json
from .policy import GatePolicy
from .models import GateRequirementResult,GateEvaluation,EffectiveGateResult,DerivedBlocker,TransitionDecision,NextLegalAction


def _get(doc:Any,path:str,default=None):
    if path in {'','/'}: return doc
    cur=doc
    for raw in path.strip('/').split('/'):
        key=raw.replace('~1','/').replace('~0','~')
        if isinstance(cur,dict):
            if key not in cur:return default
            cur=cur[key]
        elif isinstance(cur,list):
            try:cur=cur[int(key)]
            except (ValueError,IndexError):return default
        else:return default
    return cur

def _match_predicate(record:dict[str,Any],pred:dict[str,Any])->bool:
    val=_get(record,pred.get('path','/'),None)
    if 'exists' in pred:
        exists=val is not None
        if exists != bool(pred['exists']): return False
    if 'equals' in pred and val!=pred['equals']: return False
    if 'in' in pred and val not in pred['in']: return False
    if 'not_in' in pred and val in pred['not_in']: return False
    if 'contains' in pred:
        try:
            if pred['contains'] not in val:return False
        except TypeError:return False
    return True

def _object_ref(o): return {'id':o['id'],'version':int(o['version'])}
def _artifact_ref(a): return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}

def _severity_rank(s:str)->int:return {'INFO':0,'MINOR':1,'MAJOR':2,'CRITICAL':3}.get(str(s).upper(),0)

class GateEngine:
    """Pinned-policy Gate Engine for frozen GMK Schema v1.

    It evaluates current exact evidence only. Historical GateEvaluation snapshots are
    immutable; effective validity is recomputed against current dependency/stale state.
    """
    def __init__(self,root:Path):
        self.root=Path(root); self.policy=GatePolicy(self.root); self._counter=0

    def _active_objects(self,state,object_type:str|None=None)->list[dict[str,Any]]:
        out=[]
        for reg in state.registries.values():
            for e in reg.entries.values():
                if e.active_version is None:continue
                obj=state.objects.get((e.object_id,int(e.active_version)))
                if obj and (object_type is None or obj.get('object_type')==object_type):out.append(obj)
        return sorted(out,key=lambda o:(o.get('object_type',''),o['id']))

    def _artifact_heads(self,state,artifact_type:str|None=None)->list[dict[str,Any]]:
        by_id={}
        for (aid,v),a in state.artifacts.items():
            if artifact_type and a.get('artifact_type')!=artifact_type:continue
            if aid not in by_id or int(v)>int(by_id[aid]['version']):by_id[aid]=a
        return sorted(by_id.values(),key=lambda a:a['artifact_id'])

    def _fresh_object(self,state,obj:dict[str,Any])->tuple[bool,str|None]:
        if obj.get('status') in {'STALE','BLOCKED','ARCHIVED','REJECTED'}:return False,f"OBJECT_STATUS_{obj.get('status')}"
        if (obj.get('stale') or {}).get('is_stale'):return False,'OBJECT_STALE'
        key=NodeKey(NodeKind.OBJECT,obj['id'],int(obj['version']))
        if key in getattr(state,'dependency_invalidations',{}):return False,'DEPENDENCY_INVALIDATED'
        return True,None

    def _fresh_artifact(self,state,a:dict[str,Any])->tuple[bool,str|None]:
        key=NodeKey(NodeKind.ARTIFACT,a['artifact_id'],int(a['version']))
        if key in getattr(state,'dependency_invalidations',{}):return False,'DEPENDENCY_INVALIDATED'
        return True,None

    def _fresh_target(self,state,ref:dict[str,Any])->tuple[bool,str|None]:
        if 'artifact_id' in ref:
            a=state.artifacts.get((ref['artifact_id'],int(ref['version'])))
            if not a:return False,'ARTIFACT_MISSING'
            if ref.get('sha256') and a.get('sha256')!=ref.get('sha256'):return False,'ARTIFACT_HASH_MISMATCH'
            head=max((v for (aid,v) in state.artifacts if aid==ref['artifact_id']),default=int(ref['version']))
            if int(head)!=int(ref['version']):return False,'ARTIFACT_NOT_CURRENT_HEAD'
            return self._fresh_artifact(state,a)
        o=state.objects.get((ref.get('id'),int(ref.get('version',0))))
        if not o:return False,'OBJECT_MISSING'
        from gmk_state.registry import global_index
        rid=global_index(state.registries).get(o['id'])
        if rid:
            av=state.registries[rid].entries[o['id']].active_version
            if av is None or int(av)!=int(o['version']):return False,'OBJECT_NOT_ACTIVE'
        return self._fresh_object(state,o)

    def _approvals_for(self,state,target:dict[str,Any],approval_class:str)->list[dict[str,Any]]:
        out=[]
        for a in self._active_objects(state,'APPROVAL'):
            if a.get('approval_class')!=approval_class or a.get('decision')!='APPROVED':continue
            if a.get('target')!=target:continue
            fresh,_=self._fresh_object(state,a)
            if not fresh:continue
            if 'id' in target and a.get('target_decision_sha256'):
                obj=state.objects.get((target['id'],int(target['version'])))
                if not obj:continue
                # decision hash is stamped by semantic layer; import lazily to avoid cycle
                from gmk_semantics.model import decision_projection
                if sha256_json(decision_projection(obj))!=a.get('target_decision_sha256'):continue
            rc=a.get('review_context')
            if rc:
                ok,_=self._fresh_target(state,rc)
                if not ok:continue
            out.append(a)
        return out

    def _qa_reports(self,state,report_type:str)->list[dict[str,Any]]:
        return [q for q in self._active_objects(state,'QA_REPORT') if q.get('report_type')==report_type and self._fresh_object(state,q)[0]]

    def _requirement(self,state,gate_id:str,r:dict[str,Any])->GateRequirementResult:
        rid=r['id']; kind=r['kind']; on_fail=r.get('on_fail','FAIL'); non_over=bool(r.get('non_overridable',False)); ev=[]
        result='PASS'; code='OK'; msg=f'{rid} satisfied.'; warnings=[]
        def fail(code_,msg_):
            nonlocal result,code,msg
            result=on_fail; code=code_; msg=msg_
            if result=='WARN': warnings.append(code_)
        if kind=='ARTIFACT_TYPE_EXISTS':
            arts=self._artifact_heads(state,r['artifact_type'])
            fresh=[a for a in arts if self._fresh_artifact(state,a)[0]]
            if len(fresh)<int(r.get('min_count',1)):fail('ARTIFACT_EVIDENCE_MISSING',f"Gate {gate_id} requires current {r['artifact_type']} artifact evidence.")
            else:ev=[_artifact_ref(a) for a in fresh]
        elif kind=='ACTIVE_OBJECT_TYPE_EXISTS':
            objs=self._active_objects(state,r['object_type']); fresh=[o for o in objs if self._fresh_object(state,o)[0]]
            if len(fresh)<int(r.get('min_count',1)):fail('ACTIVE_OBJECT_EVIDENCE_MISSING',f"Gate {gate_id} requires at least {r.get('min_count',1)} current ACTIVE {r['object_type']} object(s).")
            else:ev=[_object_ref(o) for o in fresh]
        elif kind=='ACTIVE_OBJECTS_MATCH':
            objs=self._active_objects(state,r['object_type']); fresh=[o for o in objs if self._fresh_object(state,o)[0]]
            if len(fresh)<int(r.get('min_count',1)):fail('ACTIVE_OBJECT_EVIDENCE_MISSING',f"Gate {gate_id} requires current ACTIVE {r['object_type']} evidence.")
            elif not all(all(_match_predicate(o,p) for p in r.get('predicates',[])) for o in fresh):fail('ACTIVE_OBJECT_PREDICATE_FAILED',f"One or more ACTIVE {r['object_type']} objects do not satisfy {rid}.")
            else:ev=[_object_ref(o) for o in fresh]
        elif kind=='NO_ACTIVE_OBJECT_MATCH':
            bad=[]
            for o in self._active_objects(state,r['object_type']):
                if not self._fresh_object(state,o)[0]:continue
                if all(_match_predicate(o,p) for p in r.get('predicates',[])):bad.append(o)
            if bad:fail(r.get('code','BLOCKING_OBJECT_PRESENT'),f"Gate {gate_id} has {len(bad)} blocking {r['object_type']} object(s).")
            ev=[_object_ref(o) for o in bad]
        elif kind=='ARTIFACT_COVERAGE_FOR_ACTIVE_TYPE':
            objs=[o for o in self._active_objects(state,r['object_type']) if self._fresh_object(state,o)[0]]
            arts=[a for a in self._artifact_heads(state,r['artifact_type']) if self._fresh_artifact(state,a)[0]]
            uncovered=[]
            for o in objs:
                wanted=_object_ref(o); ok=False
                for a in arts:
                    if _get(a,r['ref_path'])==wanted:ok=True; ev.append(_artifact_ref(a)); break
                if not ok:uncovered.append(wanted)
            if not objs and r.get('require_objects',True):fail('COVERAGE_SOURCE_EMPTY',f"No ACTIVE {r['object_type']} objects exist for coverage check.")
            elif uncovered:fail('ARTIFACT_COVERAGE_INCOMPLETE',f"{r['artifact_type']} coverage is missing for {len(uncovered)} ACTIVE {r['object_type']} object(s).")
        elif kind=='QA_REPORT_RESULT':
            qs=self._qa_reports(state,r['report_type'])
            if not qs:fail('QA_REPORT_MISSING',f"Gate {gate_id} requires current QA report type {r['report_type']}.")
            else:
                # QA reports are immutable historical snapshots. Gates must evaluate the
                # latest current retest per scope, not poison the project forever with an
                # older FAIL/WARN after a newer verification report has superseded it.
                def latest_report(items):
                    return max(items,key=lambda q:(str(q.get('evaluated_at') or ''),str(q.get('updated_at') or q.get('created_at') or ''),str(q.get('id') or '')))
                cover=r.get('cover_active_type'); selected=[]
                if cover:
                    targets=[o for o in self._active_objects(state,cover) if self._fresh_object(state,o)[0]]
                    missing=[]
                    for o in targets:
                        tref=_object_ref(o); matches=[q for q in qs if q.get('scope')==tref]
                        if not matches:missing.append(tref);continue
                        selected.append(latest_report(matches))
                    if not targets:fail('QA_COVERAGE_SOURCE_EMPTY',f"No ACTIVE {cover} objects exist for QA coverage.")
                    elif missing:fail('QA_COVERAGE_INCOMPLETE',f"{r['report_type']} is missing for {len(missing)} ACTIVE {cover} object(s).")
                else:
                    selected=[latest_report(qs)]
                if result=='PASS':
                    bad=[q for q in selected if q.get('result')=='FAIL']; warn=[q for q in selected if q.get('result')=='WARN']
                    if bad:fail('QA_REPORT_FAIL',f"{len(bad)} latest {r['report_type']} report(s) are FAIL.")
                    elif warn:
                        result='WARN'; code='QA_REPORT_WARN'; msg=f"{len(warn)} latest {r['report_type']} report(s) are WARN."; warnings.append('QA_REPORT_WARN')
                    ev=[_object_ref(q) for q in selected]
        elif kind=='APPROVAL_COVERAGE':
            cls=r['approval_class']; targets=[]
            if r.get('target_object_type'):
                targets=[_object_ref(o) for o in self._active_objects(state,r['target_object_type']) if self._fresh_object(state,o)[0]]
            elif r.get('target_artifact_type'):
                targets=[_artifact_ref(a) for a in self._artifact_heads(state,r['target_artifact_type']) if self._fresh_artifact(state,a)[0]]
            missing=[t for t in targets if not self._approvals_for(state,t,cls)]
            if not targets:fail('APPROVAL_TARGET_MISSING',f"No current targets exist for required {cls} approval.")
            elif missing:fail('APPROVAL_COVERAGE_INCOMPLETE',f"{len(missing)} current target(s) lack exact {cls} approval.")
            else:ev=targets
        elif kind=='RENDER_SUCCESS':
            rms=[o for o in self._active_objects(state,'RENDER_MANIFEST') if self._fresh_object(state,o)[0]]
            good=[o for o in rms if o.get('outcome')=='SUCCESS' and _get(o,'/technical_validation/state')=='PASS']
            if len(good)<int(r.get('min_count',1)):fail('RENDER_SUCCESS_MISSING','No current successful technically-valid Render Manifest satisfies the Render gate.')
            else:ev=[_object_ref(o) for o in good]
        elif kind=='PROJECT_COMPLETION_READY':
            releases=[o for o in self._active_objects(state,'RELEASE') if self._fresh_object(state,o)[0] and o.get('state')=='RELEASED']
            cps=[o for o in self._active_objects(state,'CHECKPOINT') if self._fresh_object(state,o)[0] and o.get('checkpoint_class')=='FINAL_PROJECT' and o.get('integrity_summary')=='PASS']
            if not releases:fail('CURRENT_RELEASE_MISSING','Project completion requires a current RELEASED Release.')
            elif not cps:fail('FINAL_PROJECT_CHECKPOINT_MISSING','Project completion requires a valid FINAL_PROJECT Checkpoint.')
            else:ev=[_object_ref(releases[-1]),_object_ref(cps[-1])]
        else:fail('UNKNOWN_GATE_REQUIREMENT',f'Unknown gate requirement kind {kind}.')
        return GateRequirementResult(rid,result,code,msg,tuple(ev),tuple(warnings),non_over)

    def derive_blockers(self,state,*,gate_id:str|None=None,action_id:str|None=None)->list[DerivedBlocker]:
        out=[]
        def add(code,severity,message,*,gates=(),actions=(),target=None,source=None,non_over=False):
            seed=json.dumps([code,severity,message,gates,actions,target,source],sort_keys=True,default=str).encode(); bid='BLK_'+hashlib.sha256(seed).hexdigest()[:12].upper()
            b=DerivedBlocker(bid,code,severity,message,tuple(gates),tuple(actions),deepcopy(target),deepcopy(source),non_over)
            if gate_id:
                if b.action_ids and not b.gate_ids:return
                if b.gate_ids and gate_id not in b.gate_ids:return
            if action_id:
                if b.gate_ids and not b.action_ids:return
                if b.action_ids and action_id not in b.action_ids:return
            out.append(b)
        # Research gaps explicitly scope themselves to gates.
        for gap in self._active_objects(state,'RESEARCH_GAP'):
            # An unresolved scoped gap remains a blocker even if its exact
            # dependency refs have gone stale. Staleness means the blocker itself
            # needs revision; it must never make a critical unknown disappear.
            gs=tuple(gap.get('blocked_gates') or [])
            if gs and gap.get('state') not in {'RESOLVED','REMOVED_FROM_SCOPE'}:
                sev='CRITICAL' if gap.get('importance')=='CRITICAL' else 'MAJOR'
                add('RESEARCH_GAP_BLOCKS_GATE',sev,gap.get('question','Research gap blocks gate.'),gates=gs,target=_object_ref(gap),source=_object_ref(gap),non_over=gap.get('importance')=='CRITICAL')
        # Policy-scoped object blockers.
        for rule in self.policy.blocker_rules:
            typ=rule.get('object_type');
            for obj in self._active_objects(state,typ):
                if not self._fresh_object(state,obj)[0] and typ not in {'INCIDENT','QA_ISSUE'}:continue
                if not all(_match_predicate(obj,p) for p in rule.get('predicates',[])):continue
                sev=str(obj.get(rule.get('severity_field','severity'),rule.get('severity','MAJOR')))
                if _severity_rank(sev)<_severity_rank(rule.get('min_severity','INFO')):continue
                add(rule['code'],sev,rule.get('message',rule['code']),gates=tuple(rule.get('gate_ids',[])),actions=tuple(rule.get('action_ids',[])),target=_object_ref(obj),source=_object_ref(obj),non_over=bool(rule.get('non_overridable',False)))
        # Safety mode is an execution boundary, not a historical gate result.
        if getattr(state,'safety_mode','NORMAL')!='NORMAL':
            add('SAFETY_MODE_BLOCK', 'CRITICAL', f"Runtime safety mode is {state.safety_mode}.", actions=('TRANSITION_PROJECT_STATE','REENTER_STAGE'), non_over=True)
        # Deduplicate deterministic IDs.
        return sorted({b.blocker_id:b for b in out}.values(),key=lambda b:b.blocker_id)

    def evaluate_gate(self,state,gate_id:str,now:str)->GateEvaluation:
        definition=self.policy.gate(gate_id)
        rr=tuple(self._requirement(state,gate_id,r) for r in definition.get('requirements',[]))
        blockers=tuple(self.derive_blockers(state,gate_id=gate_id))
        result='PASS'
        if any(x.result=='FAIL' for x in rr) or blockers:result='FAIL'
        elif any(x.result=='WARN' for x in rr):result='WARN'
        evidence=[]; warnings=[]
        for x in rr:
            evidence.extend(x.evidence);warnings.extend(x.warning_codes)
        # exact de-dup preserving order
        seen=set(); ev=[]
        for e in evidence:
            sig=json.dumps(e,sort_keys=True)
            if sig not in seen:seen.add(sig);ev.append(e)
        self._counter+=1
        eid=f'GE_{self._counter:06d}'
        return GateEvaluation(eid,gate_id,result,now,self.policy.ref,rr,tuple(ev),tuple(dict.fromkeys(warnings)),tuple(b.blocker_id for b in blockers))

    def effective(self,state,e:GateEvaluation)->EffectiveGateResult:
        reasons=[]
        for ref in e.evidence:
            ok,why=self._fresh_target(state,ref)
            if not ok: reasons.append(f"{why}:{ref}")
        # New blockers for the same gate invalidate prior PASS/WARN as current evidence.
        current_blockers=self.derive_blockers(state,gate_id=e.gate_id)
        if current_blockers and not e.blocker_refs:reasons.append('NEW_BLOCKER_PRESENT')
        return EffectiveGateResult(e,'INVALIDATED' if reasons else 'VALID',tuple(reasons))

    def _warning_accepted(self,state,e:GateEvaluation)->bool:
        # WARN may be accepted only by exact EXCEPTION approval on a warning evidence target.
        if e.result!='WARN':return True
        for ref in e.evidence:
            if self._approvals_for(state,ref,'EXCEPTION'):return True
        return False

    def evaluate_transition(self,state,fr:str,to:str,now:str,*,actor_type:str='SYSTEM',human_confirmed:bool=False)->TransitionDecision:
        td=self.policy.transition(fr,to)
        if not td:return TransitionDecision(fr,to,False,'FORBIDDEN',reason_codes=('TRANSITION_NOT_DEFINED',))
        perm=td.get('permission','FORBIDDEN'); reasons=[]; pred=[]
        if perm=='FORBIDDEN':reasons.append('TRANSITION_FORBIDDEN')
        elif perm=='HUMAN_ONLY' and actor_type!='HUMAN':reasons.append('HUMAN_ONLY_TRANSITION')
        elif perm=='HUMAN_APPROVAL_REQUIRED' and not (actor_type=='HUMAN' or human_confirmed):reasons.append('HUMAN_CONFIRMATION_REQUIRED')
        elif perm=='AI_WITH_RULES' and actor_type not in {'AI','HUMAN','SYSTEM'}:reasons.append('ACTOR_NOT_AUTHORIZED')
        gates=[];warn_need=False
        for gid in td.get('gates',[]):
            ge=self.evaluate_gate(state,gid,now); eff=self.effective(state,ge);gates.append(eff)
            if eff.validity!='VALID':reasons.append('GATE_INVALIDATED')
            if ge.result=='FAIL':reasons.append(f'GATE_FAIL:{gid}')
            if ge.result=='WARN':
                wp=td.get('warn_policy','REQUIRE_EXCEPTION')
                accepted=(wp=='ALLOW') or self._warning_accepted(state,ge)
                if not accepted:warn_need=True;reasons.append(f'GATE_WARN_UNACCEPTED:{gid}')
        blockers=self.derive_blockers(state,action_id='TRANSITION_PROJECT_STATE')
        blockers += [b for gid in td.get('gates',[]) for b in self.derive_blockers(state,gate_id=gid)]
        # transition predicates are intentionally small and explicit.
        for p in td.get('predicates',[]):
            if p=='SAFETY_NORMAL' and getattr(state,'safety_mode','NORMAL')!='NORMAL':pred.append('SAFETY_NORMAL_REQUIRED')
            elif p=='NO_BLOCKERS':
                if blockers:pred.append('BLOCKERS_PRESENT')
            elif p=='PROJECT_COMPLETION_READY':
                rr=self._requirement(state,'PROJECT_COMPLETION',{'id':'PROJECT_COMPLETION_READY','kind':'PROJECT_COMPLETION_READY','on_fail':'FAIL','non_overridable':True})
                if rr.result!='PASS':pred.append(rr.code)
        # deterministic dedup
        bmap={b.blocker_id:b for b in blockers}; blockers=tuple(sorted(bmap.values(),key=lambda b:b.blocker_id))
        allowed=not reasons and not pred and not blockers and not warn_need
        return TransitionDecision(fr,to,allowed,perm,tuple(gates),blockers,tuple(pred),warn_need,tuple(dict.fromkeys(reasons)))

    def next_legal_action(self,state,now:str,*,actor_type:str='SYSTEM')->NextLegalAction:
        fr=state.project_state
        candidates=[td for (a,_),td in self.policy.transitions.items() if a==fr]
        if not candidates:return NextLegalAction('NO_LEGAL_TRANSITION',fr,message='No forward transition is defined from the current Project State.')
        # Forward config is expected to have one normal transition; keep deterministic if more.
        td=sorted(candidates,key=lambda x:x['to'])[0]; to=td['to']; decision=self.evaluate_transition(state,fr,to,now,actor_type=actor_type)
        if decision.allowed:
            return NextLegalAction('TRANSITION_PROJECT_STATE',fr,to,tuple(td.get('gates',[])),decision.permission_class,message=f'{fr} can transition to {to}.')
        if decision.blockers:
            return NextLegalAction('RESOLVE_BLOCKER',fr,to,tuple(td.get('gates',[])),decision.permission_class,tuple(b.blocker_id for b in decision.blockers),message='Resolve scoped blockers before transition.')
        missing=list(decision.predicate_failures)
        for g in decision.gate_results:
            if g.evaluation.result!='PASS' or g.validity!='VALID':
                for r in g.evaluation.requirement_results:
                    if r.result!='PASS':missing.append(f'{g.evaluation.gate_id}:{r.requirement_id}:{r.code}')
        if decision.warning_requires_acceptance:return NextLegalAction('ACCEPT_WARNING_OR_REPAIR',fr,to,tuple(td.get('gates',[])),decision.permission_class,missing_requirements=tuple(missing),message='A WARN gate requires accepted exception or repair according to policy.')
        if any(x in decision.reason_codes for x in ('HUMAN_CONFIRMATION_REQUIRED','HUMAN_ONLY_TRANSITION')):
            return NextLegalAction('REQUEST_HUMAN_AUTHORIZATION',fr,to,tuple(td.get('gates',[])),decision.permission_class,message='Human authority is required for this transition.')
        return NextLegalAction('SATISFY_GATE_REQUIREMENTS',fr,to,tuple(td.get('gates',[])),decision.permission_class,missing_requirements=tuple(missing),message='Current exact evidence does not yet satisfy the next transition.')
