from pathlib import Path
import pytest
from gmk_voice import VoiceRuntime
from gmk_design import DesignRuntime, DesignRuntimeError
from gmk_runtime.cold_start import ColdStartLoader
from tests.build023.test_voice_runtime import _workspace
ROOT=Path(__file__).resolve().parents[2]

def _voice_locked(tmp_path):
    ws,wav=_workspace(tmp_path)
    v=VoiceRuntime(ROOT,ws);v.prepare({'master_audio_path':str(wav),'timings':[{'order':1,'start_seconds':0.1,'end_seconds':1.7}]});v.decide({'decision':'APPROVED','actor_id':'OWNER'})
    loaded=ColdStartLoader(ROOT,ws).load(); eng=loaded.engine; state=eng.snapshot()
    project=next(o for o in state.objects.values() if o.get('object_type')=='PROJECT')
    tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
    tx.create_artifact('NARRATIVE_SPINE',{'project_ref':{'id':project['id'],'version':project['version']},'core_question':'How does the evidence-led documentary hold together?','opening_promise':'Follow verified evidence through the story.','major_turns':['Discovery','Erasure','Afterlife']})
    tx.commit(); from gmk_runtime.persistence import RuntimeStore; RuntimeStore(ROOT,ws).persist(eng)
    return ws

def _plan():
    return {'design_intent':{'visual_thesis':'Evidence first, dread through restraint.','audience_feeling':'Curious, uneasy, oriented.','clarity_principle':'Every visual must clarify the claim or atmosphere without inventing evidence.'},'rules':[{'rule_id':'DNR_EVIDENCE_FIRST','domain':'COMPOSITION','action':'REQUIRE','statement':'Primary evidence remains visually dominant over decoration.','rationale':'Traceability and comprehension.'},{'rule_id':'DNR_MOTION_RESTRAINT','domain':'MOTION','action':'PREFER','statement':'Use motion only when it reveals structure, timing, or spatial relation.','rationale':'Avoid decorative movement.'}],'token_overrides':{'type_scale':'documentary','spacing':'restrained'},'graphic_policy':{'default_decision':'OPTIONAL','graphic_allowed_when':['Clarifies chronology or spatial relation'],'graphic_not_justified_by':['Decoration alone']},'motion_policy':{'default':'PURPOSE_REQUIRED'}}

def test_design_prepare_stops_at_human_boundary(tmp_path):
    ws=_voice_locked(tmp_path); out=DesignRuntime(ROOT,ws).prepare(_plan())
    assert out.project_state=='VOICE_LOCKED'; assert out.gate_result=='FAIL'; assert out.rule_count==2

def test_design_review_package_breaks_pre_scene_deadlock(tmp_path):
    ws=_voice_locked(tmp_path); r=DesignRuntime(ROOT,ws);r.prepare(_plan()); out=r.review_package()
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot(); rp=state.artifacts[(out.review_package_ref['artifact_id'],out.review_package_ref['version'])]
    assert rp['artifact_type']=='DESIGN_DNA_REVIEW_PACKAGE'; assert 'scene_plan' not in rp and 'scene_preview' not in rp

def test_human_design_approval_transitions(tmp_path):
    ws=_voice_locked(tmp_path); r=DesignRuntime(ROOT,ws);r.prepare(_plan()); out=r.decide({'decision':'APPROVED','actor_id':'OWNER'})
    assert out.project_state=='DESIGN_DNA_APPROVED'; assert out.gate_result=='PASS'

def test_rejected_design_review_does_not_transition(tmp_path):
    ws=_voice_locked(tmp_path); r=DesignRuntime(ROOT,ws);r.prepare(_plan()); out=r.decide({'decision':'REJECTED','actor_id':'OWNER'})
    assert out.project_state=='VOICE_LOCKED'; assert out.gate_result=='FAIL'

def test_design_decision_requires_human_actor(tmp_path):
    ws=_voice_locked(tmp_path); r=DesignRuntime(ROOT,ws);r.prepare(_plan())
    with pytest.raises(DesignRuntimeError,match='HUMAN_ACTOR_REQUIRED'): r.decide({'decision':'APPROVED','actor_id':''})
