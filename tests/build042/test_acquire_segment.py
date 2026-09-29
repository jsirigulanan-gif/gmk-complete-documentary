from pathlib import Path
import os,stat,subprocess,tempfile
from gmk_footage.youtube_provider import YouTubeCandidate
from gmk_footage.acquire import YouTubeAcquirer
from gmk_footage.segments import SegmentExtractor


def _source(root:Path)->Path:
 p=root/'source.mp4';subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=5','-f','lavfi','-i','sine=frequency=400:sample_rate=44100','-t','8','-pix_fmt','yuv420p','-c:v','libx264','-c:a','aac','-y',str(p)],check=True);return p

def _fake_ytdlp(root:Path,src:Path)->Path:
 p=root/'yt-dlp';code=f'''#!/usr/bin/env python3
import pathlib,shutil,sys
args=sys.argv[1:]
out=args[args.index('-o')+1]
path=pathlib.Path(out.replace('%(ext)s','mp4'))
path.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2({str(src)!r},path)
print(path)
''';p.write_text(code);p.chmod(p.stat().st_mode|stat.S_IXUSR);return p

def test_acquire_selected_candidate_and_extract_segment_with_receipts():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);src=_source(root);exe=_fake_ytdlp(root,src)
  c=YouTubeCandidate('abc','Relevant P.T. footage','https://www.youtube.com/watch?v=abc','Creator',None,8,'',None,100,None,'P.T.','EXACT_ENTITY',1)
  a=YouTubeAcquirer(str(exe)).acquire(c,root/'acquired')
  assert a.local_path.exists() and len(a.sha256)==64 and a.permission_status=='PENDING_PERMISSION'
  assert a.receipt_path.exists()
  s=SegmentExtractor().extract(a.local_path,root/'segments'/'beat.mp4',start=1.0,end=4.5,key_time=2.5,metadata={'beat_key':'BEAT_X'})
  assert s.segment_path.exists() and len(s.sha256)==64
  assert 3.3 <= s.duration_seconds <= 3.7
  assert s.receipt_path.exists()
