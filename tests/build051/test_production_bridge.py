import pytest

from gmk_projects.edit import EditError, EditSession
from gmk_projects.evidence import review_claim
from gmk_projects.production import ProductionProject
from gmk_projects.production_bridge import inspect_story, connect_story
from gmk_projects.research import research_review
from gmk_projects.script_review import review_scene_claims
from tests.build049.test_script_review import setup


def reviewed_project(tmp_path, count=2):
    p, session, claim, source = setup(tmp_path)
    review_claim(p, claim['id'], claim['version'], claim['text'], source=source,
                 excerpt='The event occurred in 1981.', disposition='SUPPORTED')
    edit = session.load()
    edit['central_question'] = 'What does the report establish?'
    edit['narrative_arc'] = 'Question, dated report, and limits of the report.'
    edit['scenes'][0]['visual'] = 'The dated report on screen'
    for _ in range(count-1):
        new = session.new_scene()
        new.update(narration=edit['scenes'][0]['narration'], visual='Close view of the dated report')
        edit['scenes'].append(new)
    session.save(edit, expected_revision=edit['revision'])
    bind_all(p)
    return p, session, source


def bind_all(p):
    report = research_review(p)
    session = EditSession(p)
    for scene in session.load()['scenes']:
        review_scene_claims(p, scene['id'], [report['claims'][0]['id']], expected_revision=session.load()['revision'],
            expected_manifest_sha256=report['manifest_sha256'], editorial_note='The narration attributes the date to the report.')


def connect(p):
    preview = inspect_story(p)
    return connect_story(p, expected_edit_sha256=preview['edit_sha256'], expected_manifest_sha256=preview['manifest_sha256'])


def test_reviewed_editor_scenes_enter_canonical_graph_and_replay_is_noop(tmp_path):
    p, session, _ = reviewed_project(tmp_path)
    assert inspect_story(p)['ready']
    result = connect(p)
    assert result['production_state'] == 'VISUAL_REQUIREMENTS_READY'
    assert result['binding']['current'] and not result['documentary_completed']
    runtime = ProductionProject(p)
    loaded = runtime._load()
    state = loaded.engine.snapshot()
    assert loaded.dependency_summary == {'drift_roots': 0, 'invalidations': 0, 'changed_objects': 0}
    for scene in session.load()['scenes']:
        refs = result['binding']['scene_map'][scene['id']]
        ref = refs['beat_ref']; beat = state.objects[(ref['id'], ref['version'])]
        assert beat['scene_ref'] == refs['scene_ref']
        assert beat['claim_bindings'][0]['claim_ref'] == scene['claim_refs'][0]
        assert beat['visual_requirement']['viewer_must_see'] == scene['visual']
        assert beat['workflow_state'] == 'VISUAL_REQUIREMENT_READY' and 'narration' not in beat
    old_sha = loaded.manifest_sha256
    again = connect(p)
    assert again['idempotent_replay']
    assert runtime._load().manifest_sha256 == old_sha


def test_unreviewed_or_stale_preview_cannot_advance_production(tmp_path):
    p, session, _, _ = setup(tmp_path)
    initial = ProductionProject(p)._load().manifest_sha256
    preview = inspect_story(p)
    assert not preview['ready']
    with pytest.raises(EditError, match='ยังเชื่อมบทไม่ได้'):
        connect(p)
    assert ProductionProject(p)._load().manifest_sha256 == initial
    edit = session.load(); edit['scenes'][0]['title'] = 'Changed'
    session.save(edit, expected_revision=edit['revision'])
    with pytest.raises(EditError, match='เปลี่ยนหลังเปิดตรวจ'):
        connect_story(p, expected_edit_sha256=preview['edit_sha256'], expected_manifest_sha256=preview['manifest_sha256'])


def test_reordering_excluding_and_reincluding_scenes_preserves_identity_and_history(tmp_path):
    p, session, _ = reviewed_project(tmp_path)
    original = connect(p)['binding']['scene_map']
    edit = session.load(); edit['scenes'].reverse(); edit['scenes'][1]['included'] = False
    session.save(edit, expected_revision=edit['revision'])
    assert not ProductionProject(p).status()['story_binding']['current']
    revised = connect(p)['binding']['scene_map']
    assert set(revised) == {edit['scenes'][0]['id']}
    edit = session.load(); edit['scenes'][1]['included'] = True
    session.save(edit, expected_revision=edit['revision'])
    restored = connect(p)['binding']['scene_map']
    assert set(restored) == set(original)
    for key in original:
        assert restored[key]['beat_ref']['id'] == original[key]['beat_ref']['id']
        assert restored[key]['beat_ref']['version'] > original[key]['beat_ref']['version']
    state = ProductionProject(p)._load().engine.snapshot()
    assert all((row['beat_ref']['id'], row['beat_ref']['version']) in state.objects for row in original.values())


