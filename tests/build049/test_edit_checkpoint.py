import json

import pytest

from gmk_projects.edit import EditSession
from gmk_projects.production import ProductionProject
from gmk_projects.storage import Project, StorageError, atomic_json


class DriveFixture:
    def __init__(self):self.files={}
    def put(self,local,path,expected):
        self.files[path]=local.read_bytes()
        return {'id':path,'size':expected['size'],'md5':expected['md5']}


def make_project(tmp_path):
    p=Project.create(tmp_path,'Checkpoint test')
    atomic_json(p.root/'script.json',{'scenes':[{'id':'SHOT-001','narration_th':'ทดสอบ'}]})
    EditSession(p).load()
    return p


def test_working_edit_is_frozen_for_sync_and_changes_mark_upload_pending(tmp_path):
    p=make_project(tmp_path);drive=DriveFixture()
    result=p.sync(drive)
    ref=result['active_edit_asset']
    archived=json.loads(drive.files[p.read()['project_id']+'/'+ref['path']])
    assert archived==EditSession(p).load()
    assert result['storage_status']=='VERIFIED'
    session=EditSession(p);data=session.load();before=data['revision']
    assert session.save(data,expected_revision=before)['revision']==before
    assert p.read()['storage_status']=='VERIFIED'
    data['scenes'][0]['title']='A revised title'
    session.save(data,expected_revision=data['revision'])
    assert p.read()['storage_status']=='PENDING_UPLOAD'


def test_edit_changed_between_checkpoint_and_transfer_rejected(tmp_path,monkeypatch):
    p=make_project(tmp_path);original=ProductionProject.checkpoint
    def edit_during_checkpoint(runtime):
        result=original(runtime)
        session=EditSession(p);data=session.load();data['scenes'][0]['title']='Changed concurrently'
        session.save(data,expected_revision=data['revision'])
        return result
    monkeypatch.setattr(ProductionProject,'checkpoint',edit_during_checkpoint)
    drive=DriveFixture()
    with pytest.raises(StorageError,match='Edit changed'):
        p.sync(drive)
    assert not drive.files
