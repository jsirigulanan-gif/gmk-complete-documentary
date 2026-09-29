from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib, json
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore

class DesignRuntimeError(RuntimeError): pass

def _aref(a): return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}
def _oref(o): return {'id':o['id'],'version':int(o['version'])}
def _heads(s,t): return [s.artifacts[(aid,int(e.head_version))] for aid,e in s.artifact_registry.entries.items() if e.artifact_type==t]
def _active(s,t):
    out=[]
    for reg in s.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type==t and e.active_version is not None: out.append(s.objects[(oid,int(e.active_version))])
    return sorted(out,key=lambda x:x['id'])
def _same_aref(a,b):
    return bool(a and b) and a.get('artifact_id')==b.get('artifact_id') and int(a.get('version',0))==int(b.get('version',0)) and a.get('sha256')==b.get('sha256')

def _base_design(root:Path):
    p=root/'config'/'design_policies.yaml'; digest=hashlib.sha256(p.read_bytes()).hexdigest()
    return {'config_id':'GMK_DESIGN_POLICY','version':'1.0.0','sha256':digest}

@dataclass(frozen=True)
class DesignPrepareResult:
    workspace:Path; project_state:str; design_dna_ref:dict; effective_tokens_ref:dict; rule_count:int; gate_result:str
    def to_dict(self): return {'workspace':str(self.workspace),'project_state':self.project_state,'design_dna_ref':self.design_dna_ref,'effective_tokens_ref':self.effective_tokens_ref,'rule_count':self.rule_count,'gate_result':self.gate_result}
@dataclass(frozen=True)
class DesignReviewResult:
    workspace:Path; project_state:str; review_package_ref:dict; design_dna_ref:dict; gate_result:str
    def to_dict(self): return {'workspace':str(self.workspace),'project_state':self.project_state,'review_package_ref':self.review_package_ref,'design_dna_ref':self.design_dna_ref,'gate_result':self.gate_result}
@dataclass(frozen=True)
class DesignDecisionResult:
    workspace:Path; project_state:str; decision:str; approval_ref:dict; review_package_ref:dict; design_dna_ref:dict; gate_result:str
    def to_dict(self): return {'workspace':str(self.workspace),'project_state':self.project_state,'decision':self.decision,'approval_ref':self.approval_ref,'review_package_ref':self.review_package_ref,'design_dna_ref':self.design_dna_ref,'gate_result':self.gate_result}

