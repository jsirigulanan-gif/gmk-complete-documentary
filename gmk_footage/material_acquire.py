from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import hashlib
import json
import shutil
import subprocess

from .web_sources import WebSourceCandidate


class MaterialAcquisitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AcquiredMaterial:
    candidate: WebSourceCandidate
    local_path: Path
    sha256: str
    size_bytes: int
    permission_status: str
    receipt_path: Path


def _default_bytes(url: str) -> bytes:
    req=Request(url,headers={'User-Agent':'GMK-Documentary-Maker/0.2'})
    with urlopen(req,timeout=60) as r:
        return r.read()


class WebVideoAcquirer:
    """Acquire selected non-YouTube web/archive video via yt-dlp without auth bypass."""
    def __init__(self,yt_dlp:str='yt-dlp',*,timeout_seconds:int=900):
        self.yt_dlp=yt_dlp;self.timeout_seconds=int(timeout_seconds)
    def acquire(self,c:WebSourceCandidate,out_dir:Path)->AcquiredMaterial:
        if c.source_priority!='WEB_VIDEO':raise MaterialAcquisitionError('WEB_VIDEO_CANDIDATE_REQUIRED')
        if not (Path(self.yt_dlp).is_file() or shutil.which(self.yt_dlp)):raise MaterialAcquisitionError(f'WEB_YTDLP_MISSING: {self.yt_dlp}')
        u=urlparse(c.page_url)
        if u.scheme not in {'http','https'}:raise MaterialAcquisitionError('WEB_VIDEO_URL_INVALID')
        out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
        slug=hashlib.sha256(c.page_url.encode()).hexdigest()[:16]
        template=str(out/f'{slug}.%(ext)s')
        cmd=[self.yt_dlp,'--no-playlist','--no-warnings','-f','bv*+ba/b','--merge-output-format','mp4','-o',template,'--print','after_move:filepath',c.page_url]
        forbidden={'--cookies','--cookies-from-browser','--username','--password','--video-password','--allow-unplayable-formats'}
        if forbidden & set(cmd):raise MaterialAcquisitionError('WEB_ACCESS_CONTROL_OPTION_FORBIDDEN')
        try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:raise MaterialAcquisitionError('WEB_VIDEO_TIMEOUT') from exc
        if p.returncode!=0:raise MaterialAcquisitionError(f'WEB_VIDEO_DOWNLOAD_FAILED: {(p.stderr or p.stdout or "")[-800:]}')
        media=None
        for line in reversed([x.strip() for x in p.stdout.splitlines() if x.strip()]):
            q=Path(line)
            if q.is_file():media=q;break
        if media is None:
            files=[x for x in out.glob(f'{slug}.*') if x.is_file() and x.suffix.lower() not in {'.part','.json','.vtt'}]
            if files:media=files[0]
        if media is None:raise MaterialAcquisitionError('WEB_VIDEO_OUTPUT_MISSING')
        raw=media.read_bytes();sha=hashlib.sha256(raw).hexdigest();receipt=out/f'{slug}.acquisition.json'
        body={'provider':c.provider,'source_url':c.page_url,'title':c.title,'creator':c.creator,'media_kind':'VIDEO','local_path':str(media.resolve()),'sha256':sha,'size_bytes':len(raw),'permission_status':'PENDING_PERMISSION','attribution':{'creator':c.creator,'title':c.title,'source_url':c.page_url,'required_in_credits':True},'access_controls_bypassed':False}
        receipt.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return AcquiredMaterial(c,media,sha,len(raw),'PENDING_PERMISSION',receipt)


class StillImageAcquirer:
    def __init__(self,fetch_bytes:Callable[[str],bytes]=_default_bytes):self.fetch_bytes=fetch_bytes
    def acquire(self,c:WebSourceCandidate,out_dir:Path)->AcquiredMaterial:
        if c.source_priority!='STILL_DOCUMENT' or not c.media_url:raise MaterialAcquisitionError('STILL_MEDIA_URL_REQUIRED')
        u=urlparse(c.media_url)
        if u.scheme not in {'http','https'}:raise MaterialAcquisitionError('STILL_URL_INVALID')
        raw=self.fetch_bytes(c.media_url)
        if not raw:raise MaterialAcquisitionError('STILL_DOWNLOAD_EMPTY')
        suffix=Path(u.path).suffix.lower()
        if suffix not in {'.jpg','.jpeg','.png','.webp','.tif','.tiff'}:suffix='.img'
        out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);slug=hashlib.sha256(c.media_url.encode()).hexdigest()[:16]
        path=out/f'{slug}{suffix}';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest();receipt=out/f'{slug}.acquisition.json'
        body={'provider':c.provider,'source_url':c.page_url,'media_url':c.media_url,'title':c.title,'creator':c.creator,'license_text':c.license_text,'media_kind':'STILL_DOCUMENT','local_path':str(path.resolve()),'sha256':sha,'size_bytes':len(raw),'permission_status':'PENDING_PERMISSION','attribution':{'creator':c.creator,'title':c.title,'source_url':c.page_url,'license':c.license_text,'required_in_credits':True}}
        receipt.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return AcquiredMaterial(c,path,sha,len(raw),'PENDING_PERMISSION',receipt)


class StillClipRenderer:
    """Turn a still/document image into a documentary timeline clip with a gentle zoom."""
    def __init__(self,ffmpeg:str='ffmpeg'):self.ffmpeg=ffmpeg
    def render(self,image:Path,output:Path,*,duration:float=6.0,width:int=1280,height:int=720,fps:int=30)->Path:
        if not (Path(self.ffmpeg).is_file() or shutil.which(self.ffmpeg)):raise MaterialAcquisitionError('STILL_FFMPEG_MISSING')
        image=Path(image);output=Path(output)
        if not image.is_file():raise MaterialAcquisitionError('STILL_SOURCE_MISSING')
        output.parent.mkdir(parents=True,exist_ok=True)
        frames=max(1,int(duration*fps))
        vf=(f"scale={width*2}:{height*2}:force_original_aspect_ratio=decrease,"
            f"pad={width*2}:{height*2}:(ow-iw)/2:(oh-ih)/2,"
            f"zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps},format=yuv420p")
        p=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-loop','1','-i',str(image),'-vf',vf,'-t',f'{duration:.3f}','-an','-c:v','libx264','-preset','veryfast','-crf','20','-movflags','+faststart','-y',str(output)],capture_output=True,text=True)
        if p.returncode!=0 or not output.is_file():raise MaterialAcquisitionError(f'STILL_RENDER_FAILED: {(p.stderr or "")[-800:]}')
        return output
