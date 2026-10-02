"""Explicit picture/listening decisions tied to exact current draft media."""
from .edit import EditError, EditSession, asset_file, fingerprint, probe


def shot_input(scene, shot):
    return {'narration': scene['narration'], 'visual': scene['visual'],
            'claim_refs': scene.get('claim_refs', []),
            'shot': {key: shot.get(key) for key in ('id', 'path', 'sha256', 'in_seconds', 'out_seconds', 'source_url')}}


def shot_review_current(scene, shot):
    review = shot.get('visual_review') or {}
    return (review.get('decision') == 'APPROVED' and review.get('input_sha256') == fingerprint(shot_input(scene, shot))
            and review.get('match_type') in {'DIRECT', 'SUPPORTING', 'CONTEXT'}
            and bool(review.get('visible_content')) and bool(review.get('match_reason')))


def voice_input(scene):
    voice = scene.get('voice') or {}
    return {'narration': scene['narration'], 'voice': {k: voice.get(k) for k in ('path', 'sha256', 'text_sha256')}}


def voice_review_current(scene):
    voice = scene.get('voice') or {}
    return (voice.get('listening_review') == 'APPROVED'
            and voice.get('review_input_sha256') == fingerprint(voice_input(scene)))


def review_shot(project, scene_id, shot_id, *, visible_content, match_reason,
                match_type, expected_revision):
    if not visible_content.strip() or not match_reason.strip() or match_type not in {'DIRECT', 'SUPPORTING', 'CONTEXT'}:
        raise EditError('ระบุภาพที่เห็น เหตุผลที่ตรงบท และประเภทภาพให้ครบ')
    session = EditSession(project); edit = session.load()
    scene = next((s for s in edit['scenes'] if s['id'] == scene_id), None)
    shot = next((s for s in scene['shots'] if s['id'] == shot_id), None) if scene else None
    if not shot:
        raise EditError('ไม่พบช็อตที่เลือก')
    info = probe(asset_file(project, shot, 'footage'))
    if not any(s['codec_type'] == 'video' for s in info['streams']) or not 0 <= shot['in_seconds'] < shot['out_seconds'] <= info['duration_seconds']+.05:
        raise EditError('ช่วงภาพต้องอยู่ในวิดีโอจริง')
    shot['visual_review'] = {'decision': 'APPROVED', 'input_sha256': fingerprint(shot_input(scene, shot)),
                             'visible_content': visible_content.strip(), 'match_reason': match_reason.strip(),
                             'match_type': match_type}
    return session.save(edit, expected_revision=expected_revision)


def review_voice(project, scene_id, *, expected_revision):
    session = EditSession(project); edit = session.load()
    scene = next((s for s in edit['scenes'] if s['id'] == scene_id), None)
    if not scene or not scene.get('voice') or scene['voice'].get('text_sha256') != fingerprint(scene['narration']):
        raise EditError('ไม่มีเสียงที่ตรงบทฉากนี้')
    info = probe(asset_file(project, scene['voice'], 'voice'))
    if not any(s['codec_type'] == 'audio' for s in info['streams']):
        raise EditError('ไฟล์ไม่มีแทร็กเสียง')
    scene['voice'].update(listening_review='APPROVED', review_input_sha256=fingerprint(voice_input(scene)))
    return session.save(edit, expected_revision=expected_revision)
