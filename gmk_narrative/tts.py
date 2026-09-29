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


class TTSRuntimeError(RuntimeError):
    pass


def _sha256_json(data: Any) -> str:
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _oref(o: dict[str, Any]) -> dict[str, Any]:
    return {'id':o['id'],'version':int(o['version'])}


def _aref(a: dict[str, Any]) -> dict[str, Any]:
    return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}


def _artifact_heads(state, artifact_type: str) -> list[dict[str,Any]]:
    out=[]
    for aid,e in state.artifact_registry.entries.items():
        if e.artifact_type!=artifact_type: continue
        out.append(state.artifacts[(aid,int(e.head_version))])
    return sorted(out,key=lambda a:a['artifact_id'])


def _active_objects(state, object_type: str) -> list[dict[str,Any]]:
    out=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type==object_type and e.active_version is not None:
                out.append(state.objects[(oid,int(e.active_version))])
    return sorted(out,key=lambda o:o['id'])


@dataclass(frozen=True)
class TTSRuntimeResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    source_script_ref: dict[str,Any]
    pronunciation_dictionary_ref: dict[str,Any]
    voice_profile_ref: dict[str,Any]
    tts_script_ref: dict[str,Any]
    voice_block_refs: tuple[dict[str,Any], ...]
    block_count: int
    gate_result: str
    transitioned: bool
    idempotent_replay: bool=False

    def to_dict(self) -> dict[str,Any]:
        return {
            'workspace':str(self.workspace),'batch_id':self.batch_id,'project_state':self.project_state,
            'manifest_version':self.manifest_version,'source_script_ref':dict(self.source_script_ref),
            'pronunciation_dictionary_ref':dict(self.pronunciation_dictionary_ref),'voice_profile_ref':dict(self.voice_profile_ref),
            'tts_script_ref':dict(self.tts_script_ref),'voice_block_refs':list(self.voice_block_refs),
            'block_count':self.block_count,'gate_result':self.gate_result,'transitioned':self.transitioned,
            'idempotent_replay':self.idempotent_replay,
        }


