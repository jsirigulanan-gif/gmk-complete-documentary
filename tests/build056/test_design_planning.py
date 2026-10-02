import pytest

from gmk_projects.design_planning import (inspect_design, prepare_design, decide_design, prepare_plans,
                                         reopen_design, design_binding_status, plan_binding_status, _tag, _file)
from gmk_projects.edit import EditError
from gmk_projects.final_production import reopen_final, _heads
from gmk_projects.production import ProductionProject
from gmk_projects.production_bridge import _active
from tests.build054.test_coverage import covered, assess
from tests.build053.test_media_bridge import footage
from tests.build055.test_final_production import prepare, decide


def action(p, fn, **kwargs):
    preview = inspect_design(p)
    return fn(p, expected_edit_sha256=preview['edit_sha256'], expected_manifest_sha256=preview['manifest_sha256'], **kwargs)


@pytest.fixture
def locked(covered):
    p,session,scene,shot,voice=covered
    edit=session.load();edit['music_omitted']=True;edit['scenes'][0]['show_title']=True
    session.save(edit,expected_revision=edit['revision'])
    assess(p,complete_selection=True,stop_reason='Reviewed synthetic selected library.')
    prepare(p);decide(p)
    return covered


def test_actual_design_preview_human_decision_and_exact_cut_plan(locked):
    p,session,scene,shot,voice=locked
    before=ProductionProject(p)._load().manifest_sha256
    assert inspect_design(p)['ready'] and ProductionProject(p)._load().manifest_sha256==before
    prepared=action(p,prepare_design)
    assert prepared['production_state']=='VOICE_LOCKED' and prepared['design_binding']['current']
    assert not prepared['design_binding']['approved']
    image=_file(ProductionProject(p),prepared['design_binding']['preview'])
    assert image.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
    sha=ProductionProject(p)._load().manifest_sha256
    assert action(p,prepare_design)['idempotent_replay'] and ProductionProject(p)._load().manifest_sha256==sha
    with pytest.raises(EditError):action(p,prepare_plans)
    accepted=action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer')
    assert accepted['production_state']=='DESIGN_DNA_APPROVED'
    status=ProductionProject(p).status();assert status['final_binding']['voice_locked'] and status['media_binding']['current']
    from gmk_design import DesignRuntime
    loaded=ProductionProject(p)._load();sha=loaded.manifest_sha256
    review=DesignRuntime(loaded.engine.root,ProductionProject(p).workspace).review_package()
    assert review.review_package_ref==accepted['design_binding']['review_ref']
    assert ProductionProject(p)._load().manifest_sha256==sha
    planned=action(p,prepare_plans)
    assert planned['production_state']=='SHOT_PLAN_READY' and planned['plan_binding']['shot_plan_ready']
    loaded=ProductionProject(p)._load();state=loaded.engine.snapshot();live=_active(state)
    shots=[o for o in live.values() if o['object_type']=='SHOT']
    assert len(shots)==1 and shots[0]['visual_strategy']=='CONTEXTUAL_BROLL'
    assert shots[0]['timing']['start']['seconds']==0 and shots[0]['timing']['end']['seconds']==.8
    assert _tag(shots[0])['used_source_frames']==24 and _tag(shots[0])['rights']=='UNKNOWN'
    assert len(shots[0]['layer_refs'])==2
    assert live[shots[0]['cue_refs'][0]['id']]['target_layer_refs']==shots[0]['layer_refs']
    assert loaded.dependency_summary['changed_objects']==0
    assert action(p,prepare_plans)['idempotent_replay']
    assert not ProductionProject(p).status()['documentary_completed']


