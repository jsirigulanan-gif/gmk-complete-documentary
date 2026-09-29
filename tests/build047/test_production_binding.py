import json
import shutil
from zipfile import ZipFile

import pytest

from gmk_projects.intake import import_research
from gmk_projects.production import ProductionProject
from gmk_projects.storage import Project, StorageError, atomic_json, digest
from gmk_runtime.cold_start import ColdStartLoader


def test_new_project_has_one_persistent_authority(tmp_path):
    p = Project.create(tmp_path, 'A documentary')
    before = ProductionProject(p).status()
    assert before['production_state'] == 'BOOTSTRAPPED'
    assert before['connected']
    assert 'production_status' not in p.read()
    after = ProductionProject(Project(p.root)).initialize()
    assert before['manifest_sha256'] == after['manifest_sha256']
    assert not after['documentary_completed']


def test_import_registers_source_and_does_not_audit_claims(tmp_path):
    p = Project.create(tmp_path, 'A documentary')
    source = tmp_path/'source.txt'
    source.write_text('Research\n100% VERIFIED\nSHOT-001 | Opening\nVISUAL: City\nAUDIO: Music\nเรื่องเล่า\n', encoding='utf-8')
    import_research(p, source)
    runtime = ProductionProject(p)
    first = runtime.status()
    assert first['production_state'] == 'RESEARCH_INTAKE'
    assert first['research_pack_count'] == 1
    assert not first['documentary_completed']
    import_research(p, source)
    assert runtime.status()['manifest_sha256'] == first['manifest_sha256']
    assert json.loads((p.root/'script.json').read_text())['fact_check_status'] == 'NOT_CHECKED'


def test_old_project_migration_retains_assets_and_can_be_repeated(tmp_path):
    p = Project(tmp_path/'old-project')
    (p.root/'research').mkdir(parents=True)
    src = p.root/'research'/'source.txt'
    src.write_text('Original research')
    meta = digest(src)
    original = {'path': 'research/source.txt', 'role': 'research', 'original_name': 'source.txt',
                **meta, 'source_urls': [], 'scene_ids': [], 'upload_status': 'PENDING', 'drive_file': None}
    atomic_json(p.manifest, {'project_id': 'old-project', 'title': 'Old documentary',
                            'production_status': 'RESEARCH_INTAKE', 'assets': [original],
                            'storage_status': 'LOCAL_ONLY'})
    runtime = ProductionProject(p)
    assert runtime.status()['production_state'] == 'NOT_CONNECTED'
    before = p.manifest.read_bytes()
    runtime.status()
    assert p.manifest.read_bytes() == before  # Status does not migrate on read.
    first = runtime.connect_existing()
    second = runtime.connect_existing()
    assert first['manifest_sha256'] == second['manifest_sha256']
    assert second['production_state'] == 'RESEARCH_INTAKE'
    assert p.read()['assets'] == [original]
    assert src.read_text() == 'Original research'


def test_corrupted_core_cannot_be_reinitialized_or_checkpointed(tmp_path):
    p = Project.create(tmp_path, 'A documentary')
    runtime = ProductionProject(p)
    pointer = runtime.workspace/'CURRENT_MANIFEST.json'
    pointer.unlink()
    with pytest.raises(StorageError, match='missing'):
        runtime.initialize()
    with pytest.raises(StorageError, match='missing'):
        runtime.status()
    with pytest.raises(Exception):
        runtime.checkpoint()
    assert p.read()['assets'] == []


def test_foreign_project_workspace_rejected_even_with_same_title_and_object_ids(tmp_path):
    a, b = Project.create(tmp_path, 'Same title'), Project.create(tmp_path, 'Same title')
    shutil.rmtree(b.root/'production')
    shutil.copytree(a.root/'production', b.root/'production')
    with pytest.raises(StorageError, match='different Drive project'):
        ProductionProject(b).status()


def test_checkpoint_is_repeatable_and_reconstructs_core(tmp_path):
    p = Project.create(tmp_path, 'A documentary')
    runtime = ProductionProject(p)
    a, b = runtime.checkpoint(), runtime.checkpoint()
    assert a == b
    assert len(p.read()['assets']) == 1
    # Trusted archive produced by this test, not an arbitrary user ZIP.
    restored = tmp_path/'restored'
    with ZipFile(p.root/a['asset_path']) as archive:
        archive.extractall(restored)
    from gmk_projects.production import RUNTIME_ROOT
    result = ColdStartLoader(RUNTIME_ROOT, restored).load()
    assert result.manifest_sha256 == runtime.status()['manifest_sha256']


def test_storage_flag_does_not_override_production_state(tmp_path):
    p = Project.create(tmp_path, 'A documentary')
    data = p.read()
    data.update(storage_status='VERIFIED', production_status='PROJECT_COMPLETED')
    atomic_json(p.manifest, data)
    result = ProductionProject(p).status()
    assert result['production_state'] == 'BOOTSTRAPPED'
    assert result['documentary_completed'] is False


def test_checkpoint_rejects_changed_research_input(tmp_path):
    p = Project.create(tmp_path, 'A documentary')
    src = tmp_path/'source.txt'
    src.write_text('Research source')
    import_research(p, src)
    runtime = ProductionProject(p)
    copied = next((runtime.workspace/'inputs'/'research').iterdir())
    copied.write_text('Changed source after registration')
    with pytest.raises(StorageError, match='checksum mismatch'):
        runtime.checkpoint()


def test_core_change_between_checkpoint_and_sync_does_not_claim_current_backup(tmp_path, monkeypatch):
    p = Project.create(tmp_path, 'A documentary')
    src = tmp_path/'source.txt'
    src.write_text('New source')
    original = ProductionProject.checkpoint
    def concurrent_edit(runtime):
        result = original(runtime)
        import_research(p, src)
        return result
    monkeypatch.setattr(ProductionProject, 'checkpoint', concurrent_edit)
    class NoTransfer:
        def put(self, *args):
            pytest.fail('Must not upload an obsolete checkpoint as the current backup')
    with pytest.raises(StorageError, match='changed while checkpointing'):
        p.sync(NoTransfer())
    assert p.read()['storage_status'] != 'VERIFIED'
