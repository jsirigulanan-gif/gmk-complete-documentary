from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from copy import deepcopy
import hashlib,json,shutil,subprocess
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.media_tools import resolve_ffprobe, MediaToolNotFound
from gmk_runtime.persistence import RuntimeStore

class VoiceRuntimeError(RuntimeError): pass

def _sha(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def _aref(a): return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}
def _oref(o): return {'id':o['id'],'version':int(o['version'])}
def _heads(s,t):
    return [s.artifacts[(aid,int(e.head_version))] for aid,e in s.artifact_registry.entries.items() if e.artifact_type==t]
def _active(s,t):
    out=[]
    for r in s.registries.values():
        for oid,e in r.entries.items():
            if e.object_type==t and e.active_version is not None: out.append(s.objects[(oid,int(e.active_version))])
    return sorted(out,key=lambda x:(x.get('order',0),x['id']))

def _probe(p:Path):
    try:
        cp=subprocess.run([resolve_ffprobe(),'-v','error','-select_streams','a:0','-show_entries','stream=sample_rate,channels,codec_name','-show_entries','format=duration,format_name','-of','json',str(p)],capture_output=True,text=True,check=True)
        d=json.loads(cp.stdout); streams=d.get('streams') or []
        if not streams: raise VoiceRuntimeError('VOICE_AUDIO_STREAM_REQUIRED')
        st=streams[0]; fmt=d.get('format') or {}; dur=float(fmt.get('duration') or 0)
        if dur<=0: raise VoiceRuntimeError('VOICE_AUDIO_DURATION_INVALID')
        return {'duration_seconds':dur,'sample_rate_hz':int(st.get('sample_rate') or 0),'channels':int(st.get('channels') or 0),'codec':st.get('codec_name'),'container':fmt.get('format_name')}
    except (subprocess.CalledProcessError,ValueError,json.JSONDecodeError,MediaToolNotFound,FileNotFoundError) as e:
        raise VoiceRuntimeError('VOICE_AUDIO_PROBE_FAILED') from e

@dataclass(frozen=True)
class VoicePrepareResult:
    workspace:Path; project_state:str; master_voice_ref:dict; timing_map_ref:dict; voice_lock_ref:dict; block_count:int; approval_ready:bool
    def to_dict(self): return {'workspace':str(self.workspace),'project_state':self.project_state,'master_voice_ref':self.master_voice_ref,'timing_map_ref':self.timing_map_ref,'voice_lock_ref':self.voice_lock_ref,'block_count':self.block_count,'approval_ready':self.approval_ready}