def test_rejection_reopen_and_style_edit_preserve_voice_without_old_design_approval(locked):
    p,session,scene,shot,voice=locked
    old=action(p,prepare_design);ref=old['design_binding']['design_ref'];image=_file(ProductionProject(p),old['design_binding']['preview'])
    rejected=action(p,decide_design,decision='REJECTED',actor_id='Synthetic designer')
    assert rejected['design_binding']['decision']=='REJECTED'
    with pytest.raises(EditError,match='มีผลตรวจแล้ว'):action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer')
    with pytest.raises(EditError):action(p,prepare_plans)
    reopened=action(p,reopen_design)
    assert reopened['production_state']=='VOICE_LOCKED' and image.is_file()
    assert ProductionProject(p).status()['final_binding']['voice_locked']
    edit=session.load();edit['music_gain']=.2;session.save(edit,expected_revision=edit['revision'])
    prepared=action(p,prepare_design)
    assert prepared['design_binding']['design_ref']['id']==ref['id'] and prepared['design_binding']['design_ref']['version']>ref['version']
    assert prepared['design_binding']['decision'] is None
    action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer');action(p,prepare_plans)
    edit=session.load();edit['music_gain']=.3;session.save(edit,expected_revision=edit['revision'])
    status=ProductionProject(p).status()
    assert status['final_binding']['voice_locked'] and not status['design_binding']['current'] and not status['plan_binding']['current']
    action(p,reopen_design)
    assert not any(o['object_type']=='APPROVAL' and o['approval_class']=='DESIGN_DNA' for o in _active(ProductionProject(p)._load().engine.snapshot()).values())


def test_preview_bytes_stale_tokens_and_foreign_records_cannot_be_approved(locked):
    from gmk_runtime.persistence import RuntimeStore
    p,session,scene,shot,voice=locked
    preview=action(p,prepare_design);before=ProductionProject(p)._load().manifest_sha256
    path=_file(ProductionProject(p),preview['design_binding']['preview']);original=path.read_bytes();path.write_bytes(b'Changed preview')
    assert not ProductionProject(p).status()['design_binding']['current']
    with pytest.raises(EditError):action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer')
    assert ProductionProject(p)._load().manifest_sha256==before
    path.write_bytes(original)
    edit=session.load();edit['width']=640;edit['height']=360;session.save(edit,expected_revision=edit['revision'])
    with pytest.raises(EditError,match='เปลี่ยนหลังเปิดตรวจ'):
        decide_design(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'],decision='APPROVED',actor_id='Synthetic designer')
    edit=session.load();edit['width']=1280;edit['height']=720;session.save(edit,expected_revision=edit['revision'])
    loaded=ProductionProject(p)._load();token=_heads(loaded.engine.snapshot(),'EFFECTIVE_DESIGN_TOKENS')[0]
    tx=loaded.engine.begin();tx.create_artifact('EFFECTIVE_DESIGN_TOKENS',{'base_design':token['base_design'],'design_dna_ref':token['design_dna_ref'],'tokens':{}});tx.commit()
    RuntimeStore(loaded.engine.root,ProductionProject(p).workspace).persist(loaded.engine)
    before=ProductionProject(p)._load().manifest_sha256
    assert not inspect_design(p)['ready']
    assert not ProductionProject(p).status()['design_binding']['current']
    with pytest.raises(EditError):action(p,prepare_plans)
    with pytest.raises(EditError):action(p,reopen_design)
    assert ProductionProject(p)._load().manifest_sha256==before


def test_failed_staging_and_explicit_plan_revisions_retain_identities(locked,monkeypatch):
    from gmk_projects import design_planning
    p,session,scene,shot,voice=locked
    action(p,prepare_design);action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer')
    before=ProductionProject(p)._load().manifest_sha256;edit=session.load();original=design_planning._object
    def fail(tx,kind,*args):
        if kind=='SHOT':raise EditError('Simulated shot staging failure')
        return original(tx,kind,*args)
    monkeypatch.setattr(design_planning,'_object',fail)
    with pytest.raises(EditError,match='Simulated'):action(p,prepare_plans)
    assert ProductionProject(p)._load().manifest_sha256==before and session.load()==edit
    assert not _heads(ProductionProject(p)._load().engine.snapshot(),'SCENE_PLAN')
    monkeypatch.setattr(design_planning,'_object',original);action(p,prepare_plans)
    state=ProductionProject(p)._load().engine.snapshot()
    identities={o['object_type']:o['id'] for o in _active(state).values() if o['object_type'] in ('SHOT','DESIGN_DNA')}
    action(p,reopen_design);action(p,prepare_design);action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer');action(p,prepare_plans)
    loaded=ProductionProject(p)._load()
    assert all(o['id']==identities[o['object_type']] for o in _active(loaded.engine.snapshot()).values() if o['object_type'] in identities)
    assert loaded.dependency_summary['changed_objects']==0
    preview=inspect_design(p)
    reopen_final(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])
    assert ProductionProject(p).status()['production_state']=='ASSET_RECON'
    assert not ProductionProject(p).status()['final_binding']['voice_locked']
    assert not any(o['object_type'] in ('SHOT','LAYER','CUE','DESIGN_DNA') for o in _active(ProductionProject(p)._load().engine.snapshot()).values())


