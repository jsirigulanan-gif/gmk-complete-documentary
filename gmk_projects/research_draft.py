"""Explicit extraction of unverified review units from frozen research text."""
from pathlib import Path
import tempfile

from .edit import EditError, asset_file, fingerprint, media_ref
from .intake import read_source
from .production import ProductionProject
from .research import analyze_research, research_review
from .storage import atomic_json


def research_inputs(project) -> list[dict]:
    """Only registered production inputs, not fetched pages or working scripts."""
    with project._lock():
        state = ProductionProject(project)._load().engine.snapshot()
        hashes = {note.split('=', 1)[1] for artifact in state.artifacts.values()
                  if artifact.get('artifact_type') == 'RESEARCH_PACK'
                  for note in artifact.get('notes', []) if note.startswith('input_sha256=')}
        return [a for a in project.read()['assets'] if a['role'] == 'research'
                and a['sha256'] in hashes and not a['original_name'].startswith('review-unit-')]


def add_review_claim(project, source_path: str, excerpt: str, claim_text: str) -> dict:
    """Record a human-selected assertion. Never approve facts or replace the script.

    The immutable derivative retains the exact original asset and excerpt. Its
    claim remains UNREVIEWED, with contextual evidence in the same imported
    source group. Repeated identical selections replay the intake safely.
    """
    text = ' '.join(claim_text.split())
    if not text or not excerpt.strip():
        raise EditError('เลือกข้อความต้นฉบับและระบุข้อกล่าวอ้างที่ต้องตรวจ')
    with project._lock():
        loaded = ProductionProject(project)._load()
        if loaded.engine.project_state not in ('RESEARCH_INTAKE', 'RESEARCH_AUDITED',
                                              'ROUGH_NARRATIVE_READY', 'VISUAL_REQUIREMENTS_READY'):
            raise EditError('เพิ่มประเด็นได้ในขั้นรีเสิร์ชหรือร่างเรื่องเท่านั้น')
        state = loaded.engine.snapshot()
        asset = next((a for a in project.read()['assets']
                      if a['path'] == source_path and a['role'] == 'research'), None)
        if not asset or not any(a.get('artifact_type') == 'RESEARCH_PACK'
                               and 'input_sha256='+asset['sha256'] in a.get('notes', [])
                               for a in state.artifacts.values()):
            raise EditError('ต้องเลือกเอกสารรีเสิร์ชที่นำเข้าในโปรเจกต์นี้')
        source_ref = media_ref(asset)
        original, _ = read_source(asset_file(project, source_ref, 'research'))
        if excerpt not in original:
            raise EditError('ข้อความที่เลือกต้องตรงกับต้นฉบับที่เก็บไว้')
    provenance = {'source': source_ref, 'excerpt': excerpt, 'claim_text': text,
                  'verification_status': 'UNREVIEWED', 'independent_evidence': False}
    # Metadata remains outside textRun: URLs or CLAIM markers in the original
    # excerpt must not silently create extra claims or independent source leads.
    derivative = {'manual_review_unit': provenance,
                  'body': {'content': [{'paragraph': {'elements': [{'textRun': {
                      'content': 'Selected research review unit\nCLAIM: '+text+'\n'}}]}}]}}
    with tempfile.TemporaryDirectory(dir=project.root, prefix='.research-draft-') as folder:
        path = Path(folder)/('review-unit-'+fingerprint(provenance)[:24]+'.json')
        atomic_json(path, derivative)
        draft = project.add_file(path, 'research')
    ProductionProject(project).register_research(draft['path'])
    analyze_research(project)
    return {'asset': media_ref(draft), 'source': source_ref,
            'verification_status': 'UNREVIEWED', 'review': research_review(project)}
