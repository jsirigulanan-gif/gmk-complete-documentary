from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import math
import shutil
import subprocess
import tempfile


class FrameSamplingError(RuntimeError):
    pass


@dataclass(frozen=True)
class SampledFrame:
    timestamp: float
    path: Path
    sha256: str

    def to_dict(self)->dict[str,Any]:
        return {"timestamp":self.timestamp,"path":str(self.path),"sha256":self.sha256}


@dataclass(frozen=True)
class FrameInspectionBundle:
    source_path: Path
    duration_seconds: float
    frames: tuple[SampledFrame,...]
    manifest_path: Path


class FrameSampler:
    """Deterministically sample visual evidence from already-acquired local media."""
    def __init__(self,ffmpeg:str='ffmpeg',ffprobe:str='ffprobe'):
        self.ffmpeg=ffmpeg;self.ffprobe=ffprobe

    def _require(self):
        for x in (self.ffmpeg,self.ffprobe):
            if not (Path(x).is_file() or shutil.which(x)):
                raise FrameSamplingError(f'FRAME_TOOL_MISSING: {x}')

    def duration(self,source:Path)->float:
        self._require();p=Path(source)
        if not p.is_file():raise FrameSamplingError(f'FRAME_SOURCE_MISSING: {p}')
        proc=subprocess.run([self.ffprobe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],capture_output=True,text=True)
        if proc.returncode!=0:raise FrameSamplingError(f'FRAME_FFPROBE_FAILED: {(proc.stderr or "").strip()}')
        try:return float(proc.stdout.strip())
        except ValueError as exc:raise FrameSamplingError('FRAME_DURATION_INVALID') from exc

    def sample(self,source:Path,output_dir:Path,*,start:float=0.0,end:float|None=None,interval:float=5.0,max_frames:int=60)->FrameInspectionBundle:
        dur=self.duration(source);start=max(0.0,float(start));end=min(dur,float(end) if end is not None else dur)
        if not (end>start):raise FrameSamplingError('FRAME_RANGE_INVALID')
        if not math.isfinite(interval) or interval<=0 or max_frames<1:raise FrameSamplingError('FRAME_SAMPLING_CONFIG_INVALID')
        out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
        times=[];t=start
        # The duration is an exclusive media boundary: there is no frame at EOF.
        # Check the rounded seek time too, since ffmpeg receives milliseconds.
        while t<=end+1e-6 and round(t,3)<dur and len(times)<max_frames:
            times.append(round(t,3));t+=interval
        frames=[]
        for idx,t in enumerate(times,1):
            target=out/f'frame_{idx:03d}_{t:010.3f}.jpg'
            proc=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-ss',f'{t:.3f}','-i',str(source),'-frames:v','1','-q:v','2','-y',str(target)],capture_output=True,text=True)
            if proc.returncode!=0 or not target.exists():
                raise FrameSamplingError(f'FRAME_EXTRACTION_FAILED: t={t}: {(proc.stderr or "").strip()}')
            frames.append(SampledFrame(t,target,hashlib.sha256(target.read_bytes()).hexdigest()))
        manifest=out/'FRAME_INSPECTION_MANIFEST.json'
        body={"source_path":str(Path(source).resolve()),"duration_seconds":dur,"range":{"start":start,"end":end},"interval":interval,"frames":[x.to_dict() for x in frames]}
        manifest.write_text(json.dumps(body,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')
        return FrameInspectionBundle(Path(source),dur,tuple(frames),manifest)
