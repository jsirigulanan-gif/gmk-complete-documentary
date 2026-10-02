import subprocess

import pytest

from gmk_projects.brief import save_brief
from gmk_projects.edit import EditError, EditSession, fingerprint
from gmk_projects.media_review import review_shot, review_voice, shot_review_current, voice_review_current
from gmk_projects.production import ProductionProject
from gmk_projects.render import approve_editorial_review, export_delivery, render_project
from gmk_projects.storage import Project
from gmk_projects.workflow import FILM_CHECKS, workflow_status
from tests.build051.test_production_bridge import reviewed_project, connect


def brief(p):
    session = EditSession(p); edit = session.load()
    return save_brief(p, topic=edit['title'], audience='General viewers', central_question=edit.get('central_question', 'What happened?'),
                      target_seconds=180, expected_revision=edit['revision'])


@pytest.fixture
def media(tmp_path):
    p, session, _ = reviewed_project(tmp_path, count=1)
    brief(p); connect(p)
    video, voice = tmp_path/'picture.mp4', tmp_path/'speech.wav'
    for args in [('-f','lavfi','-i','color=size=640x360:rate=25:duration=2','-an','-c:v','mpeg4',str(video)),
                 ('-f','lavfi','-i','sine=frequency=880:duration=0.9:sample_rate=48000',str(voice))]:
        subprocess.run(['ffmpeg','-v','error','-y',*args], check=True, capture_output=True)
    edit = session.load(); edit.update(width=640, height=360, fps=25, music_omitted=True)
    edit = session.save(edit, expected_revision=edit['revision']); scene_id = edit['scenes'][0]['id']
    edit = session.attach_voice(scene_id, voice, expected_revision=edit['revision'])
    edit = session.add_shot(scene_id, video, 0, 1.5, expected_revision=edit['revision'])
    return p, session, scene_id, edit['scenes'][0]['shots'][0]['id'], voice


def review_media(p, session, scene, shot):
    from gmk_projects.media_bridge import inspect_media, connect_media
    from gmk_projects.coverage import inspect_coverage, record_coverage
    review_voice(p, scene, expected_revision=session.load()['revision'])
    review_shot(p, scene, shot, visible_content='The fixture frame is visible.', match_reason='Fixture matching decision for this narration.',
                match_type='SUPPORTING', expected_revision=session.load()['revision'])
    preview = inspect_media(p)
    connect_media(p, expected_edit_sha256=preview['edit_sha256'], expected_manifest_sha256=preview['manifest_sha256'])
    preview = inspect_coverage(p)
    record_coverage(p, expected_edit_sha256=preview['edit_sha256'], expected_manifest_sha256=preview['manifest_sha256'],
                    complete_selection=preview['ready'], stop_reason='Reviewed synthetic fixture library is sufficient.' if preview['ready'] else '')
    if preview['ready']:
        from gmk_projects.final_production import inspect_final, prepare_final, decide_final_voice, _heads
        final = inspect_final(p)
        prepare_final(p, expected_edit_sha256=final['edit_sha256'], expected_manifest_sha256=final['manifest_sha256'])
        final = inspect_final(p);master = _heads(ProductionProject(p)._load().engine.snapshot(), 'MASTER_VOICE')[0]
        decide_final_voice(p, expected_edit_sha256=final['edit_sha256'], expected_manifest_sha256=final['manifest_sha256'],
                          expected_master_sha256=master['audio']['sha256'], decision='APPROVED', actor_id='Synthetic fixture reviewer')


def test_new_topic_brief_and_real_readiness_preserve_core_state(tmp_path):
    p=Project.create(tmp_path,'A new topic'); session=EditSession(p)
    before=ProductionProject(p)._load().manifest_sha256
    status=workflow_status(p)
    assert len(status['stages']) == 20 and status['next_action']=='BRIEF'
    assert not status['documentary_completed']
    with pytest.raises(EditError, match='ระบุ'):
        save_brief(p,topic='topic',audience='',central_question='question',target_seconds=180,expected_revision=session.load()['revision'])
    with pytest.raises(EditError, match='30–3600'):
        save_brief(p,topic='topic',audience='viewers',central_question='question',target_seconds=True,expected_revision=session.load()['revision'])
    brief(p)
    assert workflow_status(p)['next_action']=='IMPORT_RESEARCH'
    assert ProductionProject(p)._load().manifest_sha256==before


def test_exact_picture_and_voice_reviews_invalidate_on_relevant_changes(media):
    p, session, scene_id, shot_id, voice=media
    review_media(p,session,scene_id,shot_id)
    scene=session.load()['scenes'][0]
    assert shot_review_current(scene,scene['shots'][0]) and voice_review_current(scene)
    edit=session.load(); edit['scenes'][0]['visual']='A different picture is now required'
    session.save(edit,expected_revision=edit['revision'])
    scene=session.load()['scenes'][0]
    assert not shot_review_current(scene,scene['shots'][0]) and voice_review_current(scene)
    review_shot(p,scene_id,shot_id,visible_content='Checked frame',match_reason='New picture decision',match_type='CONTEXT',expected_revision=session.load()['revision'])
    session.trim_shot(scene_id,shot_id,.2,1.4,expected_revision=session.load()['revision'])
    scene=session.load()['scenes'][0]
    assert not shot_review_current(scene,scene['shots'][0])
    session.attach_voice(scene_id,voice,expected_revision=session.load()['revision'])
    assert not voice_review_current(session.load()['scenes'][0])


