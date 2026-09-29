from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import hashlib
import json
import shutil
import subprocess
import tempfile

from .youtube_provider import YouTubeCandidate


class FootageAcquisitionError(RuntimeError):
    pass


@dataclass(frozen=True)
class AcquiredFootage:
    candidate: YouTubeCandidate
    local_path: Path
    sha256: str
    size_bytes: int
    duration_seconds: float
    permission_status: str
    attribution: dict[str, Any]
    receipt_path: Path

    def to_dict(self)->dict[str,Any]:
        return {
            'source':self.candidate.to_dict(),'local_path':str(self.local_path),'sha256':self.sha256,
            'size_bytes':self.size_bytes,'duration_seconds':self.duration_seconds,
            'permission_status':self.permission_status,'attribution':dict(self.attribution),'receipt_path':str(self.receipt_path)
        }


class YouTubeAcquirer:
    """Acquire a selected public YouTube candidate without bypassing access controls.

    No cookies, credentials, impersonation or DRM-bypass flags are accepted here. Rights are
    tracked separately as PENDING_PERMISSION and do not masquerade as verified permission.
    """
    def __init__(self,yt_dlp:str='yt-dlp',ffprobe:str='ffprobe',*,timeout_seconds:int=900):
        self.yt_dlp=yt_dlp;self.ffprobe=ffprobe;self.timeout_seconds=int(timeout_seconds)

    def _require(self):
        for x in (self.yt_dlp,self.ffprobe):
            if not (Path(x).is_file() or shutil.which(x)):
                raise FootageAcquisitionError(f'ACQUIRE_TOOL_MISSING: {x}')

    def _duration(self,p:Path)->float:
        proc=subprocess.run([self.ffprobe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],capture_output=True,text=True)
        if proc.returncode!=0:raise FootageAcquisitionError(f'ACQUIRE_FFPROBE_FAILED: {(proc.stderr or "").strip()}')
        try:return float(proc.stdout.strip())
        except ValueError as exc:raise FootageAcquisitionError('ACQUIRE_DURATION_INVALID') from exc

    def acquire(self,candidate:YouTubeCandidate,output_dir:Path)->AcquiredFootage:
        self._require()
        u=urlparse(candidate.webpage_url)
        if u.scheme not in {'http','https'} or not (u.hostname or '').casefold().endswith(('youtube.com','youtu.be')):
            raise FootageAcquisitionError(f'ACQUIRE_YOUTUBE_URL_INVALID: {candidate.webpage_url}')
        out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
        template=str(out/f'{candidate.video_id}.%(ext)s')
        cmd=[self.yt_dlp,'--no-playlist','--no-warnings','-f','bv*+ba/b','--merge-output-format','mp4','-o',template,'--print','after_move:filepath',candidate.webpage_url]
        # Deliberately no cookies / username / password / DRM options.
        forbidden={'--cookies','--cookies-from-browser','--username','--password','--video-password','--allow-unplayable-formats'}
        if forbidden & set(cmd):raise FootageAcquisitionError('ACQUIRE_ACCESS_CONTROL_OPTION_FORBIDDEN')
        try:proc=subprocess.run(cmd,check=False,capture_output=True,text=True,timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:raise FootageAcquisitionError(f'ACQUIRE_TIMEOUT: {candidate.video_id}') from exc
        if proc.returncode!=0:
            detail=(proc.stderr or proc.stdout or '').strip()[-1000:]
            raise FootageAcquisitionError(f'ACQUIRE_YTDLP_FAILED: rc={proc.returncode}: {detail}')
        lines=[x.strip() for x in proc.stdout.splitlines() if x.strip()]
        candidates=[]
        for line in reversed(lines):
            p=Path(line)
            if p.is_file():candidates.append(p);break
        if not candidates:
            files=sorted(out.glob(f'{candidate.video_id}.*'),key=lambda p:p.stat().st_mtime,reverse=True)
            files=[p for p in files if p.is_file() and p.suffix.lower() not in {'.json','.vtt','.srt','.part'}]
            if files:candidates=[files[0]]
        if not candidates:raise FootageAcquisitionError(f'ACQUIRE_OUTPUT_MISSING: {candidate.video_id}')
        media=candidates[0]
        hasher=hashlib.sha256();size=0
        with media.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                hasher.update(chunk);size+=len(chunk)
        sha=hasher.hexdigest();dur=self._duration(media)
        receipt=out/f'{candidate.video_id}.acquisition.json'
        body={
            'provider':'YOUTUBE','video_id':candidate.video_id,'source_url':candidate.webpage_url,
            'title':candidate.title,'creator':candidate.channel,'query':candidate.query,'query_family':candidate.query_family,
            'local_path':str(media.resolve()),'sha256':sha,'size_bytes':size,'duration_seconds':dur,
            'permission_status':'PENDING_PERMISSION',
            'attribution':{'creator':candidate.channel,'title':candidate.title,'source_url':candidate.webpage_url,'required_in_credits':True},
            'access_controls_bypassed':False,
        }
        receipt.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return AcquiredFootage(candidate,media,sha,size,dur,'PENDING_PERMISSION',body['attribution'],receipt)
