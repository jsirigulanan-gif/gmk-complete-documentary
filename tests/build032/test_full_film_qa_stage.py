from pathlib import Path
import pytest

from gmk_qa import FullFilmQAStageRuntime, FullFilmQAStageError
from gmk_runtime.cold_start import ColdStartLoader
from tests.build031.test_scene_qa_stage import _shot_qa_passed, _plan as _scene_plan
from gmk_qa import SceneQAStageRuntime

ROOT=Path(__file__).resolve().parents[2]


def _scene_qa_passed(tmp_path):
    ws=_shot_qa_passed(tmp_path)
    out=SceneQAStageRuntime(ROOT,ws).run(_scene_plan(ws,batch='B032_SCENE_QA'))
    assert out.project_state=='SCENE_QA_PASSED'
    return ws


def _checks(keys,value='PASS'):
    return {k:value for k in keys}


def _plan(batch='B032_HAPPY',value='PASS'):
    return {
        'batch_id':batch,'reviewer_id':'full_film_reviewer','reviewed_at':'2026-09-28T07:00:00Z',
        'viewer_experience':{'checks':_checks(('narrative_clarity','pacing','engagement','comprehension','emotional_coherence'),value),'findings':[]},
        'production_integrity':{'checks':_checks(('scene_continuity','visual_consistency','audio_consistency','timing_sync','locked_decision_integrity'),value),'findings':[]},
        'delivery_integrity':{'checks':_checks(('playback_integrity','frame_integrity','audio_integrity','duration_integrity','output_completeness'),value),'findings':[]},
    }


def test_full_film_qa_happy_path_advances(tmp_path):
    ws=_scene_qa_passed(tmp_path)
    out=FullFilmQAStageRuntime(ROOT,ws).run(_plan())
    assert out.project_state=='FULL_FILM_QA_PASSED' and out.full_film_qa_gate=='PASS' and out.transitioned is True
    assert set(out.pass_report_refs)=={'viewer','production','delivery_integrity'}
    assert (ws/'reviews'/'full_film_qa'/'B032_HAPPY.json').is_file()


def test_full_film_qa_requires_all_explicit_checks(tmp_path):
    ws=_scene_qa_passed(tmp_path);plan=_plan();del plan['viewer_experience']['checks']['engagement']
    with pytest.raises(FullFilmQAStageError,match='FULL_FILM_QA_CHECK_INVALID'):
        FullFilmQAStageRuntime(ROOT,ws).run(plan)
    assert ColdStartLoader(ROOT,ws).load().engine.project_state=='SCENE_QA_PASSED'


def test_full_film_qa_fail_then_retest_pass_resolves_issues(tmp_path):
    ws=_scene_qa_passed(tmp_path)
    first=FullFilmQAStageRuntime(ROOT,ws).run(_plan(batch='B032_FAIL',value='FAIL'))
    assert first.project_state=='SCENE_QA_PASSED' and first.full_film_qa_gate=='FAIL' and first.transitioned is False
    second=FullFilmQAStageRuntime(ROOT,ws).run(_plan(batch='B032_RETEST',value='PASS'))
    assert second.project_state=='FULL_FILM_QA_PASSED' and second.full_film_qa_gate=='PASS' and second.transitioned is True
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot();issues=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='QA_ISSUE' and e.active_version is not None:
                x=state.objects[(oid,e.active_version)]
                if x.get('qa_domain') in {'VIEWER_EXPERIENCE','PRODUCTION_INTEGRITY','DELIVERY_INTEGRITY'}:issues.append(x)
    assert issues and all(x['workflow_state']=='RESOLVED' for x in issues)


def test_full_film_qa_replay_is_idempotent(tmp_path):
    ws=_scene_qa_passed(tmp_path);runtime=FullFilmQAStageRuntime(ROOT,ws);plan=_plan()
    first=runtime.run(plan);second=runtime.run(plan)
    assert first.project_state=='FULL_FILM_QA_PASSED'
    assert second.project_state=='FULL_FILM_QA_PASSED' and second.idempotent_replay is True and second.transitioned is False
    assert second.full_film_report_ref==first.full_film_report_ref and second.full_film_package_ref==first.full_film_package_ref


def test_full_film_qa_refuses_before_scene_qa_passed(tmp_path):
    ws=_shot_qa_passed(tmp_path)
    with pytest.raises(FullFilmQAStageError,match='FULL_FILM_QA_STATE_INVALID'):
        FullFilmQAStageRuntime(ROOT,ws).run(_plan(batch='B032_TOO_EARLY'))
