from pathlib import Path
import pytest

from gmk_release import DeliveryStageRuntime, DeliveryStageError
from gmk_release.runtime import ReleaseRuntime
from gmk_qa import FullFilmQAStageRuntime
from gmk_runtime.cold_start import ColdStartLoader
from tests.build032.test_full_film_qa_stage import _scene_qa_passed, _plan as _ff_plan

ROOT=Path(__file__).resolve().parents[2]


def _patch_profile(monkeypatch):
    def fake(self,config_id='GMK_TEST_320'):
        data={
            'config_id':'GMK_TEST_320','version':'1.0.0','schema_version':'1.0.0',
            'video':{'width':320,'height':180,'allowed_codecs':['h264'],'min_duration_seconds':0.1},
            'audio':{'required':False},'metadata':{'required_fields':['title','description']},
            'release':{'required_destinations':['PRIMARY'],'optional_destinations':[]},
        }
        return data,{'config_id':'GMK_TEST_320','version':'1.0.0','sha256':'a'*64}
    monkeypatch.setattr(ReleaseRuntime,'load_delivery_profile',fake)


def _full_film_ready(tmp_path):
    ws=_scene_qa_passed(tmp_path)
    out=FullFilmQAStageRuntime(ROOT,ws).run(_ff_plan(batch='B033_FF'))
    assert out.project_state=='FULL_FILM_QA_PASSED'
    return ws


def _prepare_plan(batch='B033_PREPARE',metadata=None):
    return {'batch_id':batch,'profile_id':'GMK_TEST_320','metadata':metadata or {'title':'P.T.','description':'Delivery test'}}


def _approve():
    return {'actor_id':'delivery_owner','decision':'APPROVED','checks':{
        'package_integrity':'PASS','provenance_complete':'PASS','rights_ready':'PASS','metadata_ready':'PASS','destination_ready':'PASS'}}


def test_delivery_prepare_builds_exact_candidate_without_transition(tmp_path,monkeypatch):
    _patch_profile(monkeypatch);ws=_full_film_ready(tmp_path)
    out=DeliveryStageRuntime(ROOT,ws).prepare(_prepare_plan())
    assert out.project_state=='FULL_FILM_QA_PASSED' and out.delivery_gate=='PASS'
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    pkg=state.artifacts[(out.review_package_ref['artifact_id'],out.review_package_ref['version'])]
    assert pkg['artifact_type']=='DELIVERY_REVIEW_PACKAGE'
    assert pkg['delivery_package']==out.delivery_package_ref and pkg['delivery_qa']==out.delivery_qa_ref
    assert pkg['review_summary']['delivery_qa_result']=='PASS'


def test_delivery_human_approval_enters_delivery_ready(tmp_path,monkeypatch):
    _patch_profile(monkeypatch);ws=_full_film_ready(tmp_path);runtime=DeliveryStageRuntime(ROOT,ws);runtime.prepare(_prepare_plan())
    out=runtime.decide(_approve())
    assert out.project_state=='DELIVERY_READY' and out.transitioned is True and out.delivery_gate=='PASS'
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot();ap=state.objects[(out.approval_ref['id'],out.approval_ref['version'])]
    assert ap['approval_class']=='RELEASE' and ap['decision']=='APPROVED'
    rc=state.artifacts[(ap['review_context']['artifact_id'],ap['review_context']['version'])]
    assert rc['artifact_type']=='DELIVERY_REVIEW_PACKAGE'


def test_delivery_reject_stays_full_film_qa_passed(tmp_path,monkeypatch):
    _patch_profile(monkeypatch);ws=_full_film_ready(tmp_path);runtime=DeliveryStageRuntime(ROOT,ws);runtime.prepare(_prepare_plan())
    out=runtime.decide({'actor_id':'delivery_owner','decision':'REJECTED'})
    assert out.project_state=='FULL_FILM_QA_PASSED' and out.transitioned is False


def test_delivery_prepare_replay_is_idempotent(tmp_path,monkeypatch):
    _patch_profile(monkeypatch);ws=_full_film_ready(tmp_path);runtime=DeliveryStageRuntime(ROOT,ws);plan=_prepare_plan()
    first=runtime.prepare(plan);second=runtime.prepare(plan)
    assert second.idempotent_replay is True and second.review_package_ref==first.review_package_ref and second.delivery_package_ref==first.delivery_package_ref


def test_delivery_approval_requires_explicit_human_checks(tmp_path,monkeypatch):
    _patch_profile(monkeypatch);ws=_full_film_ready(tmp_path);runtime=DeliveryStageRuntime(ROOT,ws);runtime.prepare(_prepare_plan())
    bad=_approve();bad['checks'].pop('destination_ready')
    with pytest.raises(DeliveryStageError,match='DELIVERY_HUMAN_CHECKS_INCOMPLETE'):
        runtime.decide(bad)
    assert ColdStartLoader(ROOT,ws).load().engine.project_state=='FULL_FILM_QA_PASSED'
