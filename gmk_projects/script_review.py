"""Editorial scene-to-claim bindings checked against the authoritative research heads.

This is a derived readiness report, not a new production state machine. A matching
claim ID does not establish that its wording supports narration: the operator
explicitly reviews that relationship, which is invalidated by either revision.
"""
from .edit import EditError, EditSession, fingerprint
from .research import research_review


def review_scene_claims(project, scene_id, claim_ids, *, expected_revision,
                        expected_manifest_sha256, editorial_note):
    if not editorial_note.strip():
        raise EditError('ระบุว่าหลักฐานรองรับบทฉากนี้อย่างไร')
    report = research_review(project)
    if report['manifest_sha256'] != expected_manifest_sha256:
        raise EditError('หลักฐานเปลี่ยนระหว่างตรวจ กรุณาเปิดตรวจรุ่นใหม่')
    heads = {c['id']: c for c in report['claims']}
    if not claim_ids or len(set(claim_ids)) != len(claim_ids):
        raise EditError('เลือกข้อกล่าวอ้างที่รองรับฉากอย่างน้อยหนึ่งรายการและห้ามซ้ำ')
    refs = []
    for key in claim_ids:
        if key not in heads or not heads[key]['narration_allowed']:
            raise EditError('ข้อกล่าวอ้างยังไม่ผ่านการตรวจหรือไม่อนุญาตใช้ในบท: '+key)
        refs.append({'id': key, 'version': heads[key]['version']})
    session = EditSession(project)
    data = session.load()
    scene = next((s for s in data['scenes'] if s['id'] == scene_id), None)
    if scene is None or not scene['narration'].strip():
        raise EditError('ไม่พบฉากหรือยังไม่มีบทฉากนี้')
    scene['claim_refs'] = refs
    scene['claim_review'] = {
        'narration_sha256': fingerprint(scene['narration']),
        'refs_sha256': fingerprint(refs), 'decision': 'USER_REVIEWED',
        'editorial_note': editorial_note.strip(),
    }
    return session.save(data, expected_revision=expected_revision)


def script_readiness(project, data=None, research=None):
    data = data if data is not None else EditSession(project).load()
    research = research if research is not None else research_review(project)
    heads = {c['id']: c for c in research['claims']}
    rows = []
    for scene in data['scenes']:
        if not scene['included']:
            continue
        issues = []
        refs = scene.get('claim_refs', [])
        if not refs:
            issues.append('ยังไม่ได้ผูกข้อกล่าวอ้างกับบทฉากนี้')
        for ref in refs:
            claim = heads.get(ref.get('id'))
            if claim is None:
                issues.append('ไม่พบข้อกล่าวอ้าง '+str(ref.get('id')))
            elif claim['version'] != ref.get('version'):
                issues.append('ข้อกล่าวอ้างเปลี่ยนรุ่น ต้องตรวจบทใหม่: '+claim['id'])
            elif not claim['narration_allowed']:
                issues.append('ยังไม่อนุญาตใช้ข้อกล่าวอ้างในบท: '+claim['id'])
        decision = scene.get('claim_review', {})
        if (decision.get('decision') != 'USER_REVIEWED'
                or decision.get('narration_sha256') != fingerprint(scene['narration'])
                or decision.get('refs_sha256') != fingerprint(refs)):
            issues.append('ยังไม่ได้ยืนยันว่าหลักฐานรองรับถ้อยคำในบทฉบับนี้')
        rows.append({'scene_id': scene['id'], 'claim_refs': refs, 'ready': not issues, 'issues': issues})
    return {'ready': bool(rows) and all(r['ready'] for r in rows), 'scenes': rows,
            'research_manifest_sha256': research['manifest_sha256'],
            'scope': 'Explicit scene-to-claim editorial review against current canonical claim versions; not a final production gate.'}