def test_reviewed_project_runs_through_render_checklist_and_local_delivery(media):
    p, session, scene_id, shot_id, _=media
    review_media(p,session,scene_id,shot_id)
    before=workflow_status(p)
    assert before['next_action']=='RENDER',before['stages']
    result=render_project(p)
    assert workflow_status(p)['next_action']=='FILM_QA'
    with pytest.raises(EditError,match='ให้ครบ'):
        approve_editorial_review(p,expected_master_sha256=result['technical_qa']['sha256'],checklist={'facts':True})
    assert not (p.root/'editorial_review.json').exists()
    approve_editorial_review(p,expected_master_sha256=result['technical_qa']['sha256'],checklist=dict.fromkeys(FILM_CHECKS,True))
    assert workflow_status(p)['next_action']=='EXPORT'
    export_delivery(p)
    status=workflow_status(p)
    assert status['next_action']=='DRIVE' and not status['documentary_completed']
    session.trim_shot(scene_id,shot_id,.1,1.4,expected_revision=session.load()['revision'])
    status=workflow_status(p)
    rows={s['key']:s for s in status['stages']}
    assert not rows['SELECTION']['ready'] and not rows['RENDER']['ready'] and not rows['FILM_QA']['ready'] and not rows['DELIVERY']['ready']


def test_claims_ready_but_scene_wording_review_missing_points_to_script(tmp_path):
    p, session, _=reviewed_project(tmp_path,count=1); brief(p)
    edit=session.load(); edit['scenes'][0].pop('claim_review')
    session.save(edit,expected_revision=edit['revision'])
    assert workflow_status(p)['next_action']=='SCRIPT'


def test_new_research_reopens_early_story_without_discarding_edit(tmp_path):
    from gmk_projects.intake import import_research
    p, session, _=reviewed_project(tmp_path,count=1); connect(p)
    edit=session.load(); before=ProductionProject(p)._load().manifest_sha256
    new=tmp_path/'more.txt'; new.write_text('Additional research\nCLAIM: A further assertion needs review.')
    import_research(p,new)
    assert session.load()==edit
    status=ProductionProject(p).status()
    assert status['production_state']=='RESEARCH_INTAKE' and status['claim_count']==2
    assert status['manifest_sha256']!=before and status['unreviewed_claim_count']==1


def test_missing_media_never_counts_as_acquired_or_reviewed(media):
    p,session,scene_id,shot_id,voice=media
    review_media(p,session,scene_id,shot_id)
    shot=session.load()['scenes'][0]['shots'][0]
    (p.root/shot['path']).unlink()
    status=workflow_status(p)
    rows={s['key']:s for s in status['stages']}
    assert not rows['SELECTION']['ready'] and not rows['ACQUISITION']['ready'] and not rows['SHOT_PLAN']['ready']
    assert status['next_action']=='FOOTAGE' and status['next_scene_id']==scene_id
    assert status['issues'] and not status['documentary_completed']
    before=session.load();count=len(p.read()['assets'])
    p.add_file(voice.parent/'picture.mp4','footage')
    assert session.load()==before and len(p.read()['assets'])==count
    assert workflow_status(p)['next_action']=='RENDER'


def test_missing_voice_routes_back_to_voice_even_with_prior_listening_review(media):
    p,session,scene_id,shot_id,voice=media
    review_media(p,session,scene_id,shot_id)
    scene=session.load()['scenes'][0]; (p.root/scene['voice']['path']).unlink()
    result=workflow_status(p)
    assert result['next_action']=='VOICE'
    assert result['next_scene_id']==scene_id
    assert not next(s for s in result['stages'] if s['key']=='VOICE')['ready']
    p.add_file(voice,'voice')
    assert workflow_status(p)['next_action']=='RENDER'


def test_recovery_targets_the_later_scene_with_missing_audio(tmp_path):
    p, session, _ = reviewed_project(tmp_path, count=2)
    brief(p); connect(p)
    video = tmp_path/'picture.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=640x360:rate=25:duration=2',
                    '-an','-c:v','mpeg4',str(video)],check=True,capture_output=True)
    edit=session.load();edit.update(width=640,height=360,fps=25,music_omitted=True)
    session.save(edit,expected_revision=edit['revision'])
    ids=[s['id'] for s in session.load()['scenes']]
    for i, scene_id in enumerate(ids):
        voice=tmp_path/f'voice-{i}.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        f'sine=frequency={440+i*440}:duration=0.9:sample_rate=48000',str(voice)],check=True,capture_output=True)
        session.attach_voice(scene_id,voice,expected_revision=session.load()['revision'])
        edit=session.add_shot(scene_id,video,0,1.5,expected_revision=session.load()['revision'])
        scene=next(s for s in edit['scenes'] if s['id']==scene_id)
        review_media(p,session,scene_id,scene['shots'][0]['id'])
    scenes=session.load()['scenes']
    assert workflow_status(p)['next_action']=='RENDER'
    assert all(voice_review_current(s) for s in scenes)
    (p.root/scenes[1]['voice']['path']).unlink()
    assert (p.root/scenes[0]['voice']['path']).is_file()
    result=workflow_status(p)
    assert result['next_action']=='VOICE' and result['next_scene_id']==ids[1]
