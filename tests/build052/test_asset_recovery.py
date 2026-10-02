import pytest

from gmk_projects.storage import Project, StorageError
from gmk_projects.edit import asset_file


def test_reimport_restores_exact_missing_asset_without_duplicate_or_lost_refs(tmp_path):
    p=Project.create(tmp_path,'Recovery check')
    source=tmp_path/'original.bin';source.write_bytes(b'Original registered footage')
    asset=p.add_file(source,'footage',scenes=['SCENE-1'],source_url='https://example.com/original')
    (p.root/asset['path']).unlink()
    restored=p.add_file(source,'footage',scenes=['SCENE-2'])
    assert asset_file(p,restored,'footage').read_bytes()==source.read_bytes()
    assert restored['path']==asset['path'] and len(p.read()['assets'])==1
    assert restored['scene_ids']==['SCENE-1','SCENE-2']
    assert restored['source_urls']==['https://example.com/original']


def test_reimport_rejects_changed_registered_bytes_without_overwriting_them(tmp_path):
    p=Project.create(tmp_path,'Changed asset check')
    source=tmp_path/'original.bin';source.write_bytes(b'Original registered bytes')
    asset=p.add_file(source,'footage')
    local=p.root/asset['path'];local.write_bytes(b'Changed local bytes')
    before=p.read()
    with pytest.raises(StorageError,match='changed'):
        p.add_file(source,'footage')
    assert local.read_bytes()==b'Changed local bytes' and p.read()==before
