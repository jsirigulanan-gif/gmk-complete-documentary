import pytest
from gmk_recovery import CheckpointRuntime
from gmk_incident.runtime import IncidentRuntime
from gmk_state import StateEngineError


def test_checkpoint_captures_manifest_and_registry_bundle(engine,project):
    rt=CheckpointRuntime(engine)
    cp=rt.create_checkpoint(reason='Baseline')
    verified=rt.verify_checkpoint(cp)
    assert verified['integrity']=='PASS'
    obj=engine.resolver().resolve(cp['id'],mode='HEAD')
    assert obj['checkpoint_class']=='PROJECT_STATE'
    assert obj['integrity_summary']=='PASS'
    assert len(obj['registry_snapshots'])==1


def test_restore_repoints_active_without_rewinding_head_or_deleting_history(engine,project):
    rt=CheckpointRuntime(engine)
    cp=rt.create_checkpoint(reason='Before experimental revision')
    tx=engine.begin();v2=tx.create_version(project['id'],base_version=1,patch={'working_title':'Experimental'});tx.promote_active_version(project['id'],v2['version']);tx.commit()
    assert engine.resolver().resolve(project['id'],mode='HEAD')['version']==2
    assert engine.resolver().resolve(project['id'],mode='ACTIVE')['version']==2
    plan=rt.build_restore_plan(cp)
    before=engine.manifest_version
    out=rt.restore(plan,human_confirmed=True)
    assert out['manifest_version']>before
    assert engine.resolver().resolve(project['id'],mode='HEAD')['version']==2
    assert engine.resolver().resolve(project['id'],mode='ACTIVE')['version']==1
    assert engine.snapshot().objects[(project['id'],2)]['working_title']=='Experimental'


def test_restore_requires_human_confirmation(engine,project):
    rt=CheckpointRuntime(engine);cp=rt.create_checkpoint(reason='Baseline');plan=rt.build_restore_plan(cp)
    with pytest.raises(StateEngineError) as exc:rt.restore(plan,human_confirmed=False)
    assert exc.value.code=='RESTORE_HUMAN_CONFIRMATION_REQUIRED'


def test_restore_does_not_silently_remove_incident_truth(engine,project):
    rt=CheckpointRuntime(engine);cp=rt.create_checkpoint(reason='Before incident')
    inc=IncidentRuntime(engine).open(incident_type='PROVIDER_OUTAGE',severity='MAJOR',summary='Outage',affected_scope={'type':'SYSTEM'},containment_actions=['BLOCK_EXTERNAL_OPERATIONS'])
    assert engine.safety_mode=='SAFE_MODE'
    plan=rt.build_restore_plan(cp)
    rt.restore(plan,human_confirmed=True)
    assert engine.resolver().resolve(inc['id'],mode='ACTIVE') is not None
    assert engine.safety_mode=='SAFE_MODE'


def test_restore_artifact_current_by_creating_new_head_copy(engine,project):
    rt=CheckpointRuntime(engine)
    tx=engine.begin();a1=tx.create_artifact('NARRATIVE_SPINE',{
        'project_ref':project,'core_question':'Original?','opening_promise':'Promise',
        'central_mystery':'Original mystery','major_turns':['Turn'],'final_answer':'Answer','closing_thought':'Close'
    },origin_refs=[project]);tx.commit()
    cp=rt.create_checkpoint(reason='Narrative baseline')
    tx=engine.begin();a2=tx.create_artifact_version(a1['artifact_id'],base_version=1,payload_patch={'central_mystery':'Changed mystery'});tx.commit()
    assert engine.snapshot().artifacts[(a1['artifact_id'],2)]['central_mystery']=='Changed mystery'
    plan=rt.build_restore_plan(cp);out=rt.restore(plan,human_confirmed=True)
    head=engine.artifact_registry_snapshot()['entries'][a1['artifact_id']]['head_version']
    assert head==3
    restored=engine.snapshot().artifacts[(a1['artifact_id'],3)]
    assert restored['central_mystery']=='Original mystery'
    assert out['artifact_copies'][0]['restored_as']['version']==3
