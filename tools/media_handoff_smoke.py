from pathlib import Path
import shutil, subprocess, tempfile, sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gmk_assets import MediaHandoffRuntime

PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def make_video(path: Path):
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=size=320x180:rate=25:duration=2','-c:v','mpeg4',str(path)],check=True)


def main():
    tmp=Path(tempfile.mkdtemp(prefix='gmk-media-handoff-'))
    ws=tmp/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    lisa=tmp/'lisa.mp4'; tga=tmp/'tga.mp4'; make_video(lisa); make_video(tga)
    plan={'batch_id':'PT_MEDIA_HANDOFF_SMOKE_018','items':[
        {'candidate_key':'LISA_X_DIRECT_VERIFIED','local_path':str(lisa),'source_url':'https://twitter.com/manfightdragon/status/1170860592233472001','acquisition_method':'SYNTHETIC_SMOKE_FIXTURE','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'Synthetic smoke media standing in only for runtime validation.','match_type':'DIRECT','match_reason':'Smoke verifies byte/probe/range/Gate flow, not P.T. content authenticity.'}},
        {'candidate_key':'TGA_VIDEO','local_path':str(tga),'source_url':'https://www.youtube.com/watch?v=PKl5rYdwM6c','acquisition_method':'SYNTHETIC_SMOKE_FIXTURE','segment':{'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8},'source_locator':{'type':'FULL_SOURCE'},'visual_content':'Synthetic smoke media standing in only for runtime validation.','match_type':'DIRECT','match_reason':'Smoke verifies byte/probe/range/Gate flow, not P.T. content authenticity.'}}
    ]}
    result=MediaHandoffRuntime(ROOT,ws).run(plan)
    assert result.acquisition is not None
    assert result.acquisition.project_state=='ASSET_CATALOG_READY'
    assert result.acquisition.coverage_result in {'PASS','WARN'}
    assert len(result.acquisition.pending_asset_refs)==0
    print('PASS: media handoff validates real video bytes and reaches ASSET_CATALOG_READY in isolated smoke workspace.')

if __name__=='__main__': main()
