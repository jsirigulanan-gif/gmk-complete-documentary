from pathlib import Path
import pytest
from gmk_planning import ScenePlanRuntime, ShotPlanRuntime, ShotPlanRuntimeError
from gmk_runtime.cold_start import ColdStartLoader
from tests.build026.test_scene_plan_runtime import _design_ready

ROOT=Path(__file__).resolve().parents[2]


def _scene_ready(tmp_path,with_visual=True):
    ws=_design_ready(tmp_path,with_visual=with_visual)
    if with_visual: ScenePlanRuntime(ROOT,ws).run()
    return ws


def test_shot_plan_creates_exact_objects_and_transitions(tmp_path):
    ws=_scene_ready(tmp_path,True)
    out=ShotPlanRuntime(ROOT,ws).run()
    assert out.project_state=='SHOT_PLAN_READY'
    assert out.shot_count==1 and out.layer_count==1 and out.cue_count==1
    assert out.gate_result=='PASS' and out.transitioned is True
    s=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    shot=next(o for o in s.objects.values() if o.get('object_type')=='SHOT' and o.get('status')=='CURRENT')
    layer=s.objects[(shot['layer_refs'][0]['id'],shot['layer_refs'][0]['version'])]
    cue=s.objects[(shot['cue_refs'][0]['id'],shot['cue_refs'][0]['version'])]
    assert layer['stack_role']=='BASE' and layer['content']['type']=='MEDIA_SEGMENT'
    assert cue['action']['type']=='SHOW'
    plan=s.artifacts[(out.scene_plan_refs[0]['artifact_id'],out.scene_plan_refs[0]['version'])]
    assert plan['shots']==[{'shot_ref':{'id':shot['id'],'version':shot['version']}}]


def test_shot_plan_replay_is_idempotent(tmp_path):
    ws=_scene_ready(tmp_path,True); r=ShotPlanRuntime(ROOT,ws)
    first=r.run(); second=r.run()
    assert second.idempotent_replay is True
    assert second.project_state=='SHOT_PLAN_READY'
    assert second.shot_count==first.shot_count


def test_shot_plan_rejects_wrong_state(tmp_path):
    ws=_design_ready(tmp_path,True)
    with pytest.raises(ShotPlanRuntimeError,match='SHOT_PLAN_STATE_INVALID'):
        ShotPlanRuntime(ROOT,ws).run()
