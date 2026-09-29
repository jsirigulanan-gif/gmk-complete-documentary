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


class RoughNarrativeError(RuntimeError):
    pass


def _sha256_json(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out=[]
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: x['id'])


def _active_by_id(state, object_id: str) -> dict[str, Any]:
    for reg in state.registries.values():
        entry=reg.entries.get(object_id)
        if entry and entry.active_version is not None:
            return state.objects[(object_id, int(entry.active_version))]
    raise RoughNarrativeError(f'ROUGH_NARRATIVE_ACTIVE_OBJECT_NOT_FOUND: {object_id}')


def _unique_refs(refs: list[dict[str,Any]]) -> list[dict[str,Any]]:
    seen=set(); out=[]
    for ref in refs:
        key=(ref.get('id'), int(ref.get('version',0)))
        if key in seen: continue
        seen.add(key); out.append(deepcopy(ref))
    return out


@dataclass(frozen=True)
class RoughNarrativeResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    narrative_spine_ref: dict[str,Any]
    act_refs: tuple[dict[str,Any],...]
    scene_refs: tuple[dict[str,Any],...]
    beat_refs: tuple[dict[str,Any],...]
    included_claim_refs: tuple[dict[str,Any],...]
    excluded_claim_ids: tuple[str,...]
    gate_result: str
    idempotent_replay: bool=False

    def to_dict(self)->dict[str,Any]:
        return {
            'workspace': str(self.workspace),
            'batch_id': self.batch_id,
            'project_state': self.project_state,
            'manifest_version': self.manifest_version,
            'narrative_spine_ref': self.narrative_spine_ref,
            'act_refs': list(self.act_refs),
            'scene_refs': list(self.scene_refs),
            'beat_refs': list(self.beat_refs),
            'included_claim_refs': list(self.included_claim_refs),
            'excluded_claim_ids': list(self.excluded_claim_ids),
            'gate_result': self.gate_result,
            'idempotent_replay': self.idempotent_replay,
        }


