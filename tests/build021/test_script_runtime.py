from pathlib import Path
import shutil, subprocess
import pytest

from gmk_assets import MediaHandoffRuntime, VisualCoverageRuntime
from gmk_narrative import ScriptRuntime, ScriptRuntimeError
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def _video(path: Path,duration: float=2.0):
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=size=320x180:rate=25:duration={duration}','-c:v','mpeg4',str(path)],check=True)


def _handoff(a,b):
    return {'batch_id':'PT_MEDIA_HANDOFF_TEST_021','items':[
        {'candidate_key':'LISA_X_DIRECT_VERIFIED','local_path':str(a),'source_url':'https://twitter.com/manfightdragon/status/1170860592233472001','acquisition_method':'AUTHORIZED_MANUAL_EXPORT','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'Lisa camera-hack source-locked media.','match_type':'DIRECT','match_reason':'Direct verified source media.'}},
        {'candidate_key':'TGA_VIDEO','local_path':str(b),'source_url':'https://www.youtube.com/watch?v=PKl5rYdwM6c','acquisition_method':'AUTHORIZED_MANUAL_EXPORT','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'TGA source-locked stage statement.','match_type':'DIRECT','match_reason':'Direct verified source media.'}}
    ]}


def _ready(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'lisa.mp4'; b=tmp_path/'tga.mp4'; _video(a); _video(b)
    MediaHandoffRuntime(ROOT,ws).run(_handoff(a,b)); VisualCoverageRuntime(ROOT,ws).run(); return ws


def _plan(ws,batch='PT_SCRIPT_TEST_021'):
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot(); blocks=[]
    rank={'DIRECT':0,'ATTRIBUTED':1,'QUALIFIED':2,'THEORY':3,'INTERPRETIVE':4,'UNRESOLVED':5,'PROHIBITED':6}
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type!='NARRATION_BEAT' or e.active_version is None: continue
            beat=state.objects[(oid,int(e.active_version))]
            key=beat['extensions']['rough_narrative']['key']; modes=[]
            for cb in beat.get('claim_bindings',[]):
                c=state.objects[(cb['claim_ref']['id'],int(cb['claim_ref']['version']))]
                modes.append(c['production_use']['language_mode'])
            mode=max(modes,key=lambda x:rank[x]) if modes else 'INTERPRETIVE'
            blocks.append({'beat_key':key,'language_mode':mode,'narration_text':f'Final narration for {key}. This sentence is intentionally complete and traceable.'})
    return {'batch_id':batch,'language':'th-TH','blocks':blocks}


def test_script_rejects_current_pilot_before_visual_coverage():
    with pytest.raises(ScriptRuntimeError,match='STATE_INVALID'):
        ScriptRuntime(ROOT,PILOT).run({'language':'th-TH','blocks':[{'beat_key':'X','language_mode':'DIRECT','narration_text':'Complete text.'}]})


def test_script_compiles_all_beats_and_transitions(tmp_path):
    ws=_ready(tmp_path); result=ScriptRuntime(ROOT,ws).run(_plan(ws))
    assert result.block_count==10; assert result.gate_result in {'PASS','WARN'}; assert result.project_state=='SCRIPT_READY'
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    beats=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='NARRATION_BEAT' and e.active_version is not None: beats.append(state.objects[(oid,int(e.active_version))])
    assert len(beats)==10 and all(b['workflow_state']=='NARRATION_FINAL' and b.get('narration') for b in beats)


def test_script_requires_exact_one_to_one_beat_coverage(tmp_path):
    ws=_ready(tmp_path); plan=_plan(ws); plan['blocks']=plan['blocks'][:-1]
    with pytest.raises(ScriptRuntimeError,match='BEAT_COVERAGE_MISMATCH'): ScriptRuntime(ROOT,ws).run(plan)


def test_script_replay_is_idempotent(tmp_path):
    ws=_ready(tmp_path); plan=_plan(ws)
    first=ScriptRuntime(ROOT,ws).run(plan); second=ScriptRuntime(ROOT,ws).run(plan)
    assert first.project_state=='SCRIPT_READY'; assert second.idempotent_replay is True
