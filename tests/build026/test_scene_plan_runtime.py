from pathlib import Path
import pytest

from gmk_design import DesignRuntime
from gmk_planning import ScenePlanRuntime, ScenePlanRuntimeError
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from tests.build025.test_design_runtime import _voice_locked, _plan

ROOT=Path(__file__).resolve().parents[2]


def _design_ready(tmp_path, with_visual=True):
    ws=_voice_locked(tmp_path)
    d=DesignRuntime(ROOT,ws)
    d.prepare(_plan())
    d.decide({'decision':'APPROVED','actor_id':'OWNER'})
    if not with_visual:
        return ws

    loaded=ColdStartLoader(ROOT,ws).load(); eng=loaded.engine; s=eng.snapshot()
    beat=next(o for o in s.objects.values() if o.get('object_type')=='NARRATION_BEAT')
    key=(((beat.get('extensions') or {}).get('rough_narrative') or {}).get('key')) or beat['id']
    tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
    src=tx.create_object('SOURCE',{
        'source_type':'VIDEO','title':'Fixture visual source','url':'https://example.com/fixture.mp4',
        'authority_class':'PRIMARY','independence':{'group_id':'SRCGRP_FIXTURE','relationship':'ORIGINAL'},
        'availability':{'state':'AVAILABLE'},'language':'en','accessed_at':eng.now()
    })
    search=tx.create_object('SEARCH',{
        'target_beat_ref':{'id':beat['id'],'version':beat['version']},'priority':'STANDARD','search_round':1,
        'search_pass':'EXACT_OFFICIAL','query_family':'EXACT_ENTITY','query':'fixture visual','language':'en',
        'provider':{'type':'TEST'},'trigger':{'type':'INITIAL'},'workflow_state':'COMPLETED'
    })
    result=tx.create_object('SEARCH_RESULT',{
        'search_ref':search,'discovery_method':'HUMAN_INJECTION','discovery_locator':{'type':'WEB_URI','value':'https://example.com/fixture.mp4'},
        'title':'Fixture visual','source_family':'OFFICIAL','source_ref':src,'candidate_state':'SELECTED',
        'inspection':{'visible_content':'Fixture visual evidence.','exact_moment_found':True,'candidate_locator':{'type':'FULL_SOURCE'},'match_type':'DIRECT','match_reason':'Direct fixture evidence.','viewer_takeaway_supported':True}
    })
    asset=tx.create_object('ASSET',{
        'origin_search_result_ref':result,'source_ref':src,'media_type':'VIDEO','asset_class':'EVIDENCE','workflow_state':'CATALOGED',
        'original_file':{'uri':'gmk://workspace/media/originals/fixture.mp4','checksum':'0'*64,'immutable':True},
        'rights':{'status':'CLEAR','basis':'Fixture test media.'},
        'extensions':{'asset_recon':{'beat_key':key},'asset_acquisition':{'production_ready':True}}
    })
    tx.create_object('SEGMENT',{
        'asset_ref':asset,'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.0,'end_seconds':1.0},'source_locator':{'type':'FULL_SOURCE'},
        'visual_content':'Fixture visual evidence.','match_type':'DIRECT','match_reason':'Direct fixture evidence.','production_state':'VERIFIED',
        'extensions':{'asset_acquisition':{'production_ready':True}}
    })
    tx.commit(); RuntimeStore(ROOT,ws).persist(eng)
    return ws


def test_scene_plan_creates_one_plan_per_scene_and_transitions(tmp_path):
    ws=_design_ready(tmp_path,with_visual=True)
    out=ScenePlanRuntime(ROOT,ws).run()
    assert out.project_state=='SCENE_PLAN_READY'
    assert out.scene_count==1
    assert len(out.scene_plan_refs)==1
    assert len(out.scene_asset_pool_refs)==1
    assert out.beat_count==1 and out.verified_segment_count==1
    assert out.gate_result=='PASS'
    assert out.transitioned is True
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    plan=state.artifacts[(out.scene_plan_refs[0]['artifact_id'],out.scene_plan_refs[0]['version'])]
    pool=state.artifacts[(out.scene_asset_pool_refs[0]['artifact_id'],out.scene_asset_pool_refs[0]['version'])]
    assert plan['shots']==[]
    assert plan['extensions']['scene_plan_runtime']['shot_objects_deferred_to']=='SHOT_PLAN'
    assert len(pool['beat_pools'])==1 and len(pool['beat_pools'][0]['segment_refs'])==1


def test_scene_plan_replay_is_idempotent(tmp_path):
    ws=_design_ready(tmp_path,with_visual=True)
    r=ScenePlanRuntime(ROOT,ws)
    first=r.run(); second=r.run()
    assert first.project_state=='SCENE_PLAN_READY'
    assert second.project_state=='SCENE_PLAN_READY'
    assert second.idempotent_replay is True
    assert second.scene_plan_refs==first.scene_plan_refs


def test_scene_plan_rejects_scene_beat_without_verified_segment(tmp_path):
    ws=_design_ready(tmp_path,with_visual=False)
    with pytest.raises(ScenePlanRuntimeError,match='SCENE_PLAN_VERIFIED_SEGMENT_MISSING'):
        ScenePlanRuntime(ROOT,ws).run()