def test_multiple_selected_cuts_and_explicit_hold_follow_frame_clock(covered):
    from tests.build053.test_media_bridge import register,rereview
    p,session,scene,shot,voice=covered
    edit=session.load();video=p.root/edit['scenes'][0]['shots'][0]['path']
    session.trim_shot(scene,shot,.1,.4,expected_revision=edit['revision'])
    edit=session.add_shot(scene,video,.5,.9,expected_revision=session.load()['revision'])
    edit['fps']=25;edit['music_omitted']=True;edit['scenes'][0]['show_title']=True;edit['scenes'][0]['hold_last_frame']=True
    session.save(edit,expected_revision=edit['revision'])
    for cut in session.load()['scenes'][0]['shots']:rereview(p,session,scene,cut['id'])
    register(p);assess(p,complete_selection=True,stop_reason='Selected synthetic ranges with explicit final-frame hold.')
    prepare(p);decide(p);action(p,prepare_design);action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer');planned=action(p,prepare_plans)
    assert planned['plan_binding']['shot_count']==2
    live=_active(ProductionProject(p)._load().engine.snapshot());shots=sorted((o for o in live.values() if o['object_type']=='SHOT'),key=lambda o:o['order'])
    assert [(s['timing']['start']['seconds'],s['timing']['end']['seconds']) for s in shots]==[(0,.28),(.28,.8)]
    assert [_tag(s)['used_source_frames'] for s in shots]==[7,10]
    assert [_tag(s)['hold_frames'] for s in shots]==[0,3]
    assert [live[s['cue_refs'][0]['id']]['semantic_trigger']['offset_seconds'] for s in shots]==[0,.28]
    assert len(shots[0]['layer_refs'])==2 and len(shots[1]['layer_refs'])==1


def test_design_preview_in_flight_edit_does_not_publish(locked,monkeypatch):
    from gmk_projects import design_planning
    p,session,scene,shot,voice=locked
    before=ProductionProject(p)._load().manifest_sha256;original=design_planning._run
    def change(args,**kwargs):
        result=original(args,**kwargs)
        edit=session.load();edit['music_gain']=.21;session.save(edit,expected_revision=edit['revision'])
        return result
    monkeypatch.setattr(design_planning,'_run',change)
    with pytest.raises(EditError,match='เปลี่ยนหลังเปิดตรวจ'):action(p,prepare_design)
    assert ProductionProject(p)._load().manifest_sha256==before
    assert not _heads(ProductionProject(p)._load().engine.snapshot(),'EFFECTIVE_DESIGN_TOKENS')


def test_superseded_voice_review_context_invalidates_design_and_plans(locked):
    from gmk_runtime.persistence import RuntimeStore
    p,session,scene,shot,voice=locked
    action(p,prepare_design);action(p,decide_design,decision='APPROVED',actor_id='Synthetic designer');action(p,prepare_plans)
    loaded=ProductionProject(p)._load();review=_heads(loaded.engine.snapshot(),'VOICE_REVIEW_PACKAGE')[0]
    tx=loaded.engine.begin();tx.create_artifact_version(review['artifact_id'],base_version=review['version'],
        payload_patch={'extensions':{'synthetic_review_revision':True}});tx.commit()
    RuntimeStore(loaded.engine.root,ProductionProject(p).workspace).persist(loaded.engine)
    before=ProductionProject(p)._load().manifest_sha256;status=ProductionProject(p).status()
    assert not status['final_binding']['voice_locked'] and not status['design_binding']['current'] and not status['plan_binding']['current']
    with pytest.raises(EditError):action(p,prepare_plans)
    assert ProductionProject(p)._load().manifest_sha256==before
