from pathlib import Path
import subprocess,tempfile
from gmk_footage.query_planner import BeatSearchIntent
from gmk_footage.visual_matcher import VisualSemanticMatcher, VisualObservation


class FixtureVision:
    name='TEST_PIXEL_PROVIDER'
    def describe(self,frame_path:Path,*,prompt:str):
        # FrameSampler encodes timestamp in the filename. Simulate a grounded provider result.
        name=frame_path.name
        desc='generic aircraft interior'
        if '000005.000' in name:
            desc='Concorde supersonic aircraft taking off from runway with British Airways markings'
        return VisualObservation(frame_path,0.0,desc,self.name,None)


def _media(p:Path):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=5','-t','11','-pix_fmt','yuv420p','-c:v','libx264','-y',str(p)],check=True)


def _intent():
    return BeatSearchIntent('B1',{'id':'B1','version':1},'HIGH','Concorde supersonic aircraft taking off from runway','The aircraft enters service',tuple(),('Concorde enters service',),tuple(),('Concorde','aircraft','runway'),tuple(),('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED'),True)


def test_visual_matcher_nominates_pixel_grounded_timestamp():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);src=root/'source.mp4';_media(src)
        rep=VisualSemanticMatcher(FixtureVision()).match(_intent(),src,root/'inspect',interval=5,max_frames=3,threshold=.25,clip_seconds=4)
        assert rep.matches
        assert rep.matches[0].key_time==5.0
        assert rep.matches[0].provider=='TEST_PIXEL_PROVIDER'
        assert rep.match_manifest.exists() and rep.inspection_manifest.exists()
        assert 'Concorde' in rep.match_manifest.read_text(encoding='utf-8')
