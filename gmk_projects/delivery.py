"""Verify exact draft exports and their storage receipts without granting release approval."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from zipfile import ZipFile, BadZipFile

from .edit import EditError, EditSession, asset_file, fingerprint
from .production import ProductionProject
from .storage import atomic_json, digest, StorageError


RENDER_FILES = {
    'preview.mp4', 'captions.srt', 'timeline.json', 'edit.snapshot.json',
    'qa.json', 'credits.json', 'render.json', 'script-review.json',
}


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('Expected an object')
        return value
    except (OSError, ValueError) as exc:
        raise EditError('ไม่พบหรืออ่านบันทึกไม่ได้: '+path.name) from exc


def current_reviewed_render(project):
    """Read immutable render artifacts, not only the mutable last-render pointer."""
    render = read_json(project.root/'last_render.json')
    decision = read_json(project.root/'editorial_review.json')
    refs = render.get('registered', {})
    if set(refs) != RENDER_FILES:
        raise EditError('ไฟล์ประกอบการเรนเดอร์ไม่ครบ กรุณาเรนเดอร์และตรวจใหม่')
    files = {name: asset_file(project, ref, 'exports' if name == 'preview.mp4' else 'timeline')
             for name, ref in refs.items()}
    qa, snapshot, timeline, receipt, script = (
        read_json(files[name]) for name in ('qa.json', 'edit.snapshot.json', 'timeline.json', 'render.json', 'script-review.json'))
    edit_sha = fingerprint(snapshot)
    master_sha = refs['preview.mp4']['sha256']
    research_sha = ProductionProject(project).status()['manifest_sha256']
    if fingerprint(EditSession(project).load()) != edit_sha:
        raise EditError('ต้องตรวจวิดีโอรุ่นปัจจุบันก่อนสร้างชุดส่งออก')
    if any(record.get('research_manifest_sha256') != research_sha
           for record in (render, timeline, receipt, script, decision)):
        raise EditError('รีเสิร์ชเปลี่ยนแล้ว ต้องตรวจวิดีโอรุ่นใหม่ก่อนส่งออก')
    if (any(record.get('edit_sha256') != edit_sha for record in (render, timeline, receipt, decision))
            or qa.get('sha256') != master_sha or qa.get('passed') is not True
            or qa.get('full_decode_checked') is not True or qa.get('issues') != []
            or render.get('technical_qa') != qa
            or receipt.get('master_sha256') != master_sha or receipt.get('technical_qa_passed') is not True
            or timeline.get('script_review') != script
            or decision.get('master_sha256') != master_sha or decision.get('editorial_review') != 'USER_APPROVED'):
        raise EditError('ผลตรวจและไฟล์วิดีโอไม่ตรงกัน ต้องเรนเดอร์และตรวจใหม่')
    return render, decision, files, script


def verify_delivery(project):
    """Read-only local validation. Remote verification is a separate explicit action."""
    ref = project.read().get('active_delivery_asset')
    if not ref:
        raise EditError('ยังไม่มีชุดส่งออกที่ลงทะเบียน กรุณาสร้างชุดส่งออกก่อน')
    delivery = read_json(asset_file(project, ref, 'timeline'))
    render, decision, files, script = current_reviewed_render(project)
    expected = {
        'project_id': project.read()['project_id'], 'package_kind': 'REVIEWED_LOCAL_DRAFT',
        'master': render['registered']['preview.mp4'], 'edit_sha256': render['edit_sha256'],
        'research_manifest_sha256': render['research_manifest_sha256'],
        'registered': render['registered'], 'editorial_review': decision,
        'script_review_ready': script.get('ready') is True,
    }
    if any(delivery.get(key) != value for key, value in expected.items()):
        raise EditError('ชุดส่งออกเป็นคนละรุ่นกับวิดีโอที่ตรวจล่าสุด กรุณาสร้างชุดใหม่')
    package = asset_file(project, delivery['package'], 'exports')
    entries = {'documentary.mp4' if name == 'preview.mp4' else name: digest(path) for name, path in files.items()}
    review_bytes = (json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True)+'\n').encode('utf-8')
    entries['editorial-review.json'] = {'size': len(review_bytes), 'sha256': hashlib.sha256(review_bytes).hexdigest()}
    try:
        with ZipFile(package) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)) or set(names) != set(entries):
                raise EditError('รายการไฟล์ใน ZIP ไม่ตรงกับชุดส่งออก')
            for name, expected_file in entries.items():
                if bundle.getinfo(name).file_size != expected_file['size']:
                    raise EditError('ขนาดไฟล์ใน ZIP ไม่ตรง: '+name)
                sha = hashlib.sha256()
                with bundle.open(name) as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b''):
                        sha.update(chunk)
                if sha.hexdigest() != expected_file['sha256']:
                    raise EditError('เนื้อหาไฟล์ใน ZIP ไม่ตรง: '+name)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise EditError('ตรวจชุดส่งออกไม่สำเร็จ: '+str(exc)) from exc
    return {**delivery, 'record': ref, 'local_package_verified': True,
            'verification_scope': 'Exact local draft bytes and current edit/research review; no live Drive check.',
            'documentary_completed': False}


def deliver_project(project, *, drive=None):
    """Upload the project including rejected media; prove this exact draft was included."""
    before = verify_delivery(project)
    project.sync(drive)
    # Recheck after transfer: edit/research/export may have changed while checkpointing.
    with project._lock():
        after = verify_delivery(project)
        if before['record'] != after['record']:
            raise EditError('ชุดส่งออกเปลี่ยนระหว่างอัปโหลด กรุณาส่งรุ่นใหม่อีกครั้ง')
        data = project.read()
        if data['storage_status'] != 'VERIFIED':
            raise StorageError('Project storage changed after transfer; retry delivery')
        assets = {a['path']: a for a in data['assets']}
        receipts = {}
        for label, ref in (('package', after['package']), ('master', after['master']), ('record', after['record'])):
            asset = assets.get(ref['path'])
            receipt = asset.get('drive_file') if asset else None
            if (not asset or asset['sha256'] != ref['sha256'] or asset['upload_status'] != 'VERIFIED'
                    or not receipt or not receipt.get('id') or receipt.get('md5') != asset['md5']
                    or receipt.get('size') != asset['size']):
                raise StorageError('Missing exact Drive verification receipt: '+label)
            receipts[label] = receipt
        result = {**after, 'drive_status': 'VERIFIED', 'drive_receipts': receipts,
                  'verified_at': datetime.now(timezone.utc).isoformat(),
                  'storage_snapshot': data['last_snapshot'],
                  'verification_scope': 'Draft bytes verified locally; Drive adapter checked ID, MD5 and size during this delivery.',
                  'documentary_completed': False,
                  'completion_blocker': 'Canonical production and final release integration remain required.'}
        atomic_json(project.root/'delivery_verification.json', result)
        return result
