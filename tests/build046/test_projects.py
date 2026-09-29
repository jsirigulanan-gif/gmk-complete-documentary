import hashlib
import json
from zipfile import ZipFile
from pathlib import Path
from types import SimpleNamespace

import pytest

from gmk_projects.intake import parse_script, read_source
from gmk_projects.storage import Project, ProjectAcquirer, RcloneDrive, StorageError


class MemoryDrive:
    def __init__(self):
        self.files = {}
        self.fail = False

    def put(self, local, path, expected):
        if self.fail:
            raise StorageError('quota exceeded')
        raw = local.read_bytes()
        assert hashlib.md5(raw).hexdigest() == expected['md5']
        self.files[path] = raw
        return {'id': path, 'size': len(raw), 'md5': expected['md5']}


def test_failure_retry_preserves_media_and_never_claims_success(tmp_path):
    project = Project.create(tmp_path, 'สารคดีทดสอบ')
    source = tmp_path / 'clip.mp4'
    source.write_bytes(b'real file bytes for transport test')
    a = project.add_file(source, 'footage', scenes=['SHOT-001'])
    source.write_bytes(b'edited outside project')
    drive = MemoryDrive()
    drive.fail = True
    with pytest.raises(StorageError):
        project.sync(drive)
    assert project.read()['storage_status'] == 'UPLOAD_FAILED'
    assert (project.root / a['path']).read_bytes() == b'real file bytes for transport test'
    drive.fail = False
    result = project.sync(drive)
    assert result['storage_status'] == 'VERIFIED'
    assert result['production_runtime']['state_authority'] == 'production/CURRENT_MANIFEST.json'
    count = len(drive.files)
    project.sync(drive)
    assert len(drive.files) == count
    assert all(a['upload_status'] == 'VERIFIED' for a in result['assets'])


def test_duplicate_bytes_preserve_all_scene_and_source_references(tmp_path):
    p = Project.create(tmp_path, 'test')
    s = tmp_path / 'same.mp4'
    s.write_bytes(b'one asset')
    p.add_file(s, 'footage', source_url='https://example.com/a', scenes=['SHOT-001'])
    p.add_file(s, 'footage', source_url='https://example.com/b', scenes=['SHOT-002'])
    rows = p.read()['assets']
    assert len(rows) == 1
    assert rows[0]['scene_ids'] == ['SHOT-001', 'SHOT-002']
    assert len(rows[0]['source_urls']) == 2


def test_modified_local_copy_blocks_sync(tmp_path):
    p = Project.create(tmp_path, 'test')
    s = tmp_path / 'clip.mp4'
    s.write_bytes(b'original')
    a = p.add_file(s, 'footage')
    (p.root / a['path']).write_bytes(b'changed')
    with pytest.raises(StorageError, match='changed'):
        p.sync(MemoryDrive())
    assert p.read()['storage_status'] == 'UPLOAD_FAILED'


def test_server_checksum_is_required(tmp_path, monkeypatch):
    p = tmp_path / 'clip.mp4'
    p.write_bytes(b'clip')
    drive = RcloneDrive()
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return json.dumps({'ID': 'file', 'Size': 4, 'Hashes': {'MD5': 'wrong'}})
    monkeypatch.setattr(drive, '_run', run)
    with pytest.raises(StorageError, match='verification'):
        drive.put(p, 'project/footage/clip.mp4', {'size': 4, 'md5': hashlib.md5(b'clip').hexdigest()})
    assert '--immutable' in calls[0]
    assert not any(c[0] in ('delete', 'sync', 'purge') for c in calls)


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'p/../../bad', 'p//a', 'p\\a', 'remote:bad'])
def test_reject_remote_path_escape(path):
    with pytest.raises(StorageError):
        RcloneDrive().target(path)


def test_candidate_is_archived_before_being_returned(tmp_path):
    p = Project.create(tmp_path, 'test')
    media, receipt = tmp_path / 'clip.mp4', tmp_path / 'receipt.json'
    media.write_bytes(b'candidate')
    receipt.write_text('{}')
    acquired = SimpleNamespace(local_path=media, receipt_path=receipt)
    underlying = SimpleNamespace(acquire=lambda *args: acquired)
    drive = MemoryDrive()
    acquirer = ProjectAcquirer(p, underlying, drive)
    result = acquirer.acquire(SimpleNamespace(webpage_url='https://example.com/video'), tmp_path)
    assert result is acquired
    assert p.read()['storage_status'] == 'VERIFIED'
    assert {a['role'] for a in p.read()['assets']} == {'research', 'footage', 'timeline'}


def test_intake_preserves_links_and_does_not_trust_verified(tmp_path):
    text = ('Example\n100% VERIFIED\nSHOT-001 | Opening Duration: 00:00 - 01:00\n'
            'VISUAL: ภาพเมือง\nAUDIO: เพลง\nเรื่องเล่าภาษาไทย\nEnglish narration.\n'
            'Master Media Asset Library\nsource list')
    doc = {'body': {'content': [{'paragraph': {'elements': [{'textRun': {
        'content': text, 'textStyle': {'link': {'url': 'https://example.com/evidence'}}}}]}}]}}
    path = tmp_path / 'source.json'
    path.write_text(json.dumps(doc))
    parsed = parse_script(*read_source(path))
    assert len(parsed['scenes']) == 1
    assert parsed['scenes'][0]['narration_th'] == 'เรื่องเล่าภาษาไทย'
    assert parsed['scenes'][0]['narration_en'] == 'English narration.'
    assert parsed['source_links'][0]['url'] == 'https://example.com/evidence'
    assert parsed['fact_check_status'] == 'NOT_CHECKED'
    assert parsed['scenes'][0]['timing_status'] == 'PLANNED_ONLY'


def test_duplicate_scene_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        parse_script('SHOT-001 | A\nhello\nSHOT-001 | B\nworld', [])


def test_docx_import_keeps_hyperlinks(tmp_path):
    p = tmp_path/'research.docx'
    with ZipFile(p, 'w') as archive:
        archive.writestr('word/document.xml', '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>Research title</w:t></w:r></w:p><w:p><w:hyperlink r:id="r1"><w:r><w:t>Evidence</w:t></w:r></w:hyperlink></w:p></w:body></w:document>''')
        archive.writestr('word/_rels/document.xml.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="https://example.com/evidence" TargetMode="External"/></Relationships>''')
    text, links = read_source(p)
    assert text == 'Research title\nEvidence'
    assert links == [{'text': 'Evidence', 'url': 'https://example.com/evidence'}]
