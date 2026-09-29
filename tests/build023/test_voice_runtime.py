from pathlib import Path
import subprocess, pytest
from gmk_state import StateEngine
from gmk_runtime.persistence import RuntimeStore
from gmk_runtime.cold_start import ColdStartLoader
from gmk_voice import VoiceRuntime, VoiceRuntimeError

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'

def _workspace(tmp_path):
    ws=tmp_path/'WS'; e=StateEngine(ROOT,project_state='TTS_READY')
    tx=e.begin()
    p=tx.create_object('PROJECT',{'title':'Voice runtime fixture','language':{'narration':'th-TH'},'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':1,'max':2}}})
    act=tx.create_object('ACT',{'project_ref':p,'order':1,'narrative':{'job':'Test','audience_question':'Q','knowledge_before':'A','knowledge_after':'B'}})
    sc=tx.create_object('SCENE',{'act_ref':act,'order':1,'narrative':{'purpose':'Test','viewer_question_entering':'Q','viewer_understanding_leaving':'A'},'dynamics':{'role':'SETUP','energy':'CALM'}})
    beat=tx.create_object('NARRATION_BEAT',{'scene_ref':sc,'order':1,'beat_type':'TRANSITION','idea':{'summary':'Test voice'},'viewer_takeaway':'Voice works.','claim_bindings':[],'workflow_state':'NARRATION_FINAL','narration':{'text':'Test voice line.','language_mode':'INTERPRETIVE'}})
    vp=tx.create_object('VOICE_PROFILE',{'profile_name':'Fixture','engine_class':'TTS','language':'th-TH','delivery':{'default_style':'NEUTRAL_DOCUMENTARY','speech_rate':'NATURAL'},'technical_constraints':{'sample_rate_hz':48000,'channels':1}})
    decision=e.semantic.decision_hash(tx.staged.objects[(beat['id'],beat['version'])])
    script=tx.create_artifact('VOICEOVER_SCRIPT_FINAL',{'project_ref':p,'language':'th-TH','blocks':[{'beat_ref':beat,'narration_text':'Test voice line.','decision_sha256':decision}]})
    pd=tx.create_artifact('PRONUNCIATION_DICTIONARY',{'language':'th-TH','entries':[]})
    tts=tx.create_artifact('TTS_READY_SCRIPT',{'source_script':script,'pronunciation_dictionary':pd,'voice_profile_ref':vp,'blocks':[{'order':1,'beat_ref':beat,'text':'Test voice line.','delivery':{'style':'NEUTRAL_DOCUMENTARY','speech_rate':'NATURAL'}}]})
    tx.create_object('VOICE_BLOCK',{'voice_profile_ref':vp,'tts_script_ref':tts,'source_beat_refs':[beat],'order':1,'delivery':{},'workflow_state':'TTS_READY'})
    tx.commit(); RuntimeStore(ROOT,ws).persist(e)
    wav=tmp_path/'master.wav'; subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-ac','1',str(wav)],check=True)
    return ws,wav

def test_voice_rejects_current_pilot_before_tts_ready():
    with pytest.raises(VoiceRuntimeError,match='STATE_INVALID'): VoiceRuntime(ROOT,PILOT).prepare({'master_audio_path':'x','timings':[]})

def test_voice_prepare_creates_verified_master_and_stops_at_human_boundary(tmp_path):
    ws,wav=_workspace(tmp_path); out=VoiceRuntime(ROOT,ws).prepare({'master_audio_path':str(wav),'timings':[{'order':1,'start_seconds':0.1,'end_seconds':1.7}]})
    assert out.project_state=='TTS_READY' and out.block_count==1 and out.approval_ready is False
    loaded=ColdStartLoader(ROOT,ws).load(); state=loaded.engine.snapshot(); mv=state.artifacts[(out.master_voice_ref['artifact_id'],out.master_voice_ref['version'])]
    assert mv['audio']['duration_seconds']>1.9 and len(mv['audio']['sha256'])==64
    lock=state.artifacts[(out.voice_lock_ref['artifact_id'],out.voice_lock_ref['version'])]
    assert lock['extensions']['voice_runtime']['human_approval_required'] is True
    assert loaded.engine.gates.evaluate_gate(state,'VOICE',loaded.engine.now()).result=='FAIL'

def test_voice_prepare_rejects_invalid_timing(tmp_path):
    ws,wav=_workspace(tmp_path)
    with pytest.raises(VoiceRuntimeError,match='TIMING_INVALID'): VoiceRuntime(ROOT,ws).prepare({'master_audio_path':str(wav),'timings':[{'order':1,'start_seconds':0.1,'end_seconds':9.0}]})
