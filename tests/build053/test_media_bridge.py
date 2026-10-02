from copy import deepcopy
import subprocess

import pytest

from gmk_projects.edit import EditError
from gmk_projects.media_bridge import connect_media, inspect_media, _pools
from gmk_projects.media_review import review_shot
from gmk_projects.production import ProductionProject
from gmk_projects.production_bridge import _active
from tests.build051.test_production_bridge import reviewed_project, connect


@pytest.fixture
def footage(tmp_path):
    p, session, source = reviewed_project(tmp_path, count=1)
    connect(p)
    video = tmp_path/'picture.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=320x180:rate=25:duration=2',
                    '-an','-c:v','mpeg4',str(video)],check=True,capture_output=True)
    scene = session.load()['scenes'][0]['id']
    edit=session.add_shot(scene,video,.1,1.5,expected_revision=session.load()['revision'])
    shot=edit['scenes'][0]['shots'][0]['id']
    review_shot(p,scene,shot,visible_content='The synthetic frame is visible.',match_reason='Explicit fixture picture match.',
                match_type='SUPPORTING',expected_revision=edit['revision'])
    return p, session, scene, shot, video


def register(p):
    preview=inspect_media(p)
    return connect_media(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])


def test_reviewed_local_footage_registers_canonical_bytes_ranges_and_replays(footage):
    p,session,scene,shot,video=footage
    edit=session.load()
    result=register(p)
    assert result['binding']['current'] and result['production_state']=='ASSET_RECON'
    assert not result['documentary_completed'] and not result['binding']['coverage_approved']
    loaded=ProductionProject(p)._load();live=_active(loaded.engine.snapshot())
    assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
    assets=[o for o in live.values() if o['object_type']=='ASSET']
    segments=[o for o in live.values() if o['object_type']=='SEGMENT']
    assert len(assets)==len(segments)==1
    assert assets[0]['original_file']['checksum']==edit['scenes'][0]['shots'][0]['sha256']
    assert assets[0]['rights']['status']=='UNKNOWN' and assets[0]['workflow_state']=='CATALOGED'
    assert segments[0]['selector']['start_seconds']==.1 and segments[0]['selector']['end_seconds']==1.5
    assert segments[0]['production_state']=='VERIFIED' and segments[0]['match_type']=='SUPPORTING'
    assert not any(o.get('report_type')=='SEARCH_COMPLETION_CERTIFICATE' for o in live.values())
    before=loaded.manifest_sha256
    assert register(p)['idempotent_replay']
    assert ProductionProject(p)._load().manifest_sha256==before and session.load()==edit


def rows(p, scene):
    return _pools(ProductionProject(p)._load().engine.snapshot())[scene]['extensions']['project_media']['rows']


def rereview(p, session, scene, shot, match='SUPPORTING'):
    return review_shot(p,scene,shot,visible_content='Rechecked synthetic frame.',match_reason='Current explicit fixture decision.',
                       match_type=match,expected_revision=session.load()['revision'])


def test_trim_rejects_old_preview_and_review_then_versions_same_identity(footage):
    p,session,scene,shot,_=footage
    register(p); original=rows(p,scene)[0]; preview=inspect_media(p)
    before=ProductionProject(p)._load().manifest_sha256
    session.trim_shot(scene,shot,.3,1.4,expected_revision=session.load()['revision'])
    assert not inspect_media(p)['ready']
    with pytest.raises(EditError,match='เปลี่ยนหลังเปิดตรวจ'):
        connect_media(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])
    with pytest.raises(EditError,match='ยังเชื่อมภาพไม่ได้'): register(p)
    assert ProductionProject(p)._load().manifest_sha256==before
    rereview(p,session,scene,shot); assert register(p)['binding']['current']
    updated=rows(p,scene)[0]
    state=ProductionProject(p)._load().engine.snapshot()
    for key in ('asset_ref','segment_ref','result_ref'):
        assert updated[key]['id']==original[key]['id'] and updated[key]['version']>original[key]['version']
        assert (original[key]['id'],original[key]['version']) in state.objects
    # Historical exact refs remain invalidated; reconstruction must not mutate
    # records, and all newly selected current refs must remain usable.
    loaded=ProductionProject(p)._load()
    assert loaded.dependency_summary['changed_objects']==0
    live=_active(loaded.engine.snapshot())
    assert all(not live[updated[k]['id']]['stale']['is_stale'] for k in ('asset_ref','segment_ref','result_ref'))


