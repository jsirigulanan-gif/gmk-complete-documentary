from pathlib import Path
import shutil
import subprocess

import pytest

from gmk_assets import MediaHandoffRuntime, MediaHandoffError
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def _video(path: Path, duration: float = 2.0):
    subprocess.run([
        'ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=size=320x180:rate=25:duration={duration}',
        '-c:v','mpeg4',str(path)
    ], check=True)


def _plan(a: Path, b: Path):
    return {
        'batch_id':'PT_MEDIA_HANDOFF_TEST_018',
        'items':[
            {
                'candidate_key':'LISA_X_DIRECT_VERIFIED','local_path':str(a),
                'source_url':'https://twitter.com/manfightdragon/status/1170860592233472001',
                'acquisition_method':'AUTHORIZED_MANUAL_EXPORT',
                'segment':{
                    'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0},
                    'source_locator':{'type':'FULL_SOURCE'},
                    'visual_content':'Original creator camera-hack clip showing Lisa following behind the player.',
                    'match_type':'DIRECT','match_reason':'The verified local video bytes directly depict the required Lisa camera-hack reveal.'
                }
            },
            {
                'candidate_key':'TGA_VIDEO','local_path':str(b),
                'source_url':'https://www.youtube.com/watch?v=PKl5rYdwM6c',
                'acquisition_method':'AUTHORIZED_MANUAL_EXPORT',
                'segment':{
                    'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8},
                    'source_locator':{'type':'FULL_SOURCE'},
                    'visual_content':'Audiovisual stage statement preserving speaker and venue context.',
                    'match_type':'DIRECT','match_reason':'The verified local video bytes directly depict the selected Game Awards statement.'
                }
            }
        ]
    }


def test_requirements_are_exactly_two_pending_videos():
    reqs=MediaHandoffRuntime(ROOT,PILOT).requirements()
    assert {x.candidate_key for x in reqs}=={'LISA_X_DIRECT_VERIFIED','TGA_VIDEO'}


def test_handoff_closes_catalog_when_real_video_bytes_exist(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'lisa.mp4'; b=tmp_path/'tga.mp4'; _video(a); _video(b)
    result=MediaHandoffRuntime(ROOT,ws).run(_plan(a,b))
    assert result.acquisition is not None
    assert result.acquisition.coverage_result in {'PASS','WARN'}
    assert result.acquisition.project_state=='ASSET_CATALOG_READY'
    loaded=ColdStartLoader(ROOT,ws).load(); state=loaded.engine.snapshot()
    assets=[]; segs=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.active_version is None: continue
            obj=state.objects[(oid,int(e.active_version))]
            if obj.get('object_type')=='ASSET': assets.append(obj)
            if obj.get('object_type')=='SEGMENT': segs.append(obj)
    assert sum(a.get('workflow_state')=='CATALOGED' for a in assets)==10
    assert len(segs)==10


def test_handoff_rejects_text_disguised_as_video(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'fake.mp4'; a.write_text('not video')
    b=tmp_path/'tga.mp4'; _video(b)
    with pytest.raises(MediaHandoffError, match='FFPROBE_FAILED'):
        MediaHandoffRuntime(ROOT,ws).run(_plan(a,b))


def test_handoff_rejects_out_of_bounds_segment(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    a=tmp_path/'lisa.mp4'; b=tmp_path/'tga.mp4'; _video(a); _video(b)
    plan=_plan(a,b); plan['items'][0]['segment']['selector']['end_seconds']=99
    with pytest.raises(MediaHandoffError, match='OUT_OF_BOUNDS'):
        MediaHandoffRuntime(ROOT,ws).run(plan)
