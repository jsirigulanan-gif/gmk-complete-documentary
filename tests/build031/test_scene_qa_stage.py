from pathlib import Path
import pytest

from gmk_qa import QARuntime, SceneQAStageRuntime, SceneQAStageError
from gmk_render import RenderQAStageRuntime
from gmk_runtime.cold_start import ColdStartLoader
from tests.build030.test_render_shot_qa_stage import _production_render, _video, _plan as _shot_plan

ROOT=Path(__file__).resolve().parents[2]


def _shot_qa_passed(tmp_path):
    ws=_production_render(tmp_path);video=_video(tmp_path)
    out=RenderQAStageRuntime(ROOT,ws).run(_shot_plan(ws,video,batch='B031_SHOT_QA'))
    assert out.project_state=='SHOT_QA_PASSED'
    return ws


def _scene_ids(ws):
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot();out=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='SCENE' and e.active_version is not None: out.append(oid)
    return sorted(out)


def _checks(value='PASS'):
    return {k:value for k in ('shot_continuity','visual_continuity','audio_continuity','narrative_flow','coverage')}


def _plan(ws,batch='B031_HAPPY',check_value='PASS'):
    return {
        'batch_id':batch,'reviewer_id':'scene_qa_reviewer','reviewed_at':'2026-09-28T05:00:00Z',
        'scene_reviews':[{'scene_id':sid,'checks':_checks(check_value),'findings':[]} for sid in _scene_ids(ws)],
    }


def test_scene_qa_happy_path_advances(tmp_path):
    ws=_shot_qa_passed(tmp_path)
    out=SceneQAStageRuntime(ROOT,ws).run(_plan(ws))
    assert out.project_state=='SCENE_QA_PASSED' and out.scene_qa_gate=='PASS' and out.transitioned is True
    assert len(out.scene_qa_report_refs)==len(_scene_ids(ws))
    assert (ws/'reviews'/'scene_qa'/'B031_HAPPY.json').is_file()


def test_scene_qa_requires_explicit_review_for_every_scene(tmp_path):
    ws=_shot_qa_passed(tmp_path);plan=_plan(ws);plan['scene_reviews']=[]
    with pytest.raises(SceneQAStageError,match='SCENE_QA_REVIEW_COVERAGE_INCOMPLETE'):
        SceneQAStageRuntime(ROOT,ws).run(plan)
    assert ColdStartLoader(ROOT,ws).load().engine.project_state=='SHOT_QA_PASSED'


def test_scene_qa_refuses_when_latest_shot_qa_is_not_pass(tmp_path):
    ws=_shot_qa_passed(tmp_path);loaded=ColdStartLoader(ROOT,ws).load();eng=loaded.engine;state=eng.snapshot()
    shot=None;output=None
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='SHOT' and e.active_version is not None and shot is None: shot=state.objects[(oid,e.active_version)]
    reports=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='QA_REPORT' and e.active_version is not None:
                q=state.objects[(oid,e.active_version)]
                if q.get('report_type')=='SHOT_QA' and q.get('scope')=={'id':shot['id'],'version':shot['version']}: reports.append(q)
    output=reports[-1]['observed_artifact']
    QARuntime(eng).evaluate(report_type='SHOT_QA',scope={'id':shot['id'],'version':shot['version']},observed_artifact=output,
        findings=[{'severity':'MAJOR','code':'LATE_SHOT_FAIL','description':'late failure','root_cause':{'state':'IDENTIFIED','category':'RENDERER'}}])
    from gmk_runtime.persistence import RuntimeStore
    RuntimeStore(ROOT,ws).persist(eng)
    with pytest.raises(SceneQAStageError,match='SCENE_QA_PREREQUISITE_GATE_INVALID|SCENE_QA_SHOT_QA_NOT_PASS'):
        SceneQAStageRuntime(ROOT,ws).run(_plan(ws,batch='B031_BLOCKED'))


def test_failed_scene_qa_can_be_retested_and_latest_pass_unblocks_gate(tmp_path):
    ws=_shot_qa_passed(tmp_path)
    first=SceneQAStageRuntime(ROOT,ws).run(_plan(ws,batch='B031_FAIL',check_value='FAIL'))
    assert first.project_state=='SHOT_QA_PASSED' and first.scene_qa_gate=='FAIL' and first.transitioned is False
    second=SceneQAStageRuntime(ROOT,ws).run(_plan(ws,batch='B031_RETEST',check_value='PASS'))
    assert second.project_state=='SCENE_QA_PASSED' and second.scene_qa_gate=='PASS' and second.transitioned is True
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot();issues=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='QA_ISSUE' and e.active_version is not None:
                issue=state.objects[(oid,e.active_version)]
                if issue.get('qa_domain') in {'SCENE','SCENE_QA'}: issues.append(issue)
    assert issues and all(x['workflow_state']=='RESOLVED' for x in issues)


def test_scene_qa_replay_is_idempotent(tmp_path):
    ws=_shot_qa_passed(tmp_path);runtime=SceneQAStageRuntime(ROOT,ws);plan=_plan(ws)
    first=runtime.run(plan);second=runtime.run(plan)
    assert first.project_state=='SCENE_QA_PASSED'
    assert second.project_state=='SCENE_QA_PASSED' and second.idempotent_replay is True and second.transitioned is False
    assert second.scene_qa_report_refs==first.scene_qa_report_refs
