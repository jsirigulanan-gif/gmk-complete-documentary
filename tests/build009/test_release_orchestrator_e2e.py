import pytest
from gmk_orchestrator import GMKOrchestrator
from gmk_render import RenderProduct
from gmk_operations import OperationExecutionResult
from gmk_state.errors import StateEngineError
from gmk_runtime import RuntimeStore, ColdStartLoader
from tests.build009.conftest import Clock

class FinalAdapter:
    def render(self,payload,snapshot,*,attempt):
        return RenderProduct('gmk://renders/project-master.mp4',b'project-master-v1',technical={'width':3840,'height':2160,'duration_seconds':5.0,'codec':'h264','audio_present':True})

def publisher(operation):
    return OperationExecutionResult('SUCCEEDED','published',{'remote_id':'synthetic-release-1'})

def advance_preproduction(orch):
    # AI/AUTO transitions up to TTS_READY.
    for expected in ['RESEARCH_INTAKE','RESEARCH_AUDITED','ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY','ASSET_RECON','ASSET_CATALOG_READY','VISUAL_COVERAGE_READY','SCRIPT_READY','TTS_READY']:
        orch.advance(actor_type='SYSTEM'); assert orch.engine.project_state==expected
    # Human approval boundaries.
    orch.advance(actor_type='HUMAN',human_confirmed=True); assert orch.engine.project_state=='VOICE_LOCKED'
    orch.advance(actor_type='HUMAN',human_confirmed=True); assert orch.engine.project_state=='DESIGN_DNA_APPROVED'
    for expected in ['SCENE_PLAN_READY','SHOT_PLAN_READY','HTML_REVIEW']:
        orch.advance(actor_type='SYSTEM'); assert orch.engine.project_state==expected
    orch.advance(actor_type='HUMAN',human_confirmed=True); assert orch.engine.project_state=='HTML_APPROVED'
    orch.advance(actor_type='HUMAN',human_confirmed=True); assert orch.engine.project_state=='PRODUCTION_RENDER'

def test_end_to_end_orchestrator_reaches_project_completed(engine,full_ready,root,tmp_path):
    orch=GMKOrchestrator(engine)
    advance_preproduction(orch)

    # Final project master is rendered only from the exact PROJECT lock.
    job=orch.render.queue_final(production_lock_ref=full_ready['project_lock'],scope_type='PROJECT',scope_target=full_ready['project'])
    rendered=orch.render.execute(job,FinalAdapter())
    assert rendered['failed'] is False

    shotqa=orch.qa.evaluate(report_type='SHOT_QA',scope=full_ready['shot'],observed_artifact=rendered['output_ref'],findings=[])
    sceneqa=orch.qa.evaluate(report_type='SCENE_QA',scope=full_ready['scene'],observed_artifact=rendered['output_ref'],findings=[])
    fullqa=orch.qa.evaluate_full_film(production_lock=full_ready['project_lock'],master_output=rendered['output_ref'])
    assert shotqa['result']==sceneqa['result']==fullqa['result']=='PASS'

    orch.advance(actor_type='SYSTEM'); assert engine.project_state=='SHOT_QA_PASSED'
    orch.advance(actor_type='SYSTEM'); assert engine.project_state=='SCENE_QA_PASSED'
    orch.advance(actor_type='SYSTEM'); assert engine.project_state=='FULL_FILM_QA_PASSED'

    candidate=orch.release.prepare_release(project_lock_ref=full_ready['project_lock'],master_output_ref=rendered['output_ref'],full_film_qa_ref=fullqa['report_ref'],metadata={'title':'Synthetic GMK Integration Release','description':'End-to-end runtime smoke test.'})
    assert candidate['delivery_qa']['id'].startswith('QAR_')
    orch.advance(actor_type='HUMAN',human_confirmed=True); assert engine.project_state=='DELIVERY_READY'

    published=orch.release.publish(candidate,executor=publisher,release_label='v1',human_confirmed=True)
    completed=orch.release.finalize_project(published.release_ref,important_artifact_refs=[fullqa['package_ref'],candidate['delivery_package']])
    assert completed['project_state']=='PROJECT_COMPLETED'

    state=engine.snapshot(); release=state.objects[(published.release_ref['id'],published.release_ref['version'])]
    assert release['state']=='RELEASED'
    manifest=orch.release.checkpoints.builder.build(state,engine.gates)
    assert manifest['current']['current_release']==published.release_ref
    assert manifest['project_state']['current']=='PROJECT_COMPLETED'

    # Persist and cold-start the completed project; released truth and completion survive restart.
    RuntimeStore(root,tmp_path).persist(engine)
    cold=ColdStartLoader(root,tmp_path).load(clock=Clock())
    assert cold.engine.project_state=='PROJECT_COMPLETED'
    assert cold.manifest['current']['current_release']==published.release_ref

    # Frozen Release truth cannot be revised in place.
    with pytest.raises(StateEngineError) as exc:
        tx=engine.begin(); tx.create_version(published.release_ref['id'],base_version=published.release_ref['version'],patch={'release_label':'mutated'})
    assert exc.value.code=='RELEASED_OBJECT_MUTATION_FORBIDDEN'


def test_project_lock_aggregates_scene_lock_without_live_reresolution(engine,full_ready):
    state=engine.snapshot(); lock=state.artifacts[(full_ready['project_lock']['artifact_id'],full_ready['project_lock']['version'])]
    assert lock['scope']['type']=='PROJECT'
    assert lock['scene_locks']==[full_ready['scene_lock']]
    assert full_ready['shot'] in lock['shots']
    # Creating a newer HEAD shot does not rewrite the frozen project lock.
    tx=engine.begin(); v2=tx.create_version(full_ready['shot']['id'],base_version=1,patch={'viewer_takeaway':'Experimental HEAD only.'}); tx.commit()
    lock_after=engine.snapshot().artifacts[(full_ready['project_lock']['artifact_id'],full_ready['project_lock']['version'])]
    assert lock_after['shots']==lock['shots']
    assert v2 not in lock_after['shots']


def test_delivery_profile_failure_blocks_release(engine,full_ready):
    orch=GMKOrchestrator(engine)
    advance_preproduction(orch)
    class BadAdapter:
        def render(self,payload,snapshot,*,attempt):
            return RenderProduct('gmk://renders/bad.mp4',b'bad',technical={'width':1920,'height':1080,'duration_seconds':5.0,'codec':'h264'})
    job=orch.render.queue_final(production_lock_ref=full_ready['project_lock'],scope_type='PROJECT',scope_target=full_ready['project'])
    rendered=orch.render.execute(job,BadAdapter())
    fullqa=orch.qa.evaluate_full_film(production_lock=full_ready['project_lock'],master_output=rendered['output_ref'])
    with pytest.raises(StateEngineError) as exc:
        orch.release.prepare_release(project_lock_ref=full_ready['project_lock'],master_output_ref=rendered['output_ref'],full_film_qa_ref=fullqa['report_ref'],metadata={'title':'x','description':'y'})
    assert exc.value.code=='RELEASE_DELIVERY_QA_INVALID'
