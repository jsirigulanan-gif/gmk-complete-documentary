import pytest

from gmk_projects.edit import EditError, EditSession, media_ref
from gmk_projects.evidence import review_claim
from gmk_projects.intake import import_research
from gmk_projects.research import research_review
from gmk_projects.script_review import review_scene_claims, script_readiness
from gmk_projects.storage import Project


def setup(tmp_path):
    project = Project.create(tmp_path, 'Scene evidence test')
    source = tmp_path/'source.txt'
    source.write_text('Research\nCLAIM: The event occurred in 1981.')
    import_research(project, source)
    session = EditSession(project)
    edit = session.load()
    edit['scenes'][0]['narration'] = 'รายงานระบุว่าเหตุการณ์เกิดขึ้นในปี 1981'
    session.save(edit, expected_revision=edit['revision'])
    claim = research_review(project)['claims'][0]
    archived = tmp_path/'archive.txt'
    archived.write_text('The event occurred in 1981.')
    ref = media_ref(project.add_file(archived, 'research', source_url='https://example.com/report'))
    source = {'title': 'Example', 'url': 'https://example.com/report', 'text': ref, 'raw': ref}
    return project, session, claim, source


def bind(project, session):
    research = research_review(project)
    edit = session.load()
    return review_scene_claims(project, edit['scenes'][0]['id'], [research['claims'][0]['id']],
        expected_revision=edit['revision'], expected_manifest_sha256=research['manifest_sha256'],
        editorial_note='The narration attributes the date to the archived report.')


def test_binding_requires_evidence_and_wording_review_and_invalidates_on_changes(tmp_path):
    p, session, claim, source = setup(tmp_path)
    assert not script_readiness(p)['ready']
    with pytest.raises(EditError, match='ยังไม่ผ่าน'):
        bind(p, session)
    review_claim(p, claim['id'], claim['version'], claim['text'], source=source,
                 excerpt='The event occurred in 1981.', disposition='SUPPORTED')
    bound = bind(p, session)
    assert script_readiness(p)['ready']
    bound['scenes'][0]['narration'] = 'เหตุการณ์เกิดขึ้นในปี 1982'
    session.save(bound, expected_revision=bound['revision'])
    assert not script_readiness(p)['ready']
    assert 'claim_review' not in session.load()['scenes'][0]


def test_retracted_canonical_claim_invalidates_previously_reviewed_scene(tmp_path):
    p, session, claim, source = setup(tmp_path)
    review_claim(p, claim['id'], claim['version'], claim['text'], source=source,
                 excerpt='The event occurred in 1981.', disposition='SUPPORTED')
    bind(p, session)
    current = research_review(p)['claims'][0]
    review_claim(p, current['id'], current['version'], current['text'], disposition='INSUFFICIENT')
    report = script_readiness(p)
    assert not report['ready'] and 'เปลี่ยนรุ่น' in report['scenes'][0]['issues'][0]
    with pytest.raises(EditError, match='ยังไม่ผ่าน'):
        bind(p, session)


def test_blank_project_opens_editor_and_excluded_scenes_are_not_claimed_ready(tmp_path):
    project = Project.create(tmp_path, 'Blank brief')
    session = EditSession(project)
    edit = session.load()
    assert edit['source_script_sha256'] is None and len(edit['scenes']) == 1
    edit['scenes'][0]['included'] = False
    session.save(edit, expected_revision=edit['revision'])
    assert not script_readiness(project)['ready']
    assert not session.preflight()['ready_to_render']


def test_batch_footage_resumes_empty_included_scenes_and_keeps_failures(tmp_path, monkeypatch):
    from gmk_projects import footage
    project = Project.create(tmp_path, 'Resume test')
    session = EditSession(project)
    edit = session.load()
    edit['scenes'] = [session.new_scene() for _ in range(4)]
    edit['scenes'][2]['shots'] = [{'existing': 'manual cut'}]
    edit['scenes'][3]['included'] = False
    session.save(edit, expected_revision=edit['revision'])
    visited = []
    def prepare(project, scene_id, **kwargs):
        visited.append(scene_id)
        if len(visited) == 1:
            raise EditError('Missing captions')
        return {'prepared': True, 'scene_id': scene_id}
    monkeypatch.setattr(footage, 'prepare_scene_footage', prepare)
    result = footage.prepare_project_footage(project)
    assert visited == [s['id'] for s in edit['scenes'][:2]]
    assert not result['scenes'][0]['prepared'] and result['scenes'][1]['prepared']
    assert session.load()['scenes'][2]['shots'] == [{'existing': 'manual cut'}]
