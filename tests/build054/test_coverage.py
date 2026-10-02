import subprocess

import pytest

from gmk_projects.coverage import inspect_coverage, record_coverage
from gmk_projects.edit import EditError
from gmk_projects.media_review import review_voice
from gmk_projects.production import ProductionProject
from gmk_projects.production_bridge import _active
from tests.build053.test_media_bridge import footage, register, rereview


@pytest.fixture
def covered(footage):
    p,session,scene,shot,video=footage
    voice=video.parent/'speech.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=duration=0.8:sample_rate=48000',str(voice)],check=True,capture_output=True)
    session.attach_voice(scene,voice,expected_revision=session.load()['revision'])
    review_voice(p,scene,expected_revision=session.load()['revision']); register(p)
    return p,session,scene,shot,voice


def assess(p,**kwargs):
    preview=inspect_coverage(p)
    return record_coverage(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'],**kwargs)


def test_exact_coverage_records_qa_and_explicit_library_stop_advances_existing_gates(covered):
    p,session,scene,shot,voice=covered
    before=ProductionProject(p)._load().manifest_sha256
    preview=inspect_coverage(p)
    assert preview['ready'] and ProductionProject(p)._load().manifest_sha256==before
    assert preview['scenes'][0]['required_seconds']==pytest.approx(.8)
    assert preview['scenes'][0]['unique_visual_seconds']==pytest.approx(.8)
    result=assess(p)
    assert result['binding']['ready'] and result['production_state']=='ASSET_RECON'
    assert not result['binding']['selection_closed'] and not result['rights_cleared']
    sha=ProductionProject(p)._load().manifest_sha256
    assert assess(p)['idempotent_replay'] and ProductionProject(p)._load().manifest_sha256==sha
    closed=assess(p,complete_selection=True,stop_reason='Use these inspected project-library pictures for this fixture.')
    assert closed['production_state']=='VISUAL_COVERAGE_READY' and closed['binding']['selection_closed']
    assert ProductionProject(p).status()['story_binding']['current'] and ProductionProject(p).status()['media_binding']['current']
    loaded=ProductionProject(p)._load();live=_active(loaded.engine.snapshot())
    certificate=next(o for o in live.values() if o['object_type']=='QA_REPORT' and o['report_type']=='SEARCH_COMPLETION_CERTIFICATE')
    decision=certificate['extensions']['project_library_stop']['decisions'][0]
    assert decision['stop_reason']=='HUMAN_STOP_WITH_REASON' and decision['scope']=='HUMAN_REVIEWED_PROJECT_LIBRARY'
    assert decision['viable_candidate_refs']==[]
    assert loaded.dependency_summary['changed_objects']==0 and not closed['documentary_completed']
    from gmk_assets import VisualCoverageRuntime
    core=VisualCoverageRuntime(loaded.engine.root,ProductionProject(p).workspace).run()
    assert core.idempotent_replay and core.covered_beats==core.total_beats==1
    assert core.verified_segments==1
    sha=loaded.manifest_sha256
    assert assess(p,complete_selection=True,stop_reason='Use these inspected project-library pictures for this fixture.')['idempotent_replay']
    assert ProductionProject(p)._load().manifest_sha256==sha


def test_context_only_and_missing_audio_cannot_be_certified(covered):
    p,session,scene,shot,voice=covered
    rereview(p,session,scene,shot,'CONTEXT');register(p)
    preview=inspect_coverage(p)
    assert preview['can_record'] and not preview['ready'] and preview['scenes'][0]['semantic']=='UNRESOLVED'
    with pytest.raises(EditError,match='ยังหยุดค้น'): assess(p,complete_selection=True,stop_reason='Stop despite the visual gap')
    failed=assess(p)
    assert failed['binding']['current'] and failed['binding']['result']=='FAIL'
    assert failed['production_state']=='ASSET_RECON'
    assert any(o['object_type']=='QA_ISSUE' for o in _active(ProductionProject(p)._load().engine.snapshot()).values())
    (p.root/session.load()['scenes'][0]['voice']['path']).unlink()
    assert not ProductionProject(p).status()['coverage_binding']['current']
    assert any(i['code']=='MEASURED_VOICE_REQUIRED' for i in inspect_coverage(p)['issues'])


def test_trim_rejects_stale_preview_and_new_review_reopens_closed_coverage(covered):
    p,session,scene,shot,_=covered
    assess(p,complete_selection=True,stop_reason='Reviewed fixture selection is sufficient.')
    preview=inspect_coverage(p); before=ProductionProject(p)._load().manifest_sha256
    session.trim_shot(scene,shot,.2,1.4,expected_revision=session.load()['revision'])
    assert not ProductionProject(p).status()['coverage_binding']['current']
    with pytest.raises(EditError,match='เปลี่ยนหลังเปิดตรวจ'):
        record_coverage(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])
    assert ProductionProject(p)._load().manifest_sha256==before
    rereview(p,session,scene,shot); register(p)
    status=ProductionProject(p).status()
    assert status['production_state']=='ASSET_RECON' and not status['coverage_binding']['current']
    assert not any(o['object_type']=='QA_REPORT' and o.get('extensions',{}).get('project_coverage')
                   for o in _active(ProductionProject(p)._load().engine.snapshot()).values())
    assert assess(p)['binding']['ready']


