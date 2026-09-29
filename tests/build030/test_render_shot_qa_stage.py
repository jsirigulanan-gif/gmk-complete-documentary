from pathlib import Path
import subprocess
import pytest

from gmk_production import ProductionLockStageRuntime
from gmk_render import RenderQAStageRuntime, RenderQAStageError
from gmk_runtime.cold_start import ColdStartLoader
from tests.build029.test_production_lock_stage import _html_approved

ROOT=Path(__file__).resolve().parents[2]


def _production_render(tmp_path):
    ws=_html_approved(tmp_path)
    r=ProductionLockStageRuntime(ROOT,ws);r.prepare();out=r.decide({'actor_id':'production_owner','decision':'APPROVED'})
    assert out.project_state=='PRODUCTION_RENDER'
    return ws


def _video(tmp_path,name='master.mp4'):
    path=tmp_path/name
    p=subprocess.run([
        'ffmpeg','-y','-loglevel','error','-f','lavfi','-i','color=c=black:s=320x180:r=24:d=0.6',
        '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-shortest','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)
    ],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    return path


def _shot_ids(ws):
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot();out=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='SHOT' and e.active_version is not None: out.append(oid)
    return sorted(out)


def _plan(ws,video,batch='B030_HAPPY',findings=None):
    return {
        'batch_id':batch,'render_file':str(video),'reviewer_id':'qa_reviewer','reviewed_at':'2026-09-28T03:00:00Z',
        'shot_reviews':[{'shot_id':sid,'findings':list(findings or [])} for sid in _shot_ids(ws)],
    }


def test_render_shot_qa_happy_path_uses_real_video_and_advances(tmp_path):
    ws=_production_render(tmp_path);video=_video(tmp_path)
    out=RenderQAStageRuntime(ROOT,ws).run(_plan(ws,video))
    assert out.project_state=='SHOT_QA_PASSED'
    assert out.render_gate==out.shot_qa_gate=='PASS' and out.transitioned is True
    assert len(out.qa_report_refs)==len(_shot_ids(ws)) and out.qa_baseline_ref
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    render=state.artifacts[(out.render_output_ref['artifact_id'],out.render_output_ref['version'])]
    assert render['technical']['width']==320 and render['technical']['height']==180
    assert render['technical']['audio_present'] is True
    assert (ws/'reviews'/'shot_qa'/'B030_HAPPY.json').is_file()
    assert (ws/'media'/'renders').is_dir()


def test_render_shot_qa_requires_explicit_review_for_every_active_shot(tmp_path):
    ws=_production_render(tmp_path);video=_video(tmp_path)
    plan=_plan(ws,video);plan['shot_reviews']=[]
    with pytest.raises(RenderQAStageError,match='SHOT_QA_REVIEW_COVERAGE_INCOMPLETE'):
        RenderQAStageRuntime(ROOT,ws).run(plan)
    assert ColdStartLoader(ROOT,ws).load().engine.project_state=='PRODUCTION_RENDER'


def test_failed_shot_qa_can_be_retested_and_latest_pass_unblocks_gate(tmp_path):
    ws=_production_render(tmp_path);video=_video(tmp_path)
    finding={'severity':'MAJOR','code':'VISUAL_MISMATCH','description':'wrong frame','root_cause':{'state':'IDENTIFIED','category':'SHOT_PLAN'}}
    first=RenderQAStageRuntime(ROOT,ws).run(_plan(ws,video,batch='B030_FAIL',findings=[finding]))
    assert first.project_state=='PRODUCTION_RENDER' and first.shot_qa_gate=='FAIL' and first.transitioned is False
    second=RenderQAStageRuntime(ROOT,ws).run(_plan(ws,video,batch='B030_RETEST',findings=[]))
    assert second.project_state=='SHOT_QA_PASSED' and second.shot_qa_gate=='PASS' and second.transitioned is True
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    issues=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='QA_ISSUE' and e.active_version is not None: issues.append(state.objects[(oid,e.active_version)])
    assert issues and all(x['workflow_state']=='RESOLVED' for x in issues)


def test_render_shot_qa_replay_is_idempotent(tmp_path):
    ws=_production_render(tmp_path);video=_video(tmp_path);runtime=RenderQAStageRuntime(ROOT,ws);plan=_plan(ws,video)
    first=runtime.run(plan);second=runtime.run(plan)
    assert first.project_state=='SHOT_QA_PASSED'
    assert second.project_state=='SHOT_QA_PASSED' and second.idempotent_replay is True and second.transitioned is False
    assert second.render_output_ref==first.render_output_ref and second.qa_report_refs==first.qa_report_refs
