from pathlib import Path

import pytest

from gmk_projects.edit import EditError, media_ref
from gmk_projects.evidence import review_claim, public_url
from gmk_projects.intake import import_research
from gmk_projects.research import research_review
from gmk_projects.storage import Project


def setup(tmp_path):
    project=Project.create(tmp_path,'Review')
    doc=tmp_path/'input.txt';doc.write_text('Research\nCLAIM: An event happened in 1981.')
    import_research(project,doc)
    excerpt=tmp_path/'external.txt';excerpt.write_text('An event happened in 1981. The location is unknown.')
    asset=project.add_file(excerpt,'research',source_url='https://example.com/source')
    source={'url':'https://example.com/source','title':'Archived example','raw':media_ref(asset),'text':media_ref(asset)}
    return project,source


def test_explicit_review_versions_claim_and_can_retract_support(tmp_path):
    p,source=setup(tmp_path)
    before=research_review(p)['claims'][0]
    review_claim(p,before['id'],before['version'],before['text'],source=source,
                 excerpt='An event happened in 1981.',disposition='SUPPORTED')
    checked=research_review(p)['claims'][0]
    assert checked['verification_state']=='SOURCE_VERIFIED' and checked['narration_allowed']
    assert checked['version']>before['version']
    review_claim(p,checked['id'],checked['version'],'A different unproven assertion.',disposition='INSUFFICIENT')
    latest=research_review(p)['claims'][0]
    assert latest['verification_state']=='INSUFFICIENT_EVIDENCE' and not latest['narration_allowed']
    assert len(latest['evidence'])==1  # Original pack context retained; old external support not inherited.


def test_fabricated_excerpt_wrong_source_and_old_version_rejected(tmp_path):
    p,source=setup(tmp_path);claim=research_review(p)['claims'][0]
    with pytest.raises(EditError,match='ตรงกับข้อความ'):
        review_claim(p,claim['id'],claim['version'],claim['text'],source=source,excerpt='Invented quotation',disposition='SUPPORTED')
    forged={**source,'url':'https://example.com/other'}
    with pytest.raises(EditError,match='URL'):
        review_claim(p,claim['id'],claim['version'],claim['text'],source=forged,excerpt='An event happened',disposition='SUPPORTED')
    with pytest.raises(EditError,match='รุ่น'):
        review_claim(p,claim['id'],999,claim['text'],disposition='INSUFFICIENT')
    assert research_review(p)['claims'][0]==claim


def test_source_fetch_rejects_private_or_credentialed_targets():
    for url in ['http://127.0.0.1/private','http://[::1]/','file:///etc/passwd','https://name:password@example.com/']:
        with pytest.raises(EditError):public_url(url)