class TTSRuntime:
    """Compile an exact final voiceover script into TTS-ready planning objects.

    This stage prepares deterministic TTS input; it does not claim that audio has been
    rendered. It creates a pronunciation dictionary, a voice profile, an exact
    TTS_READY_SCRIPT, and one VOICE_BLOCK per script block. The frozen TTS Gate is
    then used to enter TTS_READY.
    """

    PLACEHOLDER_TOKENS={'TBD','TODO','PLACEHOLDER','LOREM IPSUM','TEMP VOICE','FILLER'}
    STYLES={'NEUTRAL_DOCUMENTARY','CALM','INTIMATE','TENSE','URGENT','REFLECTIVE','REVEAL','SOMBER','TECHNICAL_EXPLANATION'}
    RATES={'SLOW','MEDIUM_SLOW','NATURAL','MEDIUM_FAST','FAST'}
    PRON_METHODS={'PLAIN_TEXT','PHONETIC','IPA','SSML_PHONEME','PROVIDER_ALIAS'}

    def __init__(self,schema_root: Path,workspace: Path):
        self.root=Path(schema_root); self.workspace=Path(workspace)

    @classmethod
    def _validate_plan(cls,plan: dict[str,Any]) -> None:
        lang=str(plan.get('language') or '').strip()
        if len(lang)<2: raise TTSRuntimeError('TTS_LANGUAGE_REQUIRED')
        vp=plan.get('voice_profile') or {}
        if not str(vp.get('profile_name') or '').strip(): raise TTSRuntimeError('TTS_VOICE_PROFILE_NAME_REQUIRED')
        engine=str(vp.get('engine_class') or 'TTS')
        if engine not in {'TTS','HYBRID'}: raise TTSRuntimeError('TTS_VOICE_ENGINE_INVALID')
        delivery=vp.get('delivery') or {}
        if delivery.get('default_style') not in cls.STYLES: raise TTSRuntimeError('TTS_DELIVERY_STYLE_INVALID')
        if delivery.get('speech_rate') not in cls.RATES: raise TTSRuntimeError('TTS_SPEECH_RATE_INVALID')
        tech=vp.get('technical_constraints') or {}
        if int(tech.get('sample_rate_hz') or 0)<8000: raise TTSRuntimeError('TTS_SAMPLE_RATE_INVALID')
        if int(tech.get('channels') or 0) not in {1,2}: raise TTSRuntimeError('TTS_CHANNELS_INVALID')
        entries=plan.get('pronunciations') or []
        keys=[]
        for i,e in enumerate(entries):
            term=str(e.get('term') or '').strip(); key=str(e.get('normalized_key') or '').strip()
            p=e.get('pronunciation') or {}; method=str(p.get('method') or ''); value=str(p.get('value') or '').strip()
            if not term or not key or method not in cls.PRON_METHODS or not value:
                raise TTSRuntimeError(f'TTS_PRONUNCIATION_INVALID: index={i}')
            keys.append(key.casefold())
        if len(keys)!=len(set(keys)): raise TTSRuntimeError('TTS_PRONUNCIATION_DUPLICATE_KEY')

    @staticmethod
    def _source_script(state) -> dict[str,Any]:
        scripts=_artifact_heads(state,'VOICEOVER_SCRIPT_FINAL')
        if len(scripts)!=1: raise TTSRuntimeError(f'TTS_SOURCE_SCRIPT_CARDINALITY_INVALID: {len(scripts)}')
        return scripts[0]

    @classmethod
    def _validate_script(cls,script: dict[str,Any],state) -> list[dict[str,Any]]:
        blocks=script.get('blocks') or []
        if not blocks: raise TTSRuntimeError('TTS_SOURCE_SCRIPT_EMPTY')
        seen=set(); normalized=[]
        for i,b in enumerate(blocks,1):
            ref=b.get('beat_ref') or {}; key=(ref.get('id'),int(ref.get('version',0)))
            beat=state.objects.get(key)
            if not beat or beat.get('object_type')!='NARRATION_BEAT': raise TTSRuntimeError(f'TTS_BEAT_REF_INVALID: index={i}')
            # Script must still point at the exact ACTIVE Beat version.
            active=None
            for reg in state.registries.values():
                e=reg.entries.get(beat['id'])
                if e: active=e.active_version; break
            if active is None or int(active)!=int(beat['version']): raise TTSRuntimeError(f'TTS_BEAT_NOT_CURRENT: {beat["id"]}@{beat["version"]}')
            if beat.get('workflow_state')!='NARRATION_FINAL': raise TTSRuntimeError(f'TTS_BEAT_NOT_FINAL: {beat["id"]}@{beat["version"]}')
            text=str(b.get('narration_text') or '').strip()
            if not text: raise TTSRuntimeError(f'TTS_TEXT_REQUIRED: index={i}')
            upper=text.upper()
            if any(tok in upper for tok in cls.PLACEHOLDER_TOKENS): raise TTSRuntimeError(f'TTS_PLACEHOLDER_FORBIDDEN: index={i}')
            if text!=(beat.get('narration') or {}).get('text'): raise TTSRuntimeError(f'TTS_TEXT_DRIFT: {beat["id"]}@{beat["version"]}')
            if key in seen: raise TTSRuntimeError('TTS_DUPLICATE_BEAT')
            seen.add(key)
            normalized.append({'order':i,'beat_ref':dict(ref),'narration_text':text,'decision_sha256':b.get('decision_sha256')})
        active_beats=_active_objects(state,'NARRATION_BEAT')
        active_refs={(b['id'],int(b['version'])) for b in active_beats}
        if seen!=active_refs:
            raise TTSRuntimeError(f'TTS_BEAT_COVERAGE_MISMATCH: script={len(seen)} active={len(active_refs)}')
        return normalized

    def _replay(self,state,batch_id: str,plan_sha: str) -> TTSRuntimeResult|None:
        for art in _artifact_heads(state,'TTS_READY_SCRIPT'):
            ext=(art.get('extensions') or {}).get('tts_runtime') or {}
            if ext.get('batch_id')!=batch_id: continue
            if ext.get('plan_sha256')!=plan_sha: raise TTSRuntimeError('TTS_BATCH_ID_COLLISION')
            pdref=art.get('pronunciation_dictionary') or {}; vpref=art.get('voice_profile_ref') or {}; ssref=art.get('source_script') or {}
            pd=state.artifacts.get((pdref.get('artifact_id'),int(pdref.get('version',0))))
            vp=state.objects.get((vpref.get('id'),int(vpref.get('version',0))))
            ss=state.artifacts.get((ssref.get('artifact_id'),int(ssref.get('version',0))))
            vbs=[]
            for o in _active_objects(state,'VOICE_BLOCK'):
                ref=o.get('tts_script_ref') or {}
                if ref.get('artifact_id')==art['artifact_id'] and int(ref.get('version',0))==int(art['version']): vbs.append(_oref(o))
            if not (pd and vp and ss): raise TTSRuntimeError('TTS_REPLAY_DEPENDENCY_MISSING')
            return TTSRuntimeResult(self.workspace,batch_id,'',0,_aref(ss),_aref(pd),_oref(vp),_aref(art),tuple(vbs),len(art.get('blocks') or []),'',False,True)
        return None

    def run(self,tts_plan: dict[str,Any]) -> TTSRuntimeResult:
        plan=deepcopy(tts_plan); self._validate_plan(plan)
        batch_id=str(plan.get('batch_id') or ('TTS_'+_sha256_json(plan)[:16].upper()))
        plan_sha=_sha256_json(plan)
        loaded=ColdStartLoader(self.root,self.workspace).load(); engine=loaded.engine; state=engine.snapshot()
        replay=self._replay(state,batch_id,plan_sha)
        if replay:
            gate=engine.gates.evaluate_gate(state,'TTS',engine.now()).result
            return TTSRuntimeResult(self.workspace,batch_id,engine.project_state,engine.manifest_version,replay.source_script_ref,replay.pronunciation_dictionary_ref,replay.voice_profile_ref,replay.tts_script_ref,replay.voice_block_refs,replay.block_count,gate,False,True)
        if engine.project_state!='SCRIPT_READY': raise TTSRuntimeError(f'TTS_STATE_INVALID: expected SCRIPT_READY, found {engine.project_state}')

        source=self._source_script(state); blocks=self._validate_script(source,state)
        if str(source.get('language') or '')!=str(plan['language']):
            raise TTSRuntimeError(f'TTS_LANGUAGE_MISMATCH: script={source.get("language")} plan={plan["language"]}')

        vp_plan=deepcopy(plan['voice_profile'])
        vp_plan.setdefault('engine_class','TTS'); vp_plan['language']=str(plan['language'])
        # Provider is optional: TTS_READY means provider-neutral input is prepared,
        # not that external synthesis has happened.
        tx=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
        try:
            pd_ref=tx.create_artifact('PRONUNCIATION_DICTIONARY',{
                'language':str(plan['language']),'entries':deepcopy(plan.get('pronunciations') or []),
                'extensions':{'tts_runtime':{'batch_id':batch_id,'plan_sha256':plan_sha}},
            },origin_refs=[_aref(source)])
            vp_ref=tx.create_object('VOICE_PROFILE',{
                'profile_name':vp_plan['profile_name'],'engine_class':vp_plan.get('engine_class','TTS'),'language':str(plan['language']),
                **({'provider':deepcopy(vp_plan['provider'])} if vp_plan.get('provider') else {}),
                'delivery':deepcopy(vp_plan['delivery']),'technical_constraints':deepcopy(vp_plan['technical_constraints']),
                'extensions':{'tts_runtime':{'batch_id':batch_id,'plan_sha256':plan_sha}},
            })
            # Resolve staged records so exact refs/checksums are available.
            pd=tx.staged.artifacts[(pd_ref['artifact_id'],int(pd_ref['version']))]
            tts_blocks=[]
            for b in blocks:
                tts_blocks.append({
                    'order':b['order'],'beat_ref':dict(b['beat_ref']),'text':b['narration_text'],
                    'source_decision_sha256':b.get('decision_sha256'),
                    'delivery':{'style':vp_plan['delivery']['default_style'],'speech_rate':vp_plan['delivery']['speech_rate']},
                })
            tts_ref=tx.create_artifact('TTS_READY_SCRIPT',{
                'source_script':_aref(source),'pronunciation_dictionary':_aref(pd),'voice_profile_ref':dict(vp_ref),'blocks':tts_blocks,
                'extensions':{'tts_runtime':{'batch_id':batch_id,'plan_sha256':plan_sha,'block_count':len(tts_blocks),'rendered_audio':False}},
            },origin_refs=[_aref(source),_aref(pd),dict(vp_ref)])
            tts_art=tx.staged.artifacts[(tts_ref['artifact_id'],int(tts_ref['version']))]
            voice_block_refs=[]
            for b in tts_blocks:
                vb=tx.create_object('VOICE_BLOCK',{
                    'voice_profile_ref':dict(vp_ref),'tts_script_ref':_aref(tts_art),'source_beat_refs':[dict(b['beat_ref'])],
                    'order':int(b['order']),'delivery':{},'workflow_state':'TTS_READY',
                    'extensions':{'tts_runtime':{'batch_id':batch_id,'plan_sha256':plan_sha}},
                })
                voice_block_refs.append(vb)
            tx.commit()
        except Exception:
            tx.discard(); raise

        gate=engine.gates.evaluate_gate(engine.snapshot(),'TTS',engine.now()).result
        transitioned=False
        if gate in {'PASS','WARN'}:
            t2=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
            try:
                t2.transition_project_state('TTS_READY',actor_type='AI',human_confirmed=False); t2.commit(); transitioned=True
            except StateEngineError:
                t2.discard(); raise
        manifest=RuntimeStore(self.root,self.workspace).persist(engine)
        fs=engine.snapshot()
        source_final=fs.artifacts[(source['artifact_id'],int(source['version']))]
        pd_final=fs.artifacts[(pd_ref['artifact_id'],int(pd_ref['version']))]
        vp_final=fs.objects[(vp_ref['id'],int(vp_ref['version']))]
        tts_final=fs.artifacts[(tts_ref['artifact_id'],int(tts_ref['version']))]
        return TTSRuntimeResult(self.workspace,batch_id,engine.project_state,manifest['manifest_version'],_aref(source_final),_aref(pd_final),_oref(vp_final),_aref(tts_final),tuple(voice_block_refs),len(blocks),gate,transitioned,False)
