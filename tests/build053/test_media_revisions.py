import subprocess

import pytest

from gmk_projects.edit import EditError
from gmk_projects.media_bridge import connect_media, inspect_media, _pools
from gmk_projects.production import ProductionProject
from gmk_projects.production_bridge import _active
from tests.build051.test_production_bridge import connect
from tests.build053.test_media_bridge import footage, register, rows, rereview


def test_evidence_retraction_reopens_owned_media_and_blocks_reconnection(footage):
    from gmk_projects.evidence import review_claim
    from gmk_projects.research import research_review
    p,session,scene,shot,_=footage
    register(p); before=session.load()
    claim=research_review(p)['claims'][0]
    review_claim(p,claim['id'],claim['version'],claim['text'],disposition='INSUFFICIENT')
    status=ProductionProject(p).status()
    assert status['production_state']=='RESEARCH_INTAKE' and not status['media_binding']['current']
    assert session.load()==before and not inspect_media(p)['ready']
    with pytest.raises(EditError): register(p)


def test_new_research_from_owned_media_preserves_edit(footage):
    from gmk_projects.intake import import_research
    p,session,scene,shot,video=footage
    register(p); before=session.load()
    research=video.parent/'additional.txt'; research.write_text('CLAIM: Further research needs review.')
    import_research(p,research)
    status=ProductionProject(p).status()
    assert status['production_state']=='RESEARCH_INTAKE' and status['claim_count']==2
    assert not status['media_binding']['current'] and session.load()==before


def test_story_change_requires_rebinding_and_keeps_asset_identity(footage):
    p,session,scene,shot,_=footage
    register(p); original=rows(p,scene)[0]
    edit=session.load(); edit['scenes'][0]['visual']='A revised view of the dated report'
    session.save(edit,expected_revision=edit['revision'])
    assert not inspect_media(p)['ready']
    assert connect(p)['binding']['current']
    rereview(p,session,scene,shot); assert register(p)['binding']['current']
    assert rows(p,scene)[0]['asset_ref']['id']==original['asset_ref']['id']


def test_status_without_draft_is_read_only(tmp_path):
    from gmk_projects.storage import Project
    p=Project.create(tmp_path,'Unedited project')
    before=ProductionProject(p)._load().manifest_sha256
    assert not (p.root/'edit.json').exists()
    assert not ProductionProject(p).status()['media_binding']['current']
    assert not (p.root/'edit.json').exists()
    assert ProductionProject(p)._load().manifest_sha256==before


def test_scene_exclusion_and_reinclusion_keep_identity_and_retire_selection(footage):
    from tests.build051.test_production_bridge import bind_all
    p,session,scene,shot,_=footage
    register(p); original=rows(p,scene)[0]
    edit=session.load(); second=session.new_scene()
    second.update(narration=edit['scenes'][0]['narration'],visual='Additional fixture scene')
    edit['scenes'].append(second); session.save(edit,expected_revision=edit['revision'])
    bind_all(p); connect(p); assert register(p)['binding']['current']
    edit=session.load(); edit['scenes'].reverse(); edit['scenes'][1]['included']=False
    session.save(edit,expected_revision=edit['revision']); connect(p)
    assert register(p)['binding']['current']
    state=ProductionProject(p)._load().engine.snapshot()
    assert _pools(state)[scene]['extensions']['project_media']['retired']
    assert original['asset_ref']['id'] not in _active(state)
    edit=session.load(); edit['scenes'][1]['included']=True
    session.save(edit,expected_revision=edit['revision']); connect(p)
    assert register(p)['binding']['current']
    assert rows(p,scene)[0]['asset_ref']['id']==original['asset_ref']['id']


def test_partial_scene_coverage_and_cli_preserve_pending_work(footage,capsys,monkeypatch):
    from gmk_projects.__main__ import main
    from gmk_projects.brief import save_brief
    from gmk_projects.workflow import workflow_status
    from gmk_projects.media_review import review_voice
    import json
    p,session,scene,shot,video=footage
    edit=session.load()
    save_brief(p,topic='Fixture',audience='Fixture viewers',central_question=edit['central_question'],
               target_seconds=180,expected_revision=edit['revision'])
    connect(p)
    voice=video.parent/'speech.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=duration=0.8',str(voice)],check=True,capture_output=True)
    session.attach_voice(scene,voice,expected_revision=session.load()['revision'])
    review_voice(p,scene,expected_revision=session.load()['revision'])
    assert workflow_status(p)['next_action']=='PRODUCTION_MEDIA'
    monkeypatch.setattr('sys.argv',['gmk_projects','media-inspect',str(p.root)])
    main(); preview=json.loads(capsys.readouterr().out)
    assert preview['ready'] and not preview['binding']['current']
    monkeypatch.setattr('sys.argv',['gmk_projects','media-connect',str(p.root),'--edit-sha256',preview['edit_sha256'],
                                  '--manifest-sha256',preview['manifest_sha256']])
    main(); connected=json.loads(capsys.readouterr().out)
    assert connected['binding']['current'] and not connected['documentary_completed']
