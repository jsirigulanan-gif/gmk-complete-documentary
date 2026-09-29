from pathlib import Path
import subprocess,tempfile,stat,shutil
from gmk_footage.youtube_provider import YouTubeCandidate
from gmk_footage.ranker import RankedCandidate
from gmk_footage.transcript import TimestampMatch
from gmk_footage.research import InspectedCandidate,BeatResearchResult,FootageResearchReport
from gmk_footage.acquire import YouTubeAcquirer
from gmk_footage.auto_production import AutomaticFootageProductionRuntime


def _media(p:Path):
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=5','-f','lavfi','-i','sine=frequency=300:sample_rate=44100','-t','8','-pix_fmt','yuv420p','-c:v','libx264','-c:a','aac','-y',str(p)],check=True)

def _fake(root:Path,src:Path):
 p=root/'yt-dlp';p.write_text(f'''#!/usr/bin/env python3
import pathlib,shutil,sys
args=sys.argv[1:];out=args[args.index('-o')+1];url=args[-1];vid=url.split('=')[-1]
path=pathlib.Path(out.replace('%(id)s',vid).replace('%(ext)s','mp4'));path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2({str(src)!r},path);print(path)
''');p.chmod(p.stat().st_mode|stat.S_IXUSR);return p

def _beat(k,vid):
 c=YouTubeCandidate(vid,f'{k} title',f'https://www.youtube.com/watch?v={vid}','Creator',None,8,'',None,100,None,'q','EXACT_ENTITY',1)
 r=RankedCandidate(c,0.9,{'x':1.0},('pt',));t=TimestampMatch(1.0,4.0,2.0,0.8,('pt',),'excerpt',2)
 return BeatResearchResult(k,{'id':k,'version':1},1,1,(InspectedCandidate(r,(t,),True),),'YOUTUBE_CANDIDATE_READY')

def test_auto_production_acquires_extracts_and_exports_rough_cut():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);src=root/'source.mp4';_media(src);exe=_fake(root,src)
  rep=FootageResearchReport('p',(_beat('BEAT_1','v1'),_beat('BEAT_2','v2')),'r',('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED'))
  runtime=AutomaticFootageProductionRuntime(acquirer=YouTubeAcquirer(str(exe)))
  x=runtime.run(rep,root/'out')
  assert len(x.beats)==2
  assert x.assembly.output_path.exists() and x.production_manifest.exists()
  assert x.assembly.duration_seconds>5
  assert 'PENDING_PERMISSION' in x.assembly.credits_path.read_text()
