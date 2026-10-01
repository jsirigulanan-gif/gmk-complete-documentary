from copy import deepcopy
from pathlib import Path

import pytest

from gmk_projects.edit import EditError, EditSession
from gmk_projects.footage import candidate_from_url
from gmk_projects.intake import import_research
from gmk_projects.storage import Project
from gmk_projects.story import generate_story, apply_story


class FixtureStory:
    name='TEST_ONLY'
    def generate(self,request):
        self.request=request
        claim=request['claims'][0]['id']
        return {'title':'Draft','central_question':'What happened?','narrative_arc':'Question, context, qualified resolution',
                'research_warnings':['Source is not verified'],
                'scenes':[{'title':role,'narration':'บทฉาก '+role,'visual':'Public archive footage',
                           'audio_direction':'Quiet music','story_role':role,'claim_ids':[claim],
                           'search_queries':['archive documentary']} for role in ('HOOK','RESOLUTION')]}


def project(tmp_path):
    p=Project.create(tmp_path,'Story test')
    source=tmp_path/'source.txt';source.write_text('Research\nCLAIM: A report says something.\n')
    import_research(p,source)
    return p


def test_story_preserves_old_draft_and_creates_unapproved_beats(tmp_path):
    p=project(tmp_path);session=EditSession(p);before=session.load()
    provider=FixtureStory();draft=generate_story(p,'Tell a careful story',provider=provider)
    assert session.load()==before
    assert not provider.request['claims'][0]['narration_allowed']
    result=apply_story(p,draft)
    assert len(result['scenes'])==2
    assert result['scenes'][0]['claim_refs'][0]['id']=='CLM_000001'
    assert all(not s['shots'] and s['voice'] is None for s in result['scenes'])
    assert any(a['role']=='timeline' and a['original_name']=='edit.json' for a in p.read()['assets'])
    assert not session.preflight()['ready_to_render']


def test_unknown_claim_and_tampered_draft_rejected(tmp_path):
    p=project(tmp_path)
    class Bad(FixtureStory):
        def generate(self,request):
            draft=super().generate(request);draft['scenes'][0]['claim_ids']=['CLM_NOT_REAL'];return draft
    with pytest.raises(EditError,match='รหัส'):
        generate_story(p,'brief',provider=Bad())
    draft=generate_story(p,'brief',provider=FixtureStory())
    draft['draft']['scenes'][0]['narration']='tampered'
    with pytest.raises(EditError,match='ลงทะเบียน'):
        apply_story(p,draft)


def test_story_cannot_overwrite_concurrent_edit(tmp_path):
    p=project(tmp_path);draft=generate_story(p,'brief',provider=FixtureStory())
    session=EditSession(p);edit=session.load();edit['scenes'][0]['title']='Changed while generating'
    session.save(edit,expected_revision=edit['revision'])
    with pytest.raises(EditError,match='แก้บท'):
        apply_story(p,draft)


def test_downloader_rejects_fake_host_and_traversal_ids():
    for url in ['https://evilyoutube.com/watch?v=abcdefghijk','file:///etc/passwd','https://youtu.be/../../something','https://youtu.be/a']:
        with pytest.raises(EditError):candidate_from_url(url)
    assert candidate_from_url('https://www.youtube.com/watch?v=abcdefghijk').video_id=='abcdefghijk'
