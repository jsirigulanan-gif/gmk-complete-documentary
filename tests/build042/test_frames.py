from pathlib import Path
import subprocess,tempfile
from gmk_footage.frames import FrameSampler


def test_frame_sampler_extracts_real_images_and_manifest():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);src=root/'tiny.mp4';out=root/'frames'
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=2','-t','6','-pix_fmt','yuv420p','-y',str(src)],check=True)
  r=FrameSampler().sample(src,out,start=0,end=5,interval=2,max_frames=5)
  assert len(r.frames)==3
  assert r.manifest_path.exists()
  assert all(x.path.exists() and len(x.sha256)==64 for x in r.frames)
  assert 5.9 <= r.duration_seconds <= 6.1
