from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib,json,shutil,subprocess,tempfile


class AssemblyError(RuntimeError):pass

@dataclass(frozen=True)
class TimelineClip:
    beat_key:str
    path:Path
    attribution:dict[str,Any]
    source_url:str|None=None
    permission_status:str='PENDING_PERMISSION'

@dataclass(frozen=True)
class AssemblyResult:
    output_path:Path
    duration_seconds:float
    sha256:str
    timeline_manifest:Path
    credits_path:Path

class DocumentaryAssembler:
    """Create a deterministic documentary rough-cut MP4 from ordered Beat clips.

    This is the first automatic-editing layer. It normalizes clips to one format, concatenates
    them in Beat order, optionally replaces guide audio with the locked narration/voice track,
    and emits timeline + credits sidecars. Higher-order graphics/transitions stay downstream.
    """
    def __init__(self,ffmpeg:str='ffmpeg',ffprobe:str='ffprobe'):
        self.ffmpeg=ffmpeg;self.ffprobe=ffprobe
    def _require(self):
        for x in (self.ffmpeg,self.ffprobe):
            if not (Path(x).is_file() or shutil.which(x)):raise AssemblyError(f'ASSEMBLY_TOOL_MISSING: {x}')
    def _duration(self,p:Path)->float:
        r=subprocess.run([self.ffprobe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],capture_output=True,text=True)
        if r.returncode!=0:raise AssemblyError(f'ASSEMBLY_FFPROBE_FAILED: {(r.stderr or "").strip()}')
        return float(r.stdout.strip())
    def assemble(self,clips:list[TimelineClip]|tuple[TimelineClip,...],output:Path,*,voice_path:Path|None=None,width:int=1280,height:int=720,fps:int=30)->AssemblyResult:
        self._require()
        if not clips:raise AssemblyError('ASSEMBLY_CLIPS_REQUIRED')
        for c in clips:
            if not Path(c.path).is_file():raise AssemblyError(f'ASSEMBLY_CLIP_MISSING: {c.path}')
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='gmk-assembly-') as td:
            root=Path(td);normalized=[];timeline=[];cursor=0.0
            for i,c in enumerate(clips,1):
                n=root/f'{i:04d}.mp4'
                vf=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p'
                # Normalize as video-only. Documentary narration is authoritative audio when supplied;
                # otherwise a silent guide track is added after concat for reliable output shape.
                p=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-i',str(c.path),'-map','0:v:0','-vf',vf,'-an','-c:v','libx264','-preset','veryfast','-crf','20','-movflags','+faststart','-y',str(n)],capture_output=True,text=True)
                if p.returncode!=0:raise AssemblyError(f'ASSEMBLY_NORMALIZE_FAILED: {c.beat_key}: {(p.stderr or "").strip()}')
                dur=self._duration(n);normalized.append(n)
                timeline.append({'order':i,'beat_key':c.beat_key,'source_clip':str(Path(c.path).resolve()),'timeline_start':cursor,'timeline_end':cursor+dur,'duration_seconds':dur,'source_url':c.source_url,'permission_status':c.permission_status,'attribution':c.attribution})
                cursor+=dur
            concat=root/'concat.txt';concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in normalized),encoding='utf-8')
            video=root/'video.mp4'
            p=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-c','copy','-y',str(video)],capture_output=True,text=True)
            if p.returncode!=0:raise AssemblyError(f'ASSEMBLY_CONCAT_FAILED: {(p.stderr or "").strip()}')
            total=self._duration(video)
            if voice_path is not None:
                voice=Path(voice_path)
                if not voice.is_file():raise AssemblyError(f'ASSEMBLY_VOICE_MISSING: {voice}')
                p=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-i',str(video),'-i',str(voice),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',f'{total:.3f}','-movflags','+faststart','-y',str(output)],capture_output=True,text=True)
            else:
                p=subprocess.run([self.ffmpeg,'-hide_banner','-loglevel','error','-i',str(video),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-t',f'{total:.3f}','-shortest','-movflags','+faststart','-y',str(output)],capture_output=True,text=True)
            if p.returncode!=0 or not output.is_file():raise AssemblyError(f'ASSEMBLY_EXPORT_FAILED: {(p.stderr or "").strip()}')
        finaldur=self._duration(output);sha=hashlib.sha256(output.read_bytes()).hexdigest()
        manifest=output.with_suffix('.timeline.json')
        body={'output_path':str(output.resolve()),'duration_seconds':finaldur,'sha256':sha,'resolution':{'width':width,'height':height},'fps':fps,'voice_path':str(Path(voice_path).resolve()) if voice_path else None,'clips':timeline}
        manifest.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        credits=output.with_suffix('.credits.txt')
        lines=['GMK Documentary Footage Credits','']
        for row in timeline:
            a=row['attribution'] or {}; lines.append(f"{row['order']:02d}. {a.get('title') or row['beat_key']} — {a.get('creator') or 'Unknown creator'}")
            if row.get('source_url'):lines.append(f"    Source: {row['source_url']}")
            lines.append(f"    Permission: {row['permission_status']}")
        credits.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        return AssemblyResult(output,finaldur,sha,manifest,credits)