class VoiceRuntime:
    """Build 023 voice preparation. It never self-approves the VOICE gate."""
    def __init__(self,schema_root:Path,workspace:Path): self.root=Path(schema_root); self.workspace=Path(workspace)
    def prepare(self,plan:dict)->VoicePrepareResult:
        loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; s=eng.snapshot()
        if eng.project_state!='TTS_READY': raise VoiceRuntimeError(f'VOICE_STATE_INVALID: expected TTS_READY, found {eng.project_state}')
        existing=_heads(s,'VOICE_LOCK_MANIFEST')
        if existing:
            lock=existing[0]; return VoicePrepareResult(self.workspace,eng.project_state,lock['master_voice'],lock['timing_map'],_aref(lock),len(lock.get('voice_blocks') or []),False)
        src=Path(str(plan.get('master_audio_path') or ''))
        if not src.is_file(): raise VoiceRuntimeError('VOICE_MASTER_AUDIO_REQUIRED')
        tech=_probe(src); digest=_sha(src)
        tts=_heads(s,'TTS_READY_SCRIPT'); script=_heads(s,'VOICEOVER_SCRIPT_FINAL'); pd=_heads(s,'PRONUNCIATION_DICTIONARY'); vp=_active(s,'VOICE_PROFILE'); blocks=_active(s,'VOICE_BLOCK'); projects=_active(s,'PROJECT')
        if not(len(tts)==len(script)==len(pd)==len(vp)==len(projects)==1): raise VoiceRuntimeError('VOICE_DEPENDENCY_CARDINALITY_INVALID')
        if not blocks: raise VoiceRuntimeError('VOICE_BLOCKS_REQUIRED')
        timings=plan.get('timings') or []
        if len(timings)!=len(blocks): raise VoiceRuntimeError('VOICE_TIMING_COVERAGE_MISMATCH')
        by_order={int(x.get('order',0)):x for x in timings}; last=0.0; tm=[]
        for b in blocks:
            x=by_order.get(int(b['order']))
            if not x: raise VoiceRuntimeError(f'VOICE_TIMING_MISSING: {b["order"]}')
            st=float(x.get('start_seconds',-1)); en=float(x.get('end_seconds',-1))
            if st<last-0.005 or en<=st or en>tech['duration_seconds']+0.005: raise VoiceRuntimeError(f'VOICE_TIMING_INVALID: {b["order"]}')
            tm.append({'order':int(b['order']),'voice_block_ref':_oref(b),'start_seconds':st,'end_seconds':en}); last=en
        dest=self.workspace/'media'/'voice'; dest.mkdir(parents=True,exist_ok=True); ext=src.suffix.lower() or '.audio'; out=dest/f'master_voice_{digest[:16]}{ext}'
        if not out.exists(): shutil.copy2(src,out)
        uri='gmk://workspace/'+str(out.relative_to(self.workspace)).replace('\\','/')
        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        mv=tx.create_artifact('MASTER_VOICE',{'project_ref':_oref(projects[0]),'source_voice_blocks':[_oref(x) for x in blocks],'audio':{'uri':uri,'sha256':digest,'duration_seconds':tech['duration_seconds'],'sample_rate_hz':tech['sample_rate_hz'],'channels':tech['channels']},'extensions':{'voice_runtime':{'verified_bytes':True,'codec':tech['codec'],'container':tech['container']}}},origin_refs=[_aref(tts[0])])
        mva=tx.staged.artifacts[(mv['artifact_id'],int(mv['version']))]
        vtm=tx.create_artifact('VOICE_TIMING_MAP',{'master_voice':_aref(mva),'duration_seconds':tech['duration_seconds'],'blocks':tm},origin_refs=[_aref(mva)])
        vtma=tx.staged.artifacts[(vtm['artifact_id'],int(vtm['version']))]
        # Imported-master mode deliberately keeps VOICE_BLOCK identities unchanged here.
        # Revising each block to point back to MASTER_VOICE would create a dependency cycle
        # (MASTER_VOICE already derives from those blocks) and correctly stale the graph.
        locked_blocks=[_oref(b) for b in blocks]
        lock=tx.create_artifact('VOICE_LOCK_MANIFEST',{'voice_profile_ref':_oref(vp[0]),'voiceover_script':_aref(script[0]),'tts_script':_aref(tts[0]),'pronunciation_dictionary':_aref(pd[0]),'voice_blocks':locked_blocks,'master_voice':_aref(mva),'timing_map':_aref(vtma),'extensions':{'voice_runtime':{'human_approval_required':True,'approval_created':False,'mode':'IMPORTED_MASTER'}}},origin_refs=[_aref(mva),_aref(vtma),_aref(tts[0])])
        tx.commit(); RuntimeStore(self.root,self.workspace).persist(eng); fs=eng.snapshot(); la=fs.artifacts[(lock['artifact_id'],int(lock['version']))]
        gate=eng.gates.evaluate_gate(fs,'VOICE',eng.now()).result
        if gate!='FAIL': raise VoiceRuntimeError('VOICE_GATE_SHOULD_REQUIRE_HUMAN_APPROVAL')
        return VoicePrepareResult(self.workspace,eng.project_state,_aref(fs.artifacts[(mv['artifact_id'],int(mv['version']))]),_aref(fs.artifacts[(vtm['artifact_id'],int(vtm['version']))]),_aref(la),len(locked_blocks),False)

@dataclass(frozen=True)
class VoiceReviewResult:
    workspace:Path; project_state:str; review_package_ref:dict; voice_lock_ref:dict; gate_result:str
    def to_dict(self): return {'workspace':str(self.workspace),'project_state':self.project_state,'review_package_ref':self.review_package_ref,'voice_lock_ref':self.voice_lock_ref,'gate_result':self.gate_result}

@dataclass(frozen=True)
class VoiceDecisionResult:
    workspace:Path; project_state:str; decision:str; approval_ref:dict; review_package_ref:dict; voice_lock_ref:dict; gate_result:str
    def to_dict(self): return {'workspace':str(self.workspace),'project_state':self.project_state,'decision':self.decision,'approval_ref':self.approval_ref,'review_package_ref':self.review_package_ref,'voice_lock_ref':self.voice_lock_ref,'gate_result':self.gate_result}

def _voice_review_heads(s):
    return _heads(s,'VOICE_REVIEW_PACKAGE')

def _approval_objects(s):
    return _active(s,'APPROVAL')

def _same_aref(a,b):
    return bool(a and b) and a.get('artifact_id')==b.get('artifact_id') and int(a.get('version',0))==int(b.get('version',0)) and a.get('sha256')==b.get('sha256')

