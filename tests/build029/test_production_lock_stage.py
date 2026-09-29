from pathlib import Path
import pytest

from gmk_review import HTMLReviewRuntime
from gmk_production import ProductionLockStageRuntime, ProductionLockStageError
from gmk_runtime.cold_start import ColdStartLoader
from tests.build028.test_html_review_runtime import _shot_ready

ROOT=Path(__file__).resolve().parents[2]


def _html_approved(tmp_path):
    ws=_shot_ready(tmp_path)
    r=HTMLReviewRuntime(ROOT,ws)
    r.prepare()
    r.decide({'actor_id':'scene_reviewer','decision':'APPROVED'})
    return ws


def test_production_lock_prepare_creates_exact_review_closure(tmp_path):
    ws=_html_approved(tmp_path)
    out=ProductionLockStageRuntime(ROOT,ws).prepare()
    assert out.project_state=='HTML_APPROVED'
    assert out.scene_count==1 and out.shot_count==1
    assert out.gate_result=='FAIL' and out.transitioned is False
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    pkg=state.artifacts[(out.review_package_ref['artifact_id'],out.review_package_ref['version'])]
    assert pkg['artifact_type']=='PRODUCTION_LOCK_REVIEW_PACKAGE'
    assert pkg['closure_sha256']==out.closure_sha256
    assert pkg['review_summary']['shot_count']==1


def test_production_lock_human_approval_builds_locks_and_transitions(tmp_path):
    ws=_html_approved(tmp_path);r=ProductionLockStageRuntime(ROOT,ws);r.prepare()
    out=r.decide({'actor_id':'production_owner','decision':'APPROVED'})
    assert out.project_state=='PRODUCTION_RENDER'
    assert out.transitioned is True and out.gate_result=='PASS'
    assert len(out.scene_lock_refs)==1 and out.project_lock_ref
    assert out.shot_visual_approval_count==1
    assert out.production_lock_approval_count==2
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    locks=[a for a in state.artifacts.values() if a.get('artifact_type')=='PRODUCTION_LOCK_MANIFEST']
    assert {x['scope']['type'] for x in locks}=={'SCENE','PROJECT'}


def test_production_lock_rejection_is_durable_and_does_not_create_lock(tmp_path):
    ws=_html_approved(tmp_path);r=ProductionLockStageRuntime(ROOT,ws);r.prepare()
    first=r.decide({'actor_id':'production_owner','decision':'REJECTED'})
    second=r.decide({'actor_id':'production_owner','decision':'REJECTED'})
    assert first.project_state=='HTML_APPROVED' and first.gate_result=='FAIL'
    assert second.idempotent_replay is True
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    assert not [a for a in state.artifacts.values() if a.get('artifact_type')=='PRODUCTION_LOCK_MANIFEST']


def test_production_lock_approved_replay_is_idempotent(tmp_path):
    ws=_html_approved(tmp_path);r=ProductionLockStageRuntime(ROOT,ws);r.prepare()
    first=r.decide({'actor_id':'production_owner','decision':'APPROVED'})
    second=r.decide({'actor_id':'production_owner','decision':'APPROVED'})
    assert first.project_state=='PRODUCTION_RENDER'
    assert second.project_state=='PRODUCTION_RENDER' and second.idempotent_replay is True
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    locks=[a for a in state.artifacts.values() if a.get('artifact_type')=='PRODUCTION_LOCK_MANIFEST']
    assert len(locks)==2


def test_production_lock_prepare_rejects_wrong_state(tmp_path):
    ws=_shot_ready(tmp_path)
    with pytest.raises(ProductionLockStageError,match='PRODUCTION_LOCK_STATE_INVALID'):
        ProductionLockStageRuntime(ROOT,ws).prepare()
