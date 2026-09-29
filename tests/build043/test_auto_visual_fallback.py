from pathlib import Path
import subprocess,tempfile,stat,shutil
from gmk_footage.query_planner import BeatSearchIntent
from gmk_footage.youtube_provider import YouTubeCandidate
from gmk_footage.ranker import RankedCandidate
from gmk_footage.research import InspectedCandidate,BeatResearchResult,FootageResearchReport
from gmk_footage.acquire import YouTubeAcquirer
from gmk_footage.auto_production import AutomaticFootageProductionRuntime
from gmk_footage.visual_matcher import VisualSemanticMatcher, VisualObservation


class FixtureVision:
    name='TEST_PIXEL_PROVIDER'
    def describe(self,frame_path:Path,*,prompt:str):
        desc='Concorde aircraft on runway British Airways' if '000005.000' in frame_path.name else 'unrelated indoor scene'
        return VisualObservation(frame_path,0.0,desc,self.name,None)


def _media(p:Path):
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=5','-f','lavfi','-i','sine=frequency=300:sample_rate=44100','-t','11','-pix_fmt','yuv420p','-c:v','libx264','-c:a','aac','-y',str(p)],check=True)


def _fake(root:Path,src:Path):
 p=root/'yt-dlp';p.write_text(f'''#!/usr/bin/env python3
import pathlib,shutil,sys
args=sys.argv[1:];out=args[args.index('-o')+1];url=args[-1];vid=url.split('=')[-1]
path=pathlib.Path(out.replace('%(id)s',vid).replace('%(ext)s','mp4'));path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2({str(src)!r},path);print(path)
''');p.chmod(p.stat().st_mode|stat.S_IXUSR);return p


def test_auto_production_uses_visual_semantic_fallback_without_metadata_guessing():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);src=root/'source.mp4';_media(src);exe=_fake(root,src)
  intent=BeatSearchIntent('BEAT_1',{'id':'BEAT_1','version':1},'HIGH','Concorde aircraft on runway','Concorde prepares for flight',tuple(),('Concorde flight',),tuple(),('Concorde','aircraft','runway'),tuple(),('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED'),True)
  c=YouTubeCandidate('v1','Concorde archive', 'https://www.youtube.com/watch?v=v1','Creator',None,11,'',None,100,None,'q','EXACT_ENTITY',1)
  r=RankedCandidate(c,.9,{'x':1.0},('concorde',))
  beat=BeatResearchResult('BEAT_1',{'id':'BEAT_1','version':1},1,1,(InspectedCandidate(r,tuple(),False),),'YOUTUBE_VISUAL_INSPECTION_REQUIRED',intent)
  rep=FootageResearchReport('p',(beat,),'r',('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED'))
  runtime=AutomaticFootageProductionRuntime(acquirer=YouTubeAcquirer(str(exe)),visual_matcher=VisualSemanticMatcher(FixtureVision()))
  x=runtime.run(rep,root/'out',visual_interval=5,visual_threshold=.2)
  assert len(x.beats)==1 and x.beats[0].selection_mode=='VISUAL_SEMANTIC'
  assert x.beats[0].visual_match_manifest and x.beats[0].visual_match_manifest.exists()
  assert x.assembly.output_path.exists()
  assert 'PENDING_PERMISSION' in x.assembly.credits_path.read_text()