def test_evidence_retraction_invalidates_bound_story_and_requires_new_review(tmp_path):
    p, _, source = reviewed_project(tmp_path)
    connect(p)
    claim = research_review(p)['claims'][0]
    review_claim(p, claim['id'], claim['version'], claim['text'], disposition='INSUFFICIENT')
    status = ProductionProject(p).status()
    assert status['production_state'] == 'RESEARCH_INTAKE'
    assert not status['story_binding']['current']
    with pytest.raises(EditError, match='ยังเชื่อมบทไม่ได้'):
        connect(p)
    claim = research_review(p)['claims'][0]
    review_claim(p, claim['id'], claim['version'], claim['text'], source=source,
                 excerpt='The event occurred in 1981.', disposition='SUPPORTED')
    bind_all(p)
    assert connect(p)['binding']['current']


def test_late_gate_failure_leaves_persistent_project_untouched(tmp_path, monkeypatch):
    from gmk_projects import production_bridge
    p, _, _ = reviewed_project(tmp_path)
    runtime = ProductionProject(p)
    before = runtime._load().manifest_sha256
    original = production_bridge._transition
    def fail_late(engine, target):
        if target == 'VISUAL_REQUIREMENTS_READY':
            raise EditError('Simulated final gate failure')
        original(engine, target)
    monkeypatch.setattr(production_bridge, '_transition', fail_late)
    with pytest.raises(EditError, match='Simulated'):
        connect(p)
    assert runtime._load().manifest_sha256 == before
    assert runtime.status()['production_state'] == 'RESEARCH_INTAKE'
    assert not runtime.status()['story_binding']['connected']


def test_search_uses_exact_canonical_beat_and_media_edits_do_not_change_binding(tmp_path):
    from gmk_projects.production_bridge import scene_search_intent
    p, session, _ = reviewed_project(tmp_path, count=1)
    result = connect(p)
    edit = session.load(); scene = edit['scenes'][0]
    intent = scene_search_intent(p, scene['id'])
    assert intent.beat_ref == result['binding']['scene_map'][scene['id']]['beat_ref']
    assert list(intent.claim_refs) == scene['claim_refs']
    assert intent.claim_texts and intent.youtube_queries
    edit['music_gain'] = .2; scene['hold_last_frame'] = True
    session.save(edit, expected_revision=edit['revision'])
    assert ProductionProject(p).status()['story_binding']['current']
    assert scene_search_intent(p, scene['id']) == intent
    edit = session.load(); edit['scenes'][0]['visual'] = 'A different visual'
    session.save(edit, expected_revision=edit['revision'])
    with pytest.raises(EditError, match='เชื่อมบทใหม่'):
        scene_search_intent(p, scene['id'])


def test_research_change_rejects_preview_and_inflight_footage_save(tmp_path):
    p, session, _ = reviewed_project(tmp_path, count=1)
    connect(p)
    preview = inspect_story(p)
    edit = session.load()
    claim = research_review(p)['claims'][0]
    review_claim(p, claim['id'], claim['version'], claim['text'], disposition='INSUFFICIENT')
    with pytest.raises(EditError, match='เปลี่ยนหลังเปิดตรวจ'):
        connect_story(p, expected_edit_sha256=preview['edit_sha256'], expected_manifest_sha256=preview['manifest_sha256'])
    with pytest.raises(EditError, match='เปลี่ยนระหว่างเตรียมภาพ'):
        session.save(edit, expected_revision=edit['revision'], expected_production_manifest_sha256=preview['manifest_sha256'])
    assert session.load() == edit


def test_external_act_revision_invalidates_story_binding(tmp_path):
    from gmk_runtime.persistence import RuntimeStore
    from gmk_projects.production_bridge import scene_search_intent
    p, session, _ = reviewed_project(tmp_path, count=1)
    connect(p)
    production = ProductionProject(p)
    engine = production._load().engine
    act = next(o for o in engine.snapshot().objects.values() if o['object_type'] == 'ACT')
    tx = engine.begin()
    revised = tx.create_version(act['id'], base_version=act['version'], patch={'title': 'Externally revised act'})
    tx.promote_active_version(revised['id'], revised['version']); tx.commit()
    RuntimeStore(engine.root, production.workspace).persist(engine)
    assert not production.status()['story_binding']['current']
    with pytest.raises(EditError, match='เชื่อมบทใหม่'):
        scene_search_intent(p, session.load()['scenes'][0]['id'])


@pytest.mark.parametrize('field,value', [('visual', ''), ('story_role', 'UNKNOWN')])
def test_invalid_visual_or_role_cannot_advance(tmp_path, field, value):
    p, session, _ = reviewed_project(tmp_path, count=1)
    edit = session.load(); edit['scenes'][0][field] = value
    session.save(edit, expected_revision=edit['revision'])
    before = ProductionProject(p)._load().manifest_sha256
    assert not inspect_story(p)['ready']
    with pytest.raises(EditError, match='ยังเชื่อมบทไม่ได้'):
        connect(p)
    assert ProductionProject(p)._load().manifest_sha256 == before