def test_removed_and_restored_cut_preserves_identity_and_original_bytes(footage):
    p,session,scene,shot,_=footage
    register(p); original=rows(p,scene)[0]; edit=session.load(); saved=deepcopy(edit['scenes'][0]['shots'][0])
    edit['scenes'][0]['shots']=[]; session.save(edit,expected_revision=edit['revision'])
    result=register(p)
    assert result['binding']['current'] and result['binding']['asset_count']==0
    assert rows(p,scene)==[] and (p.root/saved['path']).is_file()
    state=ProductionProject(p)._load().engine.snapshot()
    assert state.objects[(original['asset_ref']['id'],original['asset_ref']['version'])]['status']=='ARCHIVED'
    edit=session.load(); edit['scenes'][0]['shots']=[saved]; session.save(edit,expected_revision=edit['revision'])
    assert register(p)['binding']['current']
    restored=rows(p,scene)[0]
    for key in ('asset_ref','segment_ref','result_ref'):
        assert restored[key]['id']==original[key]['id'] and restored[key]['version']>original[key]['version']


def test_context_footage_remains_unverified_and_does_not_grant_rights(footage):
    p,session,scene,shot,_=footage
    rereview(p,session,scene,shot,'CONTEXT'); register(p)
    live=_active(ProductionProject(p)._load().engine.snapshot())
    segment=next(o for o in live.values() if o['object_type']=='SEGMENT')
    assert segment['match_type']=='MISMATCH' and segment['production_state']=='UNVERIFIED'
    assert segment['extensions']['project_media']['editor_match_type']=='CONTEXT'
    status=ProductionProject(p).status()
    assert not status['media_binding']['coverage_approved'] and not status['media_binding']['rights_cleared']
    assert not status['documentary_completed']


def test_missing_or_changed_bytes_fail_without_persistent_mutation(footage):
    p,session,scene,shot,video=footage
    register(p); before=ProductionProject(p)._load().manifest_sha256
    stored=p.root/session.load()['scenes'][0]['shots'][0]['path']; stored.unlink()
    assert not inspect_media(p)['ready'] and not ProductionProject(p).status()['media_binding']['current']
    with pytest.raises(EditError): register(p)
    assert ProductionProject(p)._load().manifest_sha256==before
    p.add_file(video,'footage'); assert register(p)['idempotent_replay']
    stored.write_bytes(b'Changed video bytes')
    assert not inspect_media(p)['ready']
    with pytest.raises(EditError): register(p)
    assert ProductionProject(p)._load().manifest_sha256==before


def test_duplicate_cut_identity_cannot_register(footage):
    p,session,scene,shot,_=footage
    edit=session.load(); edit['scenes'][0]['shots'].append(deepcopy(edit['scenes'][0]['shots'][0]))
    session.save(edit,expected_revision=edit['revision'])
    before=ProductionProject(p)._load().manifest_sha256
    assert not inspect_media(p)['ready']
    with pytest.raises(EditError,match='รหัสช็อตซ้ำ'): register(p)
    assert ProductionProject(p)._load().manifest_sha256==before


def test_failed_publish_does_not_advance_disk_state(footage,monkeypatch):
    from gmk_projects import media_bridge
    p,session,scene,shot,_=footage
    before=ProductionProject(p)._load().manifest_sha256; edit=session.load()
    def failed(*args,**kwargs): raise OSError('Simulated publish failure')
    monkeypatch.setattr(media_bridge.RuntimeStore,'persist',failed)
    with pytest.raises(OSError,match='Simulated'): register(p)
    assert ProductionProject(p)._load().manifest_sha256==before and session.load()==edit
