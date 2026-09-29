from pathlib import Path
import stat,subprocess,tempfile
from gmk_footage.web_sources import WebSourceCandidate
from gmk_footage.material_acquire import WebVideoAcquirer,StillImageAcquirer,StillClipRenderer


def _video(p):subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=4','-t','3','-pix_fmt','yuv420p','-c:v','libx264','-y',str(p)],check=True)
def _fake(root,src):
 p=root/'yt-dlp';p.write_text(f'''#!/usr/bin/env python3
import pathlib,shutil,sys
args=sys.argv[1:];o=args[args.index('-o')+1];path=pathlib.Path(o.replace('%(ext)s','mp4'));path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2({str(src)!r},path);print(path)
''');p.chmod(p.stat().st_mode|stat.S_IXUSR);return p

def test_web_video_acquire_receipt():
 with tempfile.TemporaryDirectory() as td:
  r=Path(td);src=r/'s.mp4';_video(src);exe=_fake(r,src)
  c=WebSourceCandidate('ARCH','VIDEO','Historic','https://archive.org/details/x',None,'Creator','desc',None,'WEB_VIDEO',1)
  a=WebVideoAcquirer(str(exe)).acquire(c,r/'out');assert a.local_path.exists() and a.permission_status=='PENDING_PERMISSION' and a.receipt_path.exists()

def test_still_acquire_and_render_clip():
 with tempfile.TemporaryDirectory() as td:
  r=Path(td);png=r/'seed.png';subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=1','-frames:v','1','-y',str(png)],check=True)
  raw=png.read_bytes();c=WebSourceCandidate('WIKI','IMAGE','Photo','https://commons/x','https://upload/x.png','Artist','desc','CC','STILL_DOCUMENT',1)
  a=StillImageAcquirer(lambda url:raw).acquire(c,r/'out');assert a.local_path.exists()
  clip=StillClipRenderer().render(a.local_path,r/'still.mp4',duration=2,width=320,height=180,fps=10);assert clip.exists() and clip.stat().st_size>0
