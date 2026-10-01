import json
from zipfile import ZipFile

import pytest

from gmk_projects.delivery import deliver_project, verify_delivery
from gmk_projects.edit import EditError, asset_file, media_ref
from gmk_projects.render import approve_editorial_review, export_delivery, render_project
from gmk_projects.storage import Project, StorageError, atomic_json
from tests.build049.test_edit_render import setup
from tests.build049.test_edit_checkpoint import DriveFixture


@pytest.fixture
def exported(setup):
    project, session, *_ = setup
    render = render_project(project)
    approve_editorial_review(project, expected_master_sha256=render['technical_qa']['sha256'])
    package = export_delivery(project)
    return project, session, package


def test_deterministic_export_and_exact_draft_drive_delivery(exported):
    p, _, first = exported
    again = export_delivery(p)
    assert first == again  # ZIP metadata and review serialization are stable.
    checked = verify_delivery(p)
    assert checked['local_package_verified'] and not checked['documentary_completed']
    assert not checked['script_review_ready']  # Synthetic fixture has no reviewed claims.
    drive = DriveFixture()
    result = deliver_project(p, drive=drive)
    assert result['drive_status'] == 'VERIFIED'
    assert not result['documentary_completed']
    assert result['package_kind'] == 'REVIEWED_LOCAL_DRAFT'
    uploaded = drive.files[p.read()['project_id']+'/'+first['package']['path']]
    assert uploaded == asset_file(p, first['package']).read_bytes()
    snapshot = json.loads(drive.files[result['storage_snapshot']['id']])
    assert snapshot['active_delivery_asset'] == result['record']
    assert set(result['drive_receipts']) == {'package', 'master', 'record'}


@pytest.mark.parametrize('mutation', ['review', 'qa'])
def test_mutable_summary_cannot_override_archived_review_or_qa(exported, mutation):
    p, _, _ = exported
    path = p.root/('editorial_review.json' if mutation == 'review' else 'last_render.json')
    value = json.loads(path.read_text())
    if mutation == 'review':
        value['editorial_review'] = 'REJECTED'
    else:
        value['technical_qa']['full_decode_checked'] = False
    atomic_json(path, value)
    with pytest.raises(EditError, match='ผลตรวจ'):
        export_delivery(p)


def test_stale_draft_never_starts_transfer(exported):
    p, session, _ = exported
    data = session.load()
    data['scenes'][0]['title'] = 'New version'
    session.save(data, expected_revision=data['revision'])
    drive = DriveFixture()
    with pytest.raises(EditError, match='ปัจจุบัน'):
        deliver_project(p, drive=drive)
    assert drive.files == {}


def test_registered_zip_with_wrong_member_bytes_is_rejected(exported, tmp_path):
    p, _, delivery = exported
    wrong = tmp_path/'changed.zip'
    with ZipFile(asset_file(p, delivery['package'])) as original, ZipFile(wrong, 'w') as changed:
        for name in original.namelist():
            content = original.read(name)
            if name == 'documentary.mp4':
                content = bytes([content[0] ^ 1]) + content[1:]
            changed.writestr(name, content)
    ref = p.read()['active_delivery_asset']
    record = json.loads(asset_file(p, ref).read_text())
    record['package'] = media_ref(p.add_file(wrong, 'exports'))
    record_path = tmp_path/'changed-record.json'
    atomic_json(record_path, record)
    forged_ref = media_ref(p.add_file(record_path, 'timeline'))
    catalog = p.read()
    catalog['active_delivery_asset'] = forged_ref
    atomic_json(p.manifest, catalog)
    with pytest.raises(EditError, match='เนื้อหาไฟล์ใน ZIP'):
        verify_delivery(p)


def test_bad_adapter_receipt_cannot_mark_project_verified(exported):
    p, _, _ = exported
    class IncorrectDrive(DriveFixture):
        def put(self, local, path, expected):
            receipt = super().put(local, path, expected)
            return {**receipt, 'md5': '0'*32}
    with pytest.raises(StorageError, match='matching'):
        deliver_project(p, drive=IncorrectDrive())
    assert p.read()['storage_status'] == 'UPLOAD_FAILED'
    assert not (p.root/'delivery_verification.json').exists()


def test_failed_upload_is_retryable_without_reexport(exported):
    p, _, delivery = exported
    class InterruptedDrive(DriveFixture):
        fail = True
        def put(self, local, path, expected):
            if self.fail and path.endswith(delivery['package']['path']):
                raise StorageError('Simulated quota failure')
            return super().put(local, path, expected)
    drive = InterruptedDrive()
    with pytest.raises(StorageError, match='quota'):
        deliver_project(p, drive=drive)
    assert p.read()['storage_status'] == 'UPLOAD_FAILED'
    assert verify_delivery(p)['package'] == delivery['package']
    drive.fail = False
    result = deliver_project(p, drive=drive)
    assert result['drive_status'] == 'VERIFIED' and not result['documentary_completed']


def test_edit_after_upload_prevents_current_delivery_receipt(exported, monkeypatch):
    p, session, _ = exported
    original_sync = p.sync
    def sync_then_edit(drive):
        result = original_sync(drive)
        edit = session.load()
        edit['scenes'].reverse()
        session.save(edit, expected_revision=edit['revision'])
        return result
    monkeypatch.setattr(p, 'sync', sync_then_edit)
    with pytest.raises(EditError, match='ปัจจุบัน'):
        deliver_project(p, drive=DriveFixture())
    assert not (p.root/'delivery_verification.json').exists()


def test_missing_export_has_actionable_error_without_creating_edit(tmp_path):
    p = Project.create(tmp_path, 'No export')
    with pytest.raises(EditError, match='สร้างชุดส่งออกก่อน'):
        verify_delivery(p)
    assert not (p.root/'edit.json').exists()
