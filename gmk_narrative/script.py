from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state.errors import StateEngineError


class ScriptRuntimeError(RuntimeError):
    pass


def _sha256_json(data: Any) -> str:
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out=[]
    for reg in state.registries.values():
        for oid,entry in reg.entries.items():
            if entry.object_type!=object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid,int(entry.active_version))])
    return sorted(out,key=lambda x:x['id'])


def _oref(o: dict[str, Any]) -> dict[str, Any]:
    return {'id':o['id'],'version':int(o['version'])}


def _aref(a: dict[str, Any]) -> dict[str, Any]:
    return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}


@dataclass(frozen=True)
class ScriptRuntimeResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    script_ref: dict[str, Any]
    beat_refs: tuple[dict[str, Any], ...]
    block_count: int
    language: str
    gate_result: str
    transitioned: bool
    idempotent_replay: bool=False

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace':str(self.workspace),'batch_id':self.batch_id,'project_state':self.project_state,
            'manifest_version':self.manifest_version,'script_ref':dict(self.script_ref),'beat_refs':list(self.beat_refs),
            'block_count':self.block_count,'language':self.language,'gate_result':self.gate_result,
            'transitioned':self.transitioned,'idempotent_replay':self.idempotent_replay,
        }


class ScriptRuntime:
    """Compile final narration from current, research-bound Beats after visual coverage.

    Build 021 intentionally keeps the frozen VOICEOVER_SCRIPT_FINAL contract. The
    stronger completeness/currentness rules live in this runtime: exact one-to-one
    Beat coverage, no placeholders, current Claim eligibility, conservative language
    mode derivation, decision-hash pinning, and Gate-controlled SCRIPT_READY entry.
    """

    PLACEHOLDER_TOKENS={'TBD','TODO','PLACEHOLDER','FILLER','TEMP COPY','LOREM IPSUM'}
    MODE_RANK={
        'DIRECT':0,'ATTRIBUTED':1,'QUALIFIED':2,'THEORY':3,
        'INTERPRETIVE':4,'UNRESOLVED':5,'PROHIBITED':6,
    }

    def __init__(self,schema_root: Path,workspace: Path):
        self.root=Path(schema_root); self.workspace=Path(workspace)

    @staticmethod
    def _beat_key(beat: dict[str,Any]) -> str:
        key=(((beat.get('extensions') or {}).get('rough_narrative') or {}).get('key'))
        if not key: raise ScriptRuntimeError(f"SCRIPT_BEAT_KEY_MISSING: {beat.get('id')}@{beat.get('version')}")
        return str(key)

    @classmethod
    def _required_mode(cls,beat: dict[str,Any],state) -> str:
        modes=[]
        for binding in beat.get('claim_bindings') or []:
            ref=binding.get('claim_ref') or {}
            claim=state.objects.get((ref.get('id'),int(ref.get('version',0))))
            if not claim: raise ScriptRuntimeError(f"SCRIPT_CLAIM_REF_MISSING: {ref}")
            # Exact Claim refs used by narration must still be the ACTIVE version.
            active=None
            for reg in state.registries.values():
                entry=reg.entries.get(claim['id'])
                if entry:
                    active=entry.active_version; break
            if active is None or int(active)!=int(claim['version']):
                raise ScriptRuntimeError(f"SCRIPT_CLAIM_NOT_CURRENT: {claim['id']}@{claim['version']}")
            prod=claim.get('production_use') or {}
            mode=str(prod.get('language_mode') or 'PROHIBITED')
            if not prod.get('narration_allowed') or mode=='PROHIBITED':
                raise ScriptRuntimeError(f"SCRIPT_CLAIM_PROHIBITED: {claim['id']}@{claim['version']}")
            modes.append(mode)
        if not modes: return 'INTERPRETIVE'
        return max(modes,key=lambda m:cls.MODE_RANK.get(m,99))

    @classmethod
    def _validate_text(cls,key: str,text: Any) -> str:
        value=str(text or '').strip()
        if not value: raise ScriptRuntimeError(f'SCRIPT_NARRATION_REQUIRED: {key}')
        upper=value.upper()
        if any(tok in upper for tok in cls.PLACEHOLDER_TOKENS):
            raise ScriptRuntimeError(f'SCRIPT_PLACEHOLDER_FORBIDDEN: {key}')
        return value

    @classmethod
    def _validate_plan(cls,plan: dict[str,Any]) -> None:
        if not str(plan.get('language') or '').strip(): raise ScriptRuntimeError('SCRIPT_LANGUAGE_REQUIRED')
        blocks=plan.get('blocks') or []
        if not blocks: raise ScriptRuntimeError('SCRIPT_BLOCKS_REQUIRED')
        keys=[]
        for b in blocks:
            key=str(b.get('beat_key') or '').strip()
            if not key: raise ScriptRuntimeError('SCRIPT_BEAT_KEY_REQUIRED')
            cls._validate_text(key,b.get('narration_text'))
            mode=str(b.get('language_mode') or '')
            if mode not in cls.MODE_RANK or mode=='PROHIBITED': raise ScriptRuntimeError(f'SCRIPT_LANGUAGE_MODE_INVALID: {key}')
            keys.append(key)
        if len(keys)!=len(set(keys)): raise ScriptRuntimeError('SCRIPT_DUPLICATE_BEAT_KEY')

    @staticmethod
    def _script_heads(state) -> list[dict[str,Any]]:
        heads={}
        for (aid,v),art in state.artifacts.items():
            if art.get('artifact_type')!='VOICEOVER_SCRIPT_FINAL': continue
            cur=heads.get(aid)
            if cur is None or int(v)>int(cur['version']): heads[aid]=art
        return list(heads.values())

    def _replay(self,state,batch_id: str,plan_sha: str) -> ScriptRuntimeResult|None:
        matching=[]
        for art in self._script_heads(state):
            ext=(art.get('extensions') or {}).get('script_runtime') or {}
            if ext.get('batch_id')==batch_id:
                if ext.get('plan_sha256')!=plan_sha:
                    raise ScriptRuntimeError('SCRIPT_BATCH_ID_COLLISION')
                matching.append(art)
        if not matching: return None
        art=sorted(matching,key=lambda a:(a['artifact_id'],int(a['version'])))[-1]
        beat_refs=tuple(dict(b['beat_ref']) for b in art.get('blocks') or [])
        return ScriptRuntimeResult(self.workspace,batch_id,'',0,_aref(art),beat_refs,len(beat_refs),art.get('language',''),'',False,True)

    def run(self,script_plan: dict[str,Any]) -> ScriptRuntimeResult:
        plan=deepcopy(script_plan); self._validate_plan(plan)
        batch_id=str(plan.get('batch_id') or ('SCRIPT_'+_sha256_json(plan)[:16].upper()))
        plan_sha=_sha256_json(plan)
        loaded=ColdStartLoader(self.root,self.workspace).load(); engine=loaded.engine; state=engine.snapshot()
        replay=self._replay(state,batch_id,plan_sha)
        if replay:
            gate=engine.gates.evaluate_gate(state,'SCRIPT',engine.now()).result
            return ScriptRuntimeResult(self.workspace,batch_id,engine.project_state,engine.manifest_version,replay.script_ref,replay.beat_refs,replay.block_count,replay.language,gate,False,True)
        if engine.project_state!='VISUAL_COVERAGE_READY':
            raise ScriptRuntimeError(f'SCRIPT_STATE_INVALID: expected VISUAL_COVERAGE_READY, found {engine.project_state}')

        beats=_active_objects(state,'NARRATION_BEAT')
        if not beats: raise ScriptRuntimeError('SCRIPT_ACTIVE_BEATS_MISSING')
        by_key={self._beat_key(b):b for b in beats}
        requested={str(b['beat_key']):b for b in plan['blocks']}
        if set(requested)!=set(by_key):
            missing=sorted(set(by_key)-set(requested)); extra=sorted(set(requested)-set(by_key))
            raise ScriptRuntimeError(f'SCRIPT_BEAT_COVERAGE_MISMATCH: missing={missing} extra={extra}')
        for beat in beats:
            if beat.get('workflow_state')!='VISUAL_REQUIREMENT_READY':
                raise ScriptRuntimeError(f"SCRIPT_BEAT_STATE_INVALID: {beat['id']}@{beat['version']}={beat.get('workflow_state')}")
            if not beat.get('visual_requirement'):
                raise ScriptRuntimeError(f"SCRIPT_VISUAL_REQUIREMENT_MISSING: {beat['id']}@{beat['version']}")

        # Validate language policy against exact current Claims before mutation.
        prepared={}
        for key,beat in by_key.items():
            spec=requested[key]; text=self._validate_text(key,spec['narration_text'])
            required=self._required_mode(beat,state); supplied=str(spec['language_mode'])
            if self.MODE_RANK[supplied] < self.MODE_RANK[required]:
                raise ScriptRuntimeError(f'SCRIPT_LANGUAGE_MODE_TOO_STRONG: {key} requires {required}, got {supplied}')
            prepared[key]=(text,supplied,required)

        tx=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
        beat_refs=[]
        try:
            for beat in sorted(beats,key=lambda b:(b.get('scene_ref',{}).get('id',''),int(b.get('order',0)),b['id'])):
                key=self._beat_key(beat); text,mode,required=prepared[key]
                ext=deepcopy(beat.get('extensions') or {})
                ext['script_runtime']={'batch_id':batch_id,'plan_sha256':plan_sha,'beat_key':key,'required_language_mode':required}
                nr=tx.create_version(beat['id'],base_version=int(beat['version']),patch={
                    'narration':{'text':text,'language_mode':mode},
                    'workflow_state':'NARRATION_FINAL','extensions':ext,
                })
                tx.promote_active_version(nr['id'],nr['version'])
                beat_refs.append(nr)

            # Compile from staged exact Beat versions after promotion.
            blocks=[]
            for ref in beat_refs:
                b=tx.staged.objects[(ref['id'],int(ref['version']))]
                blocks.append({'beat_ref':dict(ref),'decision_sha256':engine.semantic.decision_hash(b),'narration_text':b['narration']['text']})
            projects=_active_objects(tx.staged,'PROJECT')
            if len(projects)!=1: raise ScriptRuntimeError(f'SCRIPT_PROJECT_CARDINALITY_INVALID: {len(projects)}')
            script_ref=tx.create_artifact('VOICEOVER_SCRIPT_FINAL',{
                'project_ref':_oref(projects[0]),'language':str(plan['language']),'blocks':blocks,
                'extensions':{'script_runtime':{'batch_id':batch_id,'plan_sha256':plan_sha,'block_count':len(blocks)}},
            },origin_refs=[_oref(projects[0]),*beat_refs])
            tx.commit()
        except Exception:
            tx.discard(); raise

        gate=engine.gates.evaluate_gate(engine.snapshot(),'SCRIPT',engine.now()).result
        transitioned=False
        if gate in {'PASS','WARN'}:
            t2=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
            try:
                t2.transition_project_state('SCRIPT_READY',actor_type='AI',human_confirmed=False); t2.commit(); transitioned=True
            except StateEngineError:
                t2.discard(); raise
        manifest=RuntimeStore(self.root,self.workspace).persist(engine)
        final=engine.snapshot().artifacts[(script_ref['artifact_id'],int(script_ref['version']))]
        return ScriptRuntimeResult(self.workspace,batch_id,engine.project_state,manifest['manifest_version'],_aref(final),tuple(beat_refs),len(beat_refs),str(plan['language']),gate,transitioned,False)
