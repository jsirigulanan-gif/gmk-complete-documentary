import json

import pytest

from gmk_projects.edit import EditError, EditSession
from gmk_projects.intake import import_research
from gmk_projects.production import ProductionProject
from gmk_projects.research import research_review
from gmk_projects.research_draft import add_review_claim, research_inputs
from gmk_projects.storage import Project


@pytest.fixture
def research(tmp_path):
    p = Project.create(tmp_path, 'General research')
    original = tmp_path/'notes.txt'
    original.write_text('Initial research\nThe event happened in 1981.\nFurther work is needed.\nhttps://example.com/report\n', encoding='utf-8')
    import_research(p, original)
    return p, research_inputs(p)[0]


def test_general_research_can_become_a_provenanced_unverified_review_unit(research):
    p, source = research
    session = EditSession(p); edit = session.load()
    script = (p.root/'script.json').read_bytes()
    assert not research_review(p)['claims']
    excerpt = 'The event happened in 1981.'
    result = add_review_claim(p, source['path'], excerpt, 'The event occurred in 1981.')
    claim = result['review']['claims'][0]
    assert claim['verification_state'] == 'UNREVIEWED' and not claim['narration_allowed']
    assert result['review']['production_state'] == 'RESEARCH_INTAKE'
    metadata = json.loads((p.root/result['asset']['path']).read_text())['manual_review_unit']
    assert metadata['source']['sha256'] == source['sha256']
    assert metadata['source']['path'] == source['path'] and metadata['excerpt'] == excerpt
    assert metadata['independent_evidence'] is False
    state = ProductionProject(p)._load().engine.snapshot()
    sources = [o for o in state.objects.values() if o.get('object_type') == 'SOURCE']
    assert len({o['independence']['group_id'] for o in sources}) == 1
    assert all(o['independence']['relationship'] == 'UNKNOWN' for o in sources)
    assert session.load() == edit and (p.root/'script.json').read_bytes() == script
    assert research_inputs(p) == [source]
    before = ProductionProject(p)._load().manifest_sha256
    assets = p.read()['assets']
    add_review_claim(p, source['path'], excerpt, 'The event occurred in 1981.')
    assert ProductionProject(p)._load().manifest_sha256 == before
    assert p.read()['assets'] == assets and len(research_review(p)['claims']) == 1


def test_invalid_or_changed_original_is_rejected_without_new_claims(research):
    p, source = research
    before = ProductionProject(p)._load().manifest_sha256
    assets = p.read()['assets']
    for path, excerpt, text in [(source['path'], 'Not present in the original', 'A claim'),
                                (source['path'], 'The event happened in 1981.', ''),
                                ('research/not-registered.txt', 'excerpt', 'claim')]:
        with pytest.raises(EditError):add_review_claim(p, path, excerpt, text)
    assert ProductionProject(p)._load().manifest_sha256 == before and p.read()['assets'] == assets
    (p.root/source['path']).write_text('Changed bytes', encoding='utf-8')
    with pytest.raises(EditError):
        add_review_claim(p, source['path'], 'Changed bytes', 'A different claim')
    assert not research_review(p)['claims'] and p.read()['assets'] == assets


def test_original_markers_in_selected_excerpt_do_not_create_extra_claims(tmp_path):
    p = Project.create(tmp_path, 'Research with markers')
    original = tmp_path/'notes.txt'
    original.write_text('Research\nQUESTION: What happened?\nhttps://example.com/report\nFACT: A statement.\n', encoding='utf-8')
    import_research(p, original)
    source = research_inputs(p)[0]
    excerpt = 'QUESTION: What happened?\nhttps://example.com/report\nFACT: A statement.'
    before = research_review(p)
    result = add_review_claim(p, source['path'], excerpt, 'A single manually selected assertion.')
    assert len(result['review']['claims']) == len(before['claims'])+1
    assert result['review']['source_leads'] == before['source_leads']
    assert all(not c['narration_allowed'] for c in result['review']['claims'])


def test_manual_extraction_reopens_connected_story_without_overwriting_edit(tmp_path):
    from tests.build051.test_production_bridge import reviewed_project, connect
    p, session, _ = reviewed_project(tmp_path, count=1)
    connect(p)
    before = session.load()
    source = research_inputs(p)[0]
    from gmk_projects.intake import read_source
    content, _ = read_source(p.root/source['path'])
    result = add_review_claim(p, source['path'], content, 'An additional assertion requiring verification.')
    assert result['review']['production_state'] == 'RESEARCH_INTAKE'
    assert session.load() == before
    assert len(result['review']['claims']) == 2
    assert sum(c['verification_state'] == 'UNREVIEWED' for c in result['review']['claims']) == 1
