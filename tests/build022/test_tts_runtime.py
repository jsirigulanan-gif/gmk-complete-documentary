from pathlib import Path
import shutil, subprocess
import pytest

from gmk_assets import MediaHandoffRuntime, VisualCoverageRuntime
from gmk_narrative import ScriptRuntime, TTSRuntime, TTSRuntimeError
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def _video(path: Path,duration: float=2.0):
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=size=320x180:rate=25:duration={duration}','-c:v','mpeg4',str(path)],check=True)


def _handoff(a,b):
    return {'batch_id':'PT_MEDIA_HANDOFF_TEST_022','items':[
        {'candidate_key':'LISA_X_DIRECT_VERIFIED','local_path':str(a),'source_url':'https://twitter.com/manfightdragon/status/1170860592233472001','acquisition_method':'AUTHORIZED_MANUAL_EXPORT','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'Lisa camera-hack source-locked media.','match_type':'DIRECT','match_reason':'Direct verified source media.'}},
        {'candidate_key':'TGA_VIDEO','local_path':str(b),'source_url':'https://www.youtube.com/watch?v=PKl5rYdwM6c','acquisition_method':'AUTHORIZED_MANUAL_EXPORT','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'TGA source-locked stage statement.','match_type':'DIRECT','match_reason':'Direct verified source media.'}}
    ]}


def _script_plan(ws):
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot(); blocks=[]
    rank={'DIRECT':0,'ATTRIBUTED':1,'QUALIFIED':2,'THEORY':3,'INTERPRETIVE':4,'UNRESOLVED':5,'PROHIBITED':6}
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type!='NARRATION_BEAT' or e.active_version is None: continue
            beat=state.objects[(oid,int(e.active_version))]; key=beat['extensions']['rough_narrative']['key']; modes=[]
            for cb in beat.get('claim_bindings',[]):
                c=state.objects[(cb['claim_ref']['id'],int(cb['claim_ref']['version']))]; modes.append(c['production_use']['language_mode'])
            mode=max(modes,key=lambda x:rank[x]) if modes else 'INTERPRETIVE'
            blocks.append({'beat_key':key,'language_mode':mode,'narration_text':f'Final narration for {key}. This sentence is intentionally complete and traceable.'})
    return {'batch_id':'PT_SCRIPT_TEST_022','language':'th-TH','blocks':blocks}


def _tts_plan(batch='PT_TTS_TEST_022'):
    return {
        'batch_id':batch,'language':'th-TH',
        'voice_profile':{
            'profile_name':'GMK Thai Documentary Voice','engine_class':'TTS',
            'delivery':{'default_style':'NEUTRAL_DOCUMENTARY','speech_rate':'NATURAL','pause_guidance':'Preserve sentence punctuation.'},
            'technical_constraints':{'sample_rate_hz':48000,'channels':1,'target_loudness_lufs':-16.0,'peak_limit_dbfs':-1.0},
        },
        'pronunciations':[
            {'term':'P.T.','normalized_key':'pt','pronunciation':{'method':'PLAIN_TEXT','value':'พี ที'}},
            {'term':'Kojima','normalized_key':'kojima','pronunciation':{'method':'PLAIN_TEXT','value':'โคจิมะ'}},
        ],
    }


def _ready(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'lisa.mp4'; b=tmp_path/'tga.mp4'; _video(a); _video(b)
    MediaHandoffRuntime(ROOT,ws).run(_handoff(a,b)); VisualCoverageRuntime(ROOT,ws).run(); ScriptRuntime(ROOT,ws).run(_script_plan(ws)); return ws


def test_tts_rejects_current_pilot_before_script_ready():
    with pytest.raises(TTSRuntimeError,match='STATE_INVALID'):
        TTSRuntime(ROOT,PILOT).run(_tts_plan())


def test_tts_compiles_all_blocks_and_transitions(tmp_path):
    ws=_ready(tmp_path); result=TTSRuntime(ROOT,ws).run(_tts_plan())
    assert result.block_count==10; assert result.gate_result in {'PASS','WARN'}; assert result.project_state=='TTS_READY'
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    blocks=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='VOICE_BLOCK' and e.active_version is not None: blocks.append(state.objects[(oid,int(e.active_version))])
    assert len(blocks)==10 and all(b['workflow_state']=='TTS_READY' for b in blocks)
    art=state.artifacts[(result.tts_script_ref['artifact_id'],int(result.tts_script_ref['version']))]
    assert art['extensions']['tts_runtime']['rendered_audio'] is False


def test_tts_rejects_invalid_pronunciation(tmp_path):
    ws=_ready(tmp_path); plan=_tts_plan(); plan['pronunciations'].append({'term':'PT','normalized_key':'pt','pronunciation':{'method':'PLAIN_TEXT','value':'พีที'}})
    with pytest.raises(TTSRuntimeError,match='DUPLICATE_KEY'): TTSRuntime(ROOT,ws).run(plan)


def test_tts_replay_is_idempotent(tmp_path):
    ws=_ready(tmp_path); plan=_tts_plan()
    first=TTSRuntime(ROOT,ws).run(plan); second=TTSRuntime(ROOT,ws).run(plan)
    assert first.project_state=='TTS_READY'; assert second.idempotent_replay is True
