from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess

import pytest

from gmk_pilot import PilotExecutionRuntime, PilotExecutionError
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]


def _copy_pilot(tmp_path: Path) -> Path:
    ws=tmp_path/'PT_WORKSPACE'
    shutil.copytree(ROOT/'pilot'/'PT_WORKSPACE',ws)
    return ws


def _video(path: Path, seconds: float=2.2) -> None:
    subprocess.run([
        'ffmpeg','-y','-loglevel','error',
        '-f','lavfi','-i',f'color=size=320x180:rate=25:duration={seconds}',
        '-c:v','mpeg4',str(path)
    ],check=True)


def _plan(tmp_path: Path) -> dict:
    lisa=tmp_path/'lisa.mp4';tga=tmp_path/'tga.mp4'
    _video(lisa);_video(tga)
    return {
        'batch_id':'PT_MEDIA_HANDOFF_036_TEST',
        'items':[
            {
                'candidate_key':'LISA_X_DIRECT_VERIFIED','local_path':str(lisa),
                'source_url':'https://twitter.com/manfightdragon/status/1170860592233472001',
                'acquisition_method':'AUTHORIZED_TEST_FIXTURE',
                'segment':{
                    'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0},
                    'source_locator':{'type':'FULL_SOURCE'},
                    'visual_content':'Source-locked Lisa camera-hack media for isolated execution validation.',
                    'match_type':'DIRECT','match_reason':'Test bytes exercise the real source-lock/probe/range acquisition path only.'
                }
            },
            {
                'candidate_key':'TGA_VIDEO','local_path':str(tga),
                'source_url':'https://www.youtube.com/watch?v=PKl5rYdwM6c',
                'acquisition_method':'AUTHORIZED_TEST_FIXTURE',
                'segment':{
                    'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8},
                    'source_locator':{'type':'FULL_SOURCE'},
                    'visual_content':'Source-locked TGA stage media for isolated execution validation.',
                    'match_type':'DIRECT','match_reason':'Test bytes exercise the real source-lock/probe/range acquisition path only.'
                }
            }
        ]
    }


def test_prepare_real_pilot_pack_exposes_exact_two_source_locks(tmp_path):
    ws=_copy_pilot(tmp_path)
    out=tmp_path/'pack'
    res=PilotExecutionRuntime(ROOT,ws).prepare(out)
    assert res.project_state=='ASSET_RECON'
    assert res.requirement_count==2
    by={x['candidate_key']:x for x in res.requirements}
    assert set(by)=={'LISA_X_DIRECT_VERIFIED','TGA_VIDEO'}
    assert by['LISA_X_DIRECT_VERIFIED']['canonical_source_url']=='https://twitter.com/manfightdragon/status/1170860592233472001'
    assert by['TGA_VIDEO']['candidate_locator']=={'type':'VIDEO_TIME_RANGE','start_seconds':0,'end_seconds':135,'key_seconds':55}
    assert {'MEDIA_REQUIRED:LISA_X_DIRECT_VERIFIED','MEDIA_REQUIRED:TGA_VIDEO'} <= set(res.blockers)
    tpl=json.loads(res.handoff_template_path.read_text(encoding='utf-8'))
    lisa=next(x for x in tpl['items'] if x['candidate_key']=='LISA_X_DIRECT_VERIFIED')
    assert lisa['segment']['selector']['start_seconds'] is None
    assert res.runbook_path.is_file() and res.execution_manifest_path.is_file()


def test_preflight_does_not_mutate_real_pilot_copy(tmp_path):
    ws=_copy_pilot(tmp_path); plan=_plan(tmp_path)
    before=ColdStartLoader(ROOT,ws).load().engine
    assert before.project_state=='ASSET_RECON'
    mv=before.manifest_version
    pf=PilotExecutionRuntime(ROOT,ws).preflight(plan)
    assert pf.ready is True and pf.requirement_count==2 and len(pf.validated_items)==2
    after_pf=ColdStartLoader(ROOT,ws).load().engine
    assert after_pf.project_state=='ASSET_RECON' and after_pf.manifest_version==mv


def test_execute_reaches_visual_coverage_ready_from_real_pilot_copy(tmp_path):
    ws=_copy_pilot(tmp_path); plan=_plan(tmp_path)
    res=PilotExecutionRuntime(ROOT,ws).execute(plan)
    assert res.starting_state=='ASSET_RECON'
    assert res.project_state=='VISUAL_COVERAGE_READY'
    assert res.handoff_result['acquisition']['project_state']=='ASSET_CATALOG_READY'
    assert res.visual_coverage_result['project_state']=='VISUAL_COVERAGE_READY'
    assert ColdStartLoader(ROOT,ws).load().engine.project_state=='VISUAL_COVERAGE_READY'


def test_incomplete_or_source_mismatched_plan_fails_preflight_without_mutation(tmp_path):
    ws=_copy_pilot(tmp_path); plan=_plan(tmp_path)
    plan['items']=plan['items'][:1]
    rt=PilotExecutionRuntime(ROOT,ws)
    pf=rt.preflight(plan)
    assert not pf.ready
    assert any('COMPLETE_PENDING_SET_REQUIRED' in x for x in pf.blockers)
    assert ColdStartLoader(ROOT,ws).load().engine.project_state=='ASSET_RECON'
    with pytest.raises(PilotExecutionError,match='PREFLIGHT_FAILED'):
        rt.execute(plan)


def test_replay_after_success_is_idempotent_and_does_not_duplicate(tmp_path):
    ws=_copy_pilot(tmp_path); plan=_plan(tmp_path); rt=PilotExecutionRuntime(ROOT,ws)
    first=rt.execute(plan)
    manifest=ColdStartLoader(ROOT,ws).load().engine.manifest_version
    second=rt.execute(plan)
    assert first.project_state=='VISUAL_COVERAGE_READY'
    assert second.project_state=='VISUAL_COVERAGE_READY'
    assert second.idempotent_replay is True
    assert ColdStartLoader(ROOT,ws).load().engine.manifest_version==manifest


def test_static_audit_tracks_build036_readme_and_execution_pack():
    from gmk_audit import AuditRuntime
    r=AuditRuntime(ROOT).run('STATIC')
    assert r.fail_count==0
    by={x.name:x for x in r.checks}
    assert by['readme_current_build'].status=='PASS'
    assert by['pilot_execution_pack'].status=='PASS'