class DesignRuntime:
    def __init__(self,root:Path,workspace:Path): self.root=Path(root); self.workspace=Path(workspace)
    def prepare(self,plan:dict)->DesignPrepareResult:
        loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; s=eng.snapshot()
        if eng.project_state not in {'VOICE_LOCKED','DESIGN_DNA_APPROVED'}: raise DesignRuntimeError(f'DESIGN_STATE_INVALID: expected VOICE_LOCKED/DESIGN_DNA_APPROVED, found {eng.project_state}')
        existing=_active(s,'DESIGN_DNA')
        if existing:
            dna=existing[0]; toks=_heads(s,'EFFECTIVE_DESIGN_TOKENS')
            if len(toks)!=1: raise DesignRuntimeError('DESIGN_TOKENS_CARDINALITY_INVALID')
            return DesignPrepareResult(self.workspace,eng.project_state,_oref(dna),_aref(toks[0]),len(dna.get('rules') or []),eng.gates.evaluate_gate(s,'DESIGN_DNA',eng.now()).result)
        projects=_active(s,'PROJECT'); voices=_heads(s,'VOICE_LOCK_MANIFEST'); spines=_heads(s,'NARRATIVE_SPINE')
        if not(len(projects)==len(voices)==len(spines)==1): raise DesignRuntimeError('DESIGN_DEPENDENCY_CARDINALITY_INVALID')
        intent=plan.get('design_intent') or {}; rules=plan.get('rules') or []
        for k in ('visual_thesis','audience_feeling','clarity_principle'):
            if not str(intent.get(k) or '').strip(): raise DesignRuntimeError(f'DESIGN_INTENT_REQUIRED: {k}')
        if not rules: raise DesignRuntimeError('DESIGN_RULES_REQUIRED')
        normalized=[]
        refs=[_aref(voices[0]),_aref(spines[0])]
        for i,r in enumerate(rules,1):
            if not all(str(r.get(k) or '').strip() for k in ('domain','action','statement','rationale')): raise DesignRuntimeError(f'DESIGN_RULE_INVALID: {i}')
            normalized.append({'rule_id':str(r.get('rule_id') or f'DNR_{i:03d}').upper(),'domain':str(r['domain']).upper(),'action':str(r['action']).upper(),'statement':str(r['statement']).strip(),'rationale':str(r['rationale']).strip(),'reference_refs':refs})
        gp=plan.get('graphic_policy') or {'default_decision':'OPTIONAL'}
        payload={'project_ref':_oref(projects[0]),'base_design':_base_design(self.root),'design_intent':intent,'rules':normalized,'references':refs,'token_overrides':plan.get('token_overrides') or {},'graphic_policy':gp}
        for key in ('evidence_policy','motion_policy','transition_policy','three_d_policy'):
            if key in plan: payload[key]=plan[key]
        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        dr=tx.create_object('DESIGN_DNA',payload)
        tr=tx.create_artifact('EFFECTIVE_DESIGN_TOKENS',{'base_design':payload['base_design'],'design_dna_ref':dr,'tokens':plan.get('effective_tokens') or plan.get('token_overrides') or {}},origin_refs=refs)
        tx.commit(); RuntimeStore(self.root,self.workspace).persist(eng)
        fs=eng.snapshot(); dna=fs.objects[(dr['id'],int(dr['version']))]; tok=fs.artifacts[(tr['artifact_id'],int(tr['version']))]
        gate=eng.gates.evaluate_gate(fs,'DESIGN_DNA',eng.now()).result
        if gate!='FAIL': raise DesignRuntimeError('DESIGN_GATE_SHOULD_REQUIRE_HUMAN_APPROVAL')
        return DesignPrepareResult(self.workspace,eng.project_state,_oref(dna),_aref(tok),len(normalized),gate)

    def review_package(self)->DesignReviewResult:
        loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; s=eng.snapshot()
        if eng.project_state not in {'VOICE_LOCKED','DESIGN_DNA_APPROVED'}: raise DesignRuntimeError(f'DESIGN_REVIEW_STATE_INVALID: {eng.project_state}')
        dnas=_active(s,'DESIGN_DNA'); toks=_heads(s,'EFFECTIVE_DESIGN_TOKENS'); voices=_heads(s,'VOICE_LOCK_MANIFEST'); spines=_heads(s,'NARRATIVE_SPINE')
        if not(len(dnas)==len(toks)==len(voices)==len(spines)==1): raise DesignRuntimeError('DESIGN_REVIEW_DEPENDENCY_CARDINALITY_INVALID')
        dna=dnas[0]; dna_ref=_oref(dna)
        for rp in _heads(s,'DESIGN_DNA_REVIEW_PACKAGE'):
            if rp.get('design_dna_ref')==dna_ref:
                return DesignReviewResult(self.workspace,eng.project_state,_aref(rp),dna_ref,eng.gates.evaluate_gate(s,'DESIGN_DNA',eng.now()).result)
        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        rr=tx.create_artifact('DESIGN_DNA_REVIEW_PACKAGE',{
            'scope':{'type':'DESIGN_DNA'},'design_dna_ref':dna_ref,'voice_lock':_aref(voices[0]),'narrative_spine':_aref(spines[0]),'effective_tokens':_aref(toks[0]),
            'review_summary':{'rule_count':len(dna.get('rules') or []),'reference_count':len(dna.get('references') or []),'visual_thesis':(dna.get('design_intent') or {})['visual_thesis']},
            'extensions':{'design_runtime':{'purpose':'PRE_SCENE_HUMAN_DESIGN_REVIEW','requires_human_decision':True}}
        },origin_refs=[_aref(voices[0]),_aref(spines[0]),_aref(toks[0])])
        tx.commit(); RuntimeStore(self.root,self.workspace).persist(eng); fs=eng.snapshot(); rp=fs.artifacts[(rr['artifact_id'],int(rr['version']))]
        return DesignReviewResult(self.workspace,eng.project_state,_aref(rp),dna_ref,eng.gates.evaluate_gate(fs,'DESIGN_DNA',eng.now()).result)

    def decide(self,plan:dict)->DesignDecisionResult:
        decision=str(plan.get('decision') or '').upper(); actor_id=str(plan.get('actor_id') or '').strip()
        if decision not in {'APPROVED','REJECTED'}: raise DesignRuntimeError('DESIGN_DECISION_INVALID')
        if not actor_id: raise DesignRuntimeError('DESIGN_HUMAN_ACTOR_REQUIRED')
        review=self.review_package(); loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; s=eng.snapshot()
        dna=s.objects[(review.design_dna_ref['id'],int(review.design_dna_ref['version']))]; rp=s.artifacts[(review.review_package_ref['artifact_id'],int(review.review_package_ref['version']))]
        dh=eng.semantic.decision_hash(dna); target=_oref(dna); rc=_aref(rp)
        for ap in _active(s,'APPROVAL'):
            if ap.get('approval_class')=='DESIGN_DNA' and ap.get('target')==target and ap.get('review_context')==rc and ap.get('decision')==decision and (ap.get('actor') or {}).get('actor_id')==actor_id:
                return DesignDecisionResult(self.workspace,eng.project_state,decision,_oref(ap),rc,target,eng.gates.evaluate_gate(s,'DESIGN_DNA',eng.now()).result)
        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        ar=tx.create_approval({'approval_class':'DESIGN_DNA','target':target,'target_decision_sha256':dh,'review_context':rc,'decision':decision,'actor':{'type':'HUMAN','actor_id':actor_id},'decided_at':eng.now()})
        if decision=='APPROVED': tx.transition_project_state('DESIGN_DNA_APPROVED',actor_type='HUMAN',human_confirmed=True)
        tx.commit(); RuntimeStore(self.root,self.workspace).persist(eng); fs=eng.snapshot(); gate=eng.gates.evaluate_gate(fs,'DESIGN_DNA',eng.now()).result
        return DesignDecisionResult(self.workspace,eng.project_state,decision,ar,rc,target,gate)