def test_failed_coverage_can_be_retested_after_picture_repair_without_old_blockers(covered):
    p,session,scene,shot,_=covered
    rereview(p,session,scene,shot,'CONTEXT');register(p);failed=assess(p)
    old=failed['binding']['report_ref']
    rereview(p,session,scene,shot);register(p)
    result=assess(p,complete_selection=True,stop_reason='Picture match has been checked after repair.')
    assert result['production_state']=='VISUAL_COVERAGE_READY'
    state=ProductionProject(p)._load().engine.snapshot()
    assert state.objects[(old['id'],old['version'])]['status']=='ARCHIVED'
    assert not any(o['object_type']=='QA_ISSUE' and o.get('extensions',{}).get('project_coverage') for o in _active(state).values())


def test_overlapping_repeated_ranges_do_not_inflate_visual_duration(covered):
    p,session,scene,shot,voice=covered
    edit=session.load();video=p.root/edit['scenes'][0]['shots'][0]['path']
    session.trim_shot(scene,shot,.1,.6,expected_revision=edit['revision']);rereview(p,session,scene,shot)
    added=session.add_shot(scene,video,.1,.6,expected_revision=session.load()['revision'])
    second=added['scenes'][0]['shots'][1]['id'];rereview(p,session,scene,second);register(p)
    preview=inspect_coverage(p);row=preview['scenes'][0]
    assert not preview['ready'] and row['required_seconds']==pytest.approx(.8)
    assert row['unique_visual_seconds']==pytest.approx(.5) and row['repeated_seconds']==pytest.approx(.3)
    assert any(i['code']=='REPEATED_VISUAL_DURATION' for i in row['issues'])
    assert assess(p)['binding']['result']=='FAIL'
    # A longer original audio track must not inflate available video frames.
    extended=voice.parent/'long-audio.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-f','lavfi','-i','sine=duration=3',
                    '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',str(extended)],check=True,capture_output=True)
    edit=session.load();edit['scenes'][0]['shots']=[];session.save(edit,expected_revision=edit['revision'])
    added=session.add_shot(scene,extended,1.7,2.8,expected_revision=session.load()['revision'])
    second=added['scenes'][0]['shots'][0]['id'];rereview(p,session,scene,second);register(p)
    preview=inspect_coverage(p)
    assert not preview['ready'] and any(i['code']=='USABLE_FOOTAGE_REQUIRED' for i in preview['issues'])
    assert preview['scenes'][0]['unique_visual_seconds']==0


def test_unused_context_shot_is_not_counted_and_explicit_hold_is_disclosed(covered):
    p,session,scene,shot,voice=covered
    edit=session.load();video=p.root/edit['scenes'][0]['shots'][0]['path']
    added=session.add_shot(scene,video,0,.8,expected_revision=edit['revision'])
    second=added['scenes'][0]['shots'][1]['id'];rereview(p,session,scene,second,'CONTEXT');register(p)
    assert inspect_coverage(p)['ready']
    assert len(inspect_coverage(p)['scenes'][0]['cuts'])==1
    edit=session.load();edit['scenes'][0]['shots']=edit['scenes'][0]['shots'][:1]
    session.save(edit,expected_revision=edit['revision'])
    session.trim_shot(scene,shot,.1,.6,expected_revision=session.load()['revision']);rereview(p,session,scene,shot);register(p)
    assert not inspect_coverage(p)['ready']
    edit=session.load();edit['scenes'][0]['hold_last_frame']=True;session.save(edit,expected_revision=edit['revision'])
    preview=inspect_coverage(p);row=preview['scenes'][0]
    assert preview['ready'] and row['held_seconds']==pytest.approx(.3)
    assert row['unique_visual_seconds']==pytest.approx(.5) and row['missing_seconds']==pytest.approx(0.)
    result=assess(p);assert result['binding']['ready']
    edit=session.load();edit['scenes'][0]['hold_last_frame']=False;session.save(edit,expected_revision=edit['revision'])
    assert not ProductionProject(p).status()['coverage_binding']['current']