def _make_review_package(self)->VoiceReviewResult:
    loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; s=eng.snapshot()
    if eng.project_state not in {'TTS_READY','VOICE_LOCKED'}:
        raise VoiceRuntimeError(f'VOICE_REVIEW_STATE_INVALID: expected TTS_READY/VOICE_LOCKED, found {eng.project_state}')
    locks=_heads(s,'VOICE_LOCK_MANIFEST')
    if len(locks)!=1: raise VoiceRuntimeError('VOICE_REVIEW_LOCK_REQUIRED')
    lock=locks[0]; lock_ref=_aref(lock)
    for rp in _voice_review_heads(s):
        if _same_aref(rp.get('voice_lock'),lock_ref):
            return VoiceReviewResult(self.workspace,eng.project_state,_aref(rp),lock_ref,eng.gates.evaluate_gate(s,'VOICE',eng.now()).result)
    mv=s.artifacts.get((lock['master_voice']['artifact_id'],int(lock['master_voice']['version'])))
    tm=s.artifacts.get((lock['timing_map']['artifact_id'],int(lock['timing_map']['version'])))
    tts=s.artifacts.get((lock['tts_script']['artifact_id'],int(lock['tts_script']['version'])))
    if not mv or not tm or not tts: raise VoiceRuntimeError('VOICE_REVIEW_DEPENDENCY_MISSING')
    audio=mv.get('audio') or {}
    tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
    rr=tx.create_artifact('VOICE_REVIEW_PACKAGE',{
        'scope':{'type':'VOICE_LOCK'},
        'voice_lock':lock_ref,'master_voice':_aref(mv),'timing_map':_aref(tm),'tts_script':_aref(tts),
        'review_summary':{'block_count':len(lock.get('voice_blocks') or []),'duration_seconds':float(audio['duration_seconds']),'audio_sha256':audio['sha256']},
        'extensions':{'voice_runtime':{'purpose':'PRE_SCENE_HUMAN_VOICE_REVIEW','requires_human_decision':True}}
    },origin_refs=[lock_ref,_aref(mv),_aref(tm),_aref(tts)])
    tx.commit(); RuntimeStore(self.root,self.workspace).persist(eng)
    fs=eng.snapshot(); rp=fs.artifacts[(rr['artifact_id'],int(rr['version']))]
    return VoiceReviewResult(self.workspace,eng.project_state,_aref(rp),lock_ref,eng.gates.evaluate_gate(fs,'VOICE',eng.now()).result)

def _decide_voice(self,plan:dict)->VoiceDecisionResult:
    decision=str(plan.get('decision') or '').upper(); actor_id=str(plan.get('actor_id') or '').strip()
    if decision not in {'APPROVED','REJECTED'}: raise VoiceRuntimeError('VOICE_DECISION_INVALID')
    if not actor_id: raise VoiceRuntimeError('VOICE_HUMAN_ACTOR_REQUIRED')
    review=_make_review_package(self)
    loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; s=eng.snapshot()
    lock=s.artifacts[(review.voice_lock_ref['artifact_id'],int(review.voice_lock_ref['version']))]
    rp=s.artifacts[(review.review_package_ref['artifact_id'],int(review.review_package_ref['version']))]
    target=_aref(lock); rc=_aref(rp)
    for ap in _approval_objects(s):
        if ap.get('approval_class')=='VOICE' and ap.get('target')==target and ap.get('review_context')==rc and ap.get('decision')==decision and (ap.get('actor') or {}).get('actor_id')==actor_id:
            return VoiceDecisionResult(self.workspace,eng.project_state,decision,_oref(ap),rc,target,eng.gates.evaluate_gate(s,'VOICE',eng.now()).result)
    tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
    ar=tx.create_approval({'approval_class':'VOICE','target':target,'review_context':rc,'decision':decision,'actor':{'type':'HUMAN','actor_id':actor_id},'decided_at':eng.now()})
    if decision=='APPROVED':
        tx.transition_project_state('VOICE_LOCKED',actor_type='HUMAN',human_confirmed=True)
    tx.commit(); RuntimeStore(self.root,self.workspace).persist(eng)
    fs=eng.snapshot(); gate=eng.gates.evaluate_gate(fs,'VOICE',eng.now()).result
    return VoiceDecisionResult(self.workspace,eng.project_state,decision,ar,rc,target,gate)

VoiceRuntime.review_package=_make_review_package
VoiceRuntime.decide=_decide_voice
