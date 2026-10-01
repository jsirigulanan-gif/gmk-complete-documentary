import pytest

from gmk_projects.storage import Project, StorageError
from tests.build049.test_edit_checkpoint import DriveFixture


@pytest.mark.parametrize('bad', [None, {'id': ''}, {'md5': 'wrong'}, {'size': -1}])
def test_manifest_snapshot_requires_its_own_matching_drive_receipt(tmp_path, bad):
    project = Project.create(tmp_path, 'Snapshot receipt')
    class InvalidSnapshotDrive(DriveFixture):
        def put(self, local, path, expected):
            good = super().put(local, path, expected)
            if '/manifests/' in path:
                return None if bad is None else {**good, **bad}
            return good
    with pytest.raises(StorageError, match='matching'):
        project.sync(InvalidSnapshotDrive())
    state = project.read()
    assert state['storage_status'] == 'UPLOAD_FAILED'
    assert not state.get('last_snapshot')
