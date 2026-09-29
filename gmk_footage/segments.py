from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib,json,shutil,subprocess

class SegmentExtractionError(RuntimeError):pass

@dataclass(frozen=True)
class ExtractedSegment:
    source_path:Path;segment_path:Path;start:float;end:float;key_time:float;sha256:str;duration_seconds:float;receipt_path:Path
    def to_dict(self)->dict[str,Any]:
        return {'source_path':str(self.source_path),'segment_path':str(self.segment_path),'start':self.start,'end':self.end,'key_time':self.key_time,'sha256':self.sha256,'duration_seconds':self.duration_seconds,'receipt_path':str(self.receipt_path)}

class SegmentExtractor:
    def __init__(self,ffmpeg:str='ffmpeg',ffprobe:str='ffprobe'):
        self.ffmpeg=ffmpeg;self.ffprobe=ffprobe
    def _require(self):
        for x in (self.ffmpeg,self.ffprobe):
            if not (Path(x).is_file() or shutil.which(x)):raise SegmentExtractionError(f'SEGMENT_TOOL_MISSING: {x}')
    def _duration(self,p:Path)->float:
        x=subprocess.run([self.ffprobe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],capture_output=True,text=True)
        if x.returncode!=0:raise SegmentExtractionError('SEGMENT_FFPROBE_FAILED')
        return float(x.stdout.strip())
    def extract(self,source:Path,output:Path,*,start:float,end:float,key_time:float|None=None,metadata:dict[str,Any]|None=None)->ExtractedSegment:
        self._require();source=Path(source);output=Path(output)
        if not source.is_file():raise SegmentExtractionError(f'SEGMENT_SOURCE_MISSING: {source}')
        dur=self._duration(source);start=max(0.0,float(start));end=min(float(end),dur)
        if not end>start:raise SegmentExtractionError('SEGMENT_RANGE_INVALID')
        key=float(key_time if key_time is not None else (start+end)/2)
        if not start<=key<=end:raise SegmentExtractionError('SEGMENT_KEY_TIME_INVALID')
        output.parent.mkdir(parents=True,exist_ok=True)
        cmd=[self.ffmpeg,'-hide_banner','-loglevel','error','-ss',f'{start:.3f}','-to',f'{end:.3f}','-i',str(source),'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-movflags','+faststart','-y',str(output)]
        p=subprocess.run(cmd,capture_output=True,text=True)
        if p.returncode!=0 or not output.is_file():raise SegmentExtractionError(f'SEGMENT_FFMPEG_FAILED: {(p.stderr or "").strip()}')
        raw=output.read_bytes();sha=hashlib.sha256(raw).hexdigest();segdur=self._duration(output)
        receipt=output.with_suffix(output.suffix+'.segment.json')
        body={'source_path':str(source.resolve()),'segment_path':str(output.resolve()),'start':start,'end':end,'key_time':key,'sha256':sha,'duration_seconds':segdur,'metadata':metadata or {}}
        receipt.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return ExtractedSegment(source,output,start,end,key,sha,segdur,receipt)