def test_voice_edit_research_and_retraction_invalidate_closed_coverage(covered):
    from gmk_projects.evidence import review_claim
    from gmk_projects.research import research_review
    from gmk_projects.intake import import_research
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Reviewed current fixture library selection.')
    session.attach_voice(scene,voice,expected_revision=session.load()['revision'])
    assert not ProductionProject(p).status()['coverage_binding']['current']
    review_voice(p,scene,expected_revision=session.load()['revision'])
    # An identical voice/listening decision recovers its exact recorded binding.
    assert ProductionProject(p).status()['coverage_binding']['current']
    claim=research_review(p)['claims'][0]
    review_claim(p,claim['id'],claim['version'],claim['text'],disposition='INSUFFICIENT')
    status=ProductionProject(p).status()
    assert status['production_state']=='RESEARCH_INTAKE' and not status['coverage_binding']['current']
    assert not any(o['object_type']=='QA_REPORT' and o.get('extensions',{}).get('project_coverage') for o in _active(ProductionProject(p)._load().engine.snapshot()).values())
    extra=voice.parent/'more.txt';extra.write_text('CLAIM: A further assertion remains unverified.')
    before=session.load();import_research(p,extra);assert session.load()==before


def test_failed_staged_transition_or_publish_preserves_persisted_state(covered,monkeypatch):
    from gmk_projects import coverage
    from gmk_runtime.persistence import RuntimeStore
    p,session,scene,shot,voice=covered
    before=ProductionProject(p)._load().manifest_sha256;edit=session.load()
    original=coverage.QARuntime.evaluate
    def fail(engine,*args,**kwargs):
        if kwargs['report_type']=='SEARCH_COMPLETION_CERTIFICATE':raise EditError('Simulated late certificate failure')
        return original(engine,*args,**kwargs)
    monkeypatch.setattr(coverage.QARuntime,'evaluate',fail)
    with pytest.raises(EditError,match='Simulated'):assess(p,complete_selection=True,stop_reason='Explicit fixture selection closure.')
    assert ProductionProject(p)._load().manifest_sha256==before and session.load()==edit
    monkeypatch.setattr(coverage.QARuntime,'evaluate',original)
    assert assess(p)['binding']['ready']
    loaded=ProductionProject(p)._load()
    project_ref=loaded.manifest['project_ref']
    foreign=coverage.QARuntime(loaded.engine).evaluate(report_type='ASSET_COVERAGE_REPORT',scope=project_ref,
        findings=[{'severity':'MAJOR','code':'FOREIGN_REVIEW_PENDING','description':'Independent reviewer has an unresolved issue.'}])
    RuntimeStore(coverage.RUNTIME_ROOT,ProductionProject(p).workspace).persist(loaded.engine)
    assert not ProductionProject(p).status()['coverage_binding']['current']
    before=ProductionProject(p)._load().manifest_sha256
    with pytest.raises(EditError,match='ผลตรวจภาพจากขั้นตอนอื่นค้าง'):
        assess(p,complete_selection=True,stop_reason='Do not override the independent pending review.')
    final=ProductionProject(p)._load()
    assert final.manifest_sha256==before
    issue=final.engine.snapshot().objects[(foreign['issue_refs'][0]['id'],foreign['issue_refs'][0]['version'])]
    assert issue['workflow_state']=='OPEN' and issue['status']!='ARCHIVED'


def test_new_research_from_closed_coverage_reopens_intake_and_retains_media(covered):
    from gmk_projects.intake import import_research
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Reviewed fixture library.')
    before=session.load();media=p.root/before['scenes'][0]['shots'][0]['path']
    extra=voice.parent/'new-research.txt';extra.write_text('CLAIM: Another assertion needs evidence review.')
    import_research(p,extra)
    status=ProductionProject(p).status()
    assert status['production_state']=='RESEARCH_INTAKE' and not status['coverage_binding']['current']
    assert session.load()==before and media.is_file()
    assert not any(o.get('extensions',{}).get('project_coverage') for o in _active(ProductionProject(p)._load().engine.snapshot()).values())


def test_story_revision_from_closed_coverage_reopens_visual_requirements(covered):
    from tests.build051.test_production_bridge import connect, bind_all
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Reviewed fixture library.')
    old=ProductionProject(p).status()['story_binding']['scene_map'][scene]['beat_ref']
    edit=session.load();edit['scenes'][0]['visual']='A closer view of the dated report'
    session.save(edit,expected_revision=edit['revision']);bind_all(p)
    changed=connect(p);new=changed['binding']['scene_map'][scene]['beat_ref']
    assert changed['production_state']=='VISUAL_REQUIREMENTS_READY'
    assert new['id']==old['id'] and new['version']>old['version']
    assert not ProductionProject(p).status()['coverage_binding']['current']
    assert (p.root/session.load()['scenes'][0]['shots'][0]['path']).is_file()
