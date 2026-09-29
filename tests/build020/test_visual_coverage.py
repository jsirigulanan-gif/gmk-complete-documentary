from pathlib import Path
import shutil
import subprocess
import pytest

from gmk_assets import MediaHandoffRuntime, VisualCoverageRuntime, VisualCoverageError
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def _video(path: Path, duration: float = 2.0):
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=size=320x180:rate=25:duration={duration}','-c:v','mpeg4',str(path)],check=True)


def _handoff(a: Path,b: Path):
    return {'batch_id':'PT_MEDIA_HANDOFF_TEST_020','items':[
        {'candidate_key':'LISA_X_DIRECT_VERIFIED','local_path':str(a),'source_url':'https://twitter.com/manfightdragon/status/1170860592233472001','acquisition_method':'AUTHORIZED_MANUAL_EXPORT','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'Lisa camera-hack source-locked media.','match_type':'DIRECT','match_reason':'Direct verified source media.'}},
        {'candidate_key':'TGA_VIDEO','local_path':str(b),'source_url':'https://www.youtube.com/watch?v=PKl5rYdwM6c','acquisition_method':'AUTHORIZED_MANUAL_EXPORT','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'TGA source-locked stage statement.','match_type':'DIRECT','match_reason':'Direct verified source media.'}}
    ]}


def test_visual_coverage_rejects_current_pilot_before_catalog():
    with pytest.raises(VisualCoverageError, match='STATE_INVALID'):
        VisualCoverageRuntime(ROOT,PILOT).run()


def test_visual_coverage_transitions_after_real_media_handoff(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'lisa.mp4'; b=tmp_path/'tga.mp4'; _video(a); _video(b)
    handoff=MediaHandoffRuntime(ROOT,ws).run(_handoff(a,b))
    assert handoff.acquisition.project_state=='ASSET_CATALOG_READY'
    result=VisualCoverageRuntime(ROOT,ws).run()
    assert result.coverage_result in {'PASS','WARN'}
    assert result.covered_beats==result.total_beats==10
    assert result.project_state=='VISUAL_COVERAGE_READY'
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.engine.project_state=='VISUAL_COVERAGE_READY'


def test_visual_coverage_replay_is_idempotent(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'lisa.mp4'; b=tmp_path/'tga.mp4'; _video(a); _video(b)
    MediaHandoffRuntime(ROOT,ws).run(_handoff(a,b))
    first=VisualCoverageRuntime(ROOT,ws).run()
    second=VisualCoverageRuntime(ROOT,ws).run()
    assert first.project_state=='VISUAL_COVERAGE_READY'
    assert second.idempotent_replay is True