class RoughNarrativeRuntime:
    """Compile an audited research graph into a rough narrative graph.

    The runtime is deliberately conservative: factual Beat bindings may reference only
    current exact Claim versions that Research Audit has marked narratable. It does not
    manufacture research truth and it does not create final narration or visual plans.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root=Path(schema_root); self.workspace=Path(workspace)

    def _replay(self, state, batch_id: str, plan_sha256: str) -> RoughNarrativeResult|None:
        matches=[]
        for art in state.artifacts.values():
            if art.get('artifact_type') != 'NARRATIVE_SPINE': continue
            ext=(art.get('extensions') or {}).get('rough_narrative') or {}
            if ext.get('batch_id') == batch_id: matches.append(art)
        if not matches: return None
        exact=[a for a in matches if ((a.get('extensions') or {}).get('rough_narrative') or {}).get('plan_sha256') == plan_sha256]
        if not exact:
            raise RoughNarrativeError(f'ROUGH_NARRATIVE_BATCH_ID_COLLISION: {batch_id} already exists with different plan content.')
        art=max(exact,key=lambda x:int(x['version']))
        ext=(art.get('extensions') or {}).get('rough_narrative') or {}
        return RoughNarrativeResult(
            self.workspace,batch_id,state.project_state,state.manifest_version,
            {'artifact_id':art['artifact_id'],'artifact_type':art['artifact_type'],'version':art['version'],'sha256':art['sha256']},
            tuple(ext.get('act_refs') or ()),tuple(ext.get('scene_refs') or ()),tuple(ext.get('beat_refs') or ()),
            tuple(ext.get('included_claim_refs') or ()),tuple(ext.get('excluded_claim_ids') or ()),
            'UNKNOWN',True,
        )

    @staticmethod
    def _validate_plan_shape(plan: dict[str,Any]) -> None:
        if not plan.get('acts'):
            raise RoughNarrativeError('ROUGH_NARRATIVE_ACTS_REQUIRED')
        act_keys=[str(a.get('key')) for a in plan['acts']]
        if len(act_keys)!=len(set(act_keys)) or any(k in {'','None'} for k in act_keys):
            raise RoughNarrativeError('ROUGH_NARRATIVE_ACT_KEYS_INVALID')
        scene_keys=[]; beat_keys=[]
        for act in plan['acts']:
            scenes=act.get('scenes') or []
            if not scenes: raise RoughNarrativeError(f"ROUGH_NARRATIVE_SCENE_REQUIRED: {act.get('key')}")
            for scene in scenes:
                sk=str(scene.get('key')); scene_keys.append(sk)
                beats=scene.get('beats') or []
                if not beats: raise RoughNarrativeError(f'ROUGH_NARRATIVE_BEAT_REQUIRED: {sk}')
                for beat in beats: beat_keys.append(str(beat.get('key')))
        if len(scene_keys)!=len(set(scene_keys)) or any(k in {'','None'} for k in scene_keys):
            raise RoughNarrativeError('ROUGH_NARRATIVE_SCENE_KEYS_INVALID')
        if len(beat_keys)!=len(set(beat_keys)) or any(k in {'','None'} for k in beat_keys):
            raise RoughNarrativeError('ROUGH_NARRATIVE_BEAT_KEYS_INVALID')
        spine=plan.get('spine') or {}
        for field in ('core_question','opening_promise','major_turns'):
            if not spine.get(field): raise RoughNarrativeError(f'ROUGH_NARRATIVE_SPINE_FIELD_REQUIRED: {field}')

    @staticmethod
    def _validate_claim(claim: dict[str,Any]) -> None:
        if claim.get('object_type')!='CLAIM':
            raise RoughNarrativeError(f"ROUGH_NARRATIVE_CLAIM_TYPE_INVALID: {claim.get('id')}")
        if (claim.get('stale') or {}).get('is_stale') or claim.get('status') in {'STALE','BLOCKED','ARCHIVED','REJECTED'}:
            raise RoughNarrativeError(f"ROUGH_NARRATIVE_CLAIM_NOT_CURRENT: {claim.get('id')}@{claim.get('version')}")
        prod=claim.get('production_use') or {}
        if not prod.get('narration_allowed') or prod.get('language_mode')=='PROHIBITED':
            raise RoughNarrativeError(f"ROUGH_NARRATIVE_CLAIM_PROHIBITED: {claim.get('id')}@{claim.get('version')}")
        if claim.get('verification_state') in {'UNREVIEWED','INSUFFICIENT_EVIDENCE','CONTESTED','DISPROVEN','UNRESOLVED'}:
            raise RoughNarrativeError(f"ROUGH_NARRATIVE_CLAIM_VERIFICATION_INELIGIBLE: {claim.get('id')}={claim.get('verification_state')}")

    def run(self, narrative_plan: dict[str,Any], *, transition_if_ready: bool=True) -> RoughNarrativeResult:
        plan=deepcopy(narrative_plan); self._validate_plan_shape(plan)
        batch_id=str(plan.get('batch_id') or ('ROUGH_NARRATIVE_'+_sha256_json(plan)[:16].upper()))
        plan_sha256=_sha256_json(plan)
        loaded=ColdStartLoader(self.root,self.workspace).load(); engine=loaded.engine; state=engine.snapshot()
        replay=self._replay(state,batch_id,plan_sha256)
        if replay:
            gate=engine.gates.evaluate_gate(state,'ROUGH_NARRATIVE',engine.now()).result
            return RoughNarrativeResult(replay.workspace,replay.batch_id,engine.project_state,engine.manifest_version,replay.narrative_spine_ref,replay.act_refs,replay.scene_refs,replay.beat_refs,replay.included_claim_refs,replay.excluded_claim_ids,gate,True)
        if engine.project_state!='RESEARCH_AUDITED':
            raise RoughNarrativeError(f'ROUGH_NARRATIVE_STATE_INVALID: expected RESEARCH_AUDITED, found {engine.project_state}')

        projects=_active_objects(state,'PROJECT')
        if len(projects)!=1:
            raise RoughNarrativeError(f'ROUGH_NARRATIVE_PROJECT_CARDINALITY_INVALID: expected 1 active PROJECT, found {len(projects)}')
        project=projects[0]; project_ref={'id':project['id'],'version':project['version']}

        # Resolve every referenced Claim against ACTIVE before opening a transaction.
        claim_ids=[]
        for act in plan['acts']:
            for scene in act['scenes']:
                for beat in scene['beats']:
                    for binding in beat.get('claims') or []:
                        claim_ids.append(str(binding['claim_id']))
        claim_ids=list(dict.fromkeys(claim_ids))
        claims={cid:_active_by_id(state,cid) for cid in claim_ids}
        for claim in claims.values(): self._validate_claim(claim)
        included_claim_refs=_unique_refs([{'id':claims[c]['id'],'version':claims[c]['version']} for c in claim_ids])
        excluded_claim_ids=tuple(sorted(str(x) for x in (plan.get('excluded_claim_ids') or [])))

        tx=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
        act_refs=[]; scene_refs=[]; beat_refs=[]; act_ref_by_key={}; scene_ref_by_key={}; beat_ref_by_key={}
        try:
            for act_spec in plan['acts']:
                payload={
                    'project_ref':project_ref,
                    'order':int(act_spec['order']),
                    'title':act_spec.get('title',''),
                    'narrative':deepcopy(act_spec['narrative']),
                    'extensions':{'rough_narrative':{'batch_id':batch_id,'plan_sha256':plan_sha256,'key':act_spec['key']}},
                }
                if act_spec.get('working_title'): payload['working_title']=act_spec['working_title']
                ref=tx.create_object('ACT',payload); act_refs.append(ref); act_ref_by_key[act_spec['key']]=ref

            for act_spec in plan['acts']:
                aref=act_ref_by_key[act_spec['key']]
                for scene_spec in act_spec['scenes']:
                    payload={
                        'act_ref':aref,
                        'order':int(scene_spec['order']),
                        'title':scene_spec.get('title',''),
                        'narrative':deepcopy(scene_spec['narrative']),
                        'dynamics':deepcopy(scene_spec['dynamics']),
                        'extensions':{'rough_narrative':{'batch_id':batch_id,'plan_sha256':plan_sha256,'key':scene_spec['key']}},
                    }
                    ref=tx.create_object('SCENE',payload); scene_refs.append(ref); scene_ref_by_key[scene_spec['key']]=ref

            for act_spec in plan['acts']:
                for scene_spec in act_spec['scenes']:
                    sref=scene_ref_by_key[scene_spec['key']]
                    for beat_spec in scene_spec['beats']:
                        bindings=[]
                        for b in beat_spec.get('claims') or []:
                            claim=claims[str(b['claim_id'])]
                            bindings.append({'claim_ref':{'id':claim['id'],'version':claim['version']},'role':b.get('role','PRIMARY_FACT')})
                        payload={
                            'scene_ref':sref,
                            'order':int(beat_spec['order']),
                            'beat_type':beat_spec['beat_type'],
                            'idea':{'summary':beat_spec['idea']},
                            'viewer_takeaway':beat_spec['viewer_takeaway'],
                            'claim_bindings':bindings,
                            'workflow_state':'RESEARCH_BOUND',
                            'extensions':{'rough_narrative':{
                                'batch_id':batch_id,'plan_sha256':plan_sha256,'key':beat_spec['key'],
                                'research_modes':{cid:(claims[cid].get('production_use') or {}).get('language_mode') for cid in [str(x['claim_id']) for x in beat_spec.get('claims') or []]},
                                'synthesis_note':beat_spec.get('synthesis_note',''),
                            }},
                        }
                        if beat_spec.get('reveal') is not None: payload['reveal']=deepcopy(beat_spec['reveal'])
                        if beat_spec.get('pause') is not None: payload['pause']=deepcopy(beat_spec['pause'])
                        ref=tx.create_object('NARRATION_BEAT',payload); beat_refs.append(ref); beat_ref_by_key[beat_spec['key']]=ref

            # Add promise/payoff and narrative links only after exact Beat refs exist.
            link_edits=[]
            for act_spec in plan['acts']:
                for scene_spec in act_spec['scenes']:
                    for beat_spec in scene_spec['beats']:
                        patch={}
                        pp=beat_spec.get('promise_payoff')
                        if pp:
                            rec={'role':pp['role']}
                            if pp.get('paired_beat_key'): rec['paired_beat_ref']=beat_ref_by_key[pp['paired_beat_key']]
                            patch['promise_payoff']=rec
                        links=[]
                        for link in beat_spec.get('narrative_links') or []:
                            links.append({'type':link['type'],'target_beat_ref':beat_ref_by_key[link['target_beat_key']]})
                        if links: patch['narrative_links']=links
                        if not patch: continue
                        base=beat_ref_by_key[beat_spec['key']]
                        nr=tx.create_version(base['id'],base_version=base['version'],patch=patch)
                        tx.promote_active_version(nr['id'],nr['version'])
                        beat_ref_by_key[beat_spec['key']]=nr
            beat_refs=[beat_ref_by_key[b['key']] for a in plan['acts'] for s in a['scenes'] for b in s['beats']]

            spine=plan['spine']
            spine_payload={
                'project_ref':project_ref,
                'core_question':spine['core_question'],
                'opening_promise':spine['opening_promise'],
                'central_mystery':spine.get('central_mystery',''),
                'major_turns':list(spine['major_turns']),
                'final_answer':spine.get('final_answer',''),
                'closing_thought':spine.get('closing_thought',''),
                'extensions':{'rough_narrative':{
                    'batch_id':batch_id,'plan_sha256':plan_sha256,
                    'act_refs':act_refs,'scene_refs':scene_refs,'beat_refs':beat_refs,
                    'included_claim_refs':included_claim_refs,'excluded_claim_ids':list(excluded_claim_ids),
                    'research_boundary':'Only current audited Claims with narration_allowed=true may enter factual Beat bindings. No final narration or visual requirement is created at this stage.',
                }},
            }
            spine_ref=tx.create_artifact('NARRATIVE_SPINE',spine_payload,origin_refs=[project_ref,*included_claim_refs])
            tx.commit()
        except Exception:
            tx.discard(); raise

        gate=engine.gates.evaluate_gate(engine.snapshot(),'ROUGH_NARRATIVE',engine.now()).result
        if transition_if_ready and gate in {'PASS','WARN'} and engine.project_state=='RESEARCH_AUDITED':
            t2=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
            try:
                t2.transition_project_state('ROUGH_NARRATIVE_READY',actor_type='AI',human_confirmed=False); t2.commit()
            except StateEngineError:
                t2.discard(); raise
        manifest=RuntimeStore(self.root,self.workspace).persist(engine)
        return RoughNarrativeResult(self.workspace,batch_id,engine.project_state,manifest['manifest_version'],spine_ref,tuple(act_refs),tuple(scene_refs),tuple(beat_refs),tuple(included_claim_refs),excluded_claim_ids,gate,False)
