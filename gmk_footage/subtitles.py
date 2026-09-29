from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile

from .transcript import TranscriptCue, parse_vtt


class SubtitleFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SubtitleFetchResult:
    video_id: str
    language: str | None
    source_kind: str
    cues: tuple[TranscriptCue, ...]
    raw_vtt_path: Path


class YouTubeSubtitleFetcher:
    """Fetch human/automatic captions only; never video bytes."""

    def __init__(self, executable: str | Path='yt-dlp', *, timeout_seconds: int=60):
        self.executable=str(executable);self.timeout_seconds=int(timeout_seconds)

    def available(self)->bool:
        return Path(self.executable).is_file() or shutil.which(self.executable) is not None

    def fetch(self, video_url: str, video_id: str, *, languages: str='en.*,en') -> SubtitleFetchResult | None:
        if not self.available():
            raise SubtitleFetchError(f'YOUTUBE_YTDLP_NOT_FOUND: {self.executable}')
        with tempfile.TemporaryDirectory(prefix='gmk-subs-') as td:
            root=Path(td)
            out=str(root/'%(id)s.%(ext)s')
            cmd=[self.executable,'--skip-download','--write-subs','--write-auto-subs','--sub-format','vtt','--sub-langs',languages,'--no-warnings','-o',out,video_url]
            try:
                proc=subprocess.run(cmd,check=False,capture_output=True,text=True,timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise SubtitleFetchError(f'YOUTUBE_SUBTITLE_TIMEOUT: {video_id}') from exc
            # yt-dlp may return non-zero when a selected language is unavailable. We still
            # accept a valid VTT if one was written before the error.
            files=sorted(root.glob(f'{video_id}*.vtt')) or sorted(root.glob('*.vtt'))
            if not files:
                if proc.returncode!=0:
                    detail=(proc.stderr or proc.stdout or '').strip()[-800:]
                    if 'subtitle' in detail.casefold() or 'caption' in detail.casefold():
                        return None
                    raise SubtitleFetchError(f'YOUTUBE_SUBTITLE_FAILED: rc={proc.returncode}: {detail}')
                return None
            # Prefer manual-like language filenames before auto-generated variants only when
            # yt-dlp exposes no stronger distinction; provenance is conservative.
            src=files[0]
            cues=parse_vtt(src)
            if not cues:return None
            # persist a copy outside TemporaryDirectory so caller can inspect exact bytes
            persist=Path(tempfile.mkstemp(prefix=f'gmk-{video_id}-',suffix='.vtt')[1])
            persist.write_bytes(src.read_bytes())
            name=src.name
            lang=None
            parts=name.split('.')
            if len(parts)>=3:lang=parts[-2]
            return SubtitleFetchResult(video_id,lang,'YOUTUBE_CAPTION_OR_AUTO_CAPTION',cues,persist)
