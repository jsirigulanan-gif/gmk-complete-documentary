from pathlib import Path
import pytest
from gmk_planning import ShotPlanRuntime
from gmk_review import HTMLReviewRuntime, HTMLReviewRuntimeError
from gmk_runtime.cold_start import ColdStartLoader
from tests.build027.test_shot_plan_runtime import _scene_ready

ROOT=Path(__file__).resolve().parents[2]


def _shot_ready(tmp_path):
    ws=_scene_ready(tmp_path,True)
    ShotPlanRuntime(ROOT,ws).run()
    return ws


def test_html_review_prepare_creates_real_html_preview_and_enters_review(tmp_path):
    ws=_shot_ready(tmp_path)
    out=HTMLReviewRuntime(ROOT,ws).prepare()
    assert out.project_state=='HTML_REVIEW'
    assert out.preview_count==1 and out.review_package_count==1
    assert out.gate_result=='FAIL' and out.transitioned is True
    s=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    pv=next(a for a in s.artifacts.values() if a.get('artifact_type')=='SCENE_PREVIEW')
    html=ws/pv['preview']['workspace_path']
    assert html.is_file() and '<article class="shot">' in html.read_text(encoding='utf-8')


def test_html_review_human_approval_transitions_only_after_approval(tmp_path):
    ws=_shot_ready(tmp_path); r=HTMLReviewRuntime(ROOT,ws); r.prepare()
    out=r.decide({'actor_id':'human_reviewer','decision':'APPROVED'})
    assert out.project_state=='HTML_APPROVED'
    assert out.approved_count==out.preview_count==1
    assert out.gate_result=='PASS' and out.transitioned is True


def test_html_review_rejection_remains_in_review_and_replay_is_idempotent(tmp_path):
    ws=_shot_ready(tmp_path); r=HTMLReviewRuntime(ROOT,ws); first=r.prepare(); second=r.prepare()
    assert second.idempotent_replay is True and second.project_state=='HTML_REVIEW'
    rej=r.decide({'actor_id':'human_reviewer','decision':'REJECTED'})
    assert rej.project_state=='HTML_REVIEW' and rej.gate_result=='FAIL' and not rej.transitioned
    again=r.decide({'actor_id':'human_reviewer','decision':'REJECTED'})
    assert again.idempotent_replay is True


def test_html_review_rejects_wrong_state(tmp_path):
    ws=_scene_ready(tmp_path,True)
    with pytest.raises(HTMLReviewRuntimeError,match='HTML_REVIEW_STATE_INVALID'):
        HTMLReviewRuntime(ROOT,ws).prepare()
