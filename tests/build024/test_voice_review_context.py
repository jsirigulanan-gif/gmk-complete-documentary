from pathlib import Path
import pytest
from gmk_runtime.cold_start import ColdStartLoader
from gmk_voice import VoiceRuntime, VoiceRuntimeError
from tests.build023.test_voice_runtime import _workspace

ROOT=Path(__file__).resolve().parents[2]


def _prepared(tmp_path):
    ws,wav=_workspace(tmp_path)
    VoiceRuntime(ROOT,ws).prepare({'master_audio_path':str(wav),'timings':[{'order':1,'start_seconds':0.1,'end_seconds':1.7}]})
    return ws


def test_voice_review_package_breaks_pre_scene_deadlock(tmp_path):
    ws=_prepared(tmp_path)
    out=VoiceRuntime(ROOT,ws).review_package()
    assert out.project_state=='TTS_READY'
    assert out.gate_result=='FAIL'
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    rp=state.artifacts[(out.review_package_ref['artifact_id'],out.review_package_ref['version'])]
    assert rp['artifact_type']=='VOICE_REVIEW_PACKAGE'
    assert rp['scope']['type']=='VOICE_LOCK'
    assert 'scene_plan' not in rp and 'scene_preview' not in rp


def test_human_voice_approval_transitions_to_voice_locked(tmp_path):
    ws=_prepared(tmp_path)
    VoiceRuntime(ROOT,ws).review_package()
    out=VoiceRuntime(ROOT,ws).decide({'decision':'APPROVED','actor_id':'HUMAN_OWNER'})
    assert out.project_state=='VOICE_LOCKED'
    assert out.gate_result=='PASS'
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.engine.project_state=='VOICE_LOCKED'
    state=loaded.engine.snapshot()
    approval=state.objects[(out.approval_ref['id'],out.approval_ref['version'])]
    assert approval['actor']['type']=='HUMAN'
    assert approval['review_context']['artifact_type']=='VOICE_REVIEW_PACKAGE'


def test_rejected_voice_review_does_not_transition(tmp_path):
    ws=_prepared(tmp_path)
    out=VoiceRuntime(ROOT,ws).decide({'decision':'REJECTED','actor_id':'HUMAN_OWNER'})
    assert out.project_state=='TTS_READY'
    assert out.gate_result=='FAIL'


def test_voice_decision_requires_explicit_human_actor(tmp_path):
    ws=_prepared(tmp_path)
    with pytest.raises(VoiceRuntimeError,match='HUMAN_ACTOR_REQUIRED'):
        VoiceRuntime(ROOT,ws).decide({'decision':'APPROVED','actor_id':''})
