from pathlib import Path
import subprocess,tempfile
from gmk_footage.assembly import DocumentaryAssembler,TimelineClip


def _clip(path:Path,dur:float,freq:int):
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',f'testsrc=size=320x180:rate=5','-t',str(dur),'-pix_fmt','yuv420p','-c:v','libx264','-y',str(path)],check=True)

def _voice(path:Path,dur:float):
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t',str(dur),'-c:a','aac','-y',str(path)],check=True)

def test_assembler_exports_ordered_mp4_manifest_and_credits_with_voice():
 with tempfile.TemporaryDirectory() as td:
  r=Path(td);a=r/'a.mp4';b=r/'b.mp4';v=r/'voice.m4a';out=r/'rough.mp4'
  _clip(a,2.0,1);_clip(b,3.0,2);_voice(v,6.0)
  clips=[TimelineClip('B1',a,{'title':'Clip A','creator':'Creator A'},'https://youtube.com/a'),TimelineClip('B2',b,{'title':'Clip B','creator':'Creator B'},'https://youtube.com/b')]
  x=DocumentaryAssembler().assemble(clips,out,voice_path=v,width=640,height=360,fps=24)
  assert x.output_path.exists() and len(x.sha256)==64
  assert 4.8 <= x.duration_seconds <= 5.2
  assert x.timeline_manifest.exists() and x.credits_path.exists()
  text=x.credits_path.read_text();assert 'Clip A' in text and 'PENDING_PERMISSION' in text
