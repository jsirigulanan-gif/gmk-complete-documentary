"""Free online narration with measured audio timing, independent of Drive availability."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .storage import Project, atomic_json, digest


class VoiceError(RuntimeError):
    pass


def audio_duration(path: Path) -> float:
    p = subprocess.run([os.environ.get('GMK_FFPROBE') or 'ffprobe', '-v', 'error',
                        '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(path)],
                       capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise VoiceError('Generated audio could not be read')
    data = json.loads(p.stdout)
    value = float(data.get('format', {}).get('duration', 0))
    if not any(s.get('codec_type') == 'audio' for s in data.get('streams', [])) or not math.isfinite(value) or value <= 0:
        raise VoiceError('Generated audio has no valid audio stream/duration')
    return value


class EdgeVoice:
    name = 'edge-tts'

    def __init__(self, voice='th-TH-NiwatNeural', rate='-5%', executable=None):
        if voice not in ('th-TH-NiwatNeural', 'th-TH-PremwadeeNeural'):
            raise VoiceError('Select an available Thai voice')
        if not re.fullmatch(r'[+-]\d{1,2}%', rate):
            raise VoiceError('Invalid speech rate')
        self.voice, self.rate = voice, rate
        self.executable = executable or os.environ.get('GMK_EDGE_TTS') or shutil.which('edge-tts')

    def synthesize(self, text: str, dest: Path) -> dict:
        if not self.executable:
            raise VoiceError('Install edge-tts and configure GMK_EDGE_TTS or edge_tts_path in Operator settings')
        if not text.strip():
            raise VoiceError('Narration is empty')
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.voice-') as folder:
            folder = Path(folder)
            source, media, subtitle = folder/'text.txt', folder/'audio.mp3', folder/'captions.srt'
            source.write_text(text, encoding='utf-8')
            try:
                p = subprocess.run([self.executable, '--file', str(source), '--voice', self.voice,
                                    '--rate='+self.rate, '--write-media', str(media), '--write-subtitles', str(subtitle)],
                                   capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VoiceError('Free voice service unavailable/timed out; retry later') from exc
            if p.returncode or not media.is_file():
                raise VoiceError('Free voice service did not produce audio; no paid fallback was used')
            duration = audio_duration(media)
            os.replace(media, dest)
            if subtitle.is_file():
                os.replace(subtitle, dest.with_suffix('.srt'))
            return {'duration_seconds': duration, **digest(dest)}


def generate_voice(project: Project, provider=None, *, limit: int | None = None) -> dict:
    provider = provider or EdgeVoice()
    script_path = project.root / 'script.json'
    script_bytes = script_path.read_bytes()
    script = json.loads(script_bytes)
    scenes = script.get('scenes', [])
    if not scenes or (limit is not None and limit < 1):
        raise VoiceError('No scenes selected for narration')
    selected = scenes if limit is None else scenes[:limit]
    if any(not s.get('narration_th', '').strip() for s in selected):
        raise VoiceError('A selected scene has no Thai narration; review the imported script')
    generated = project.root / 'generated_voice'
    generated.mkdir(exist_ok=True)
    rows, offset = [], 0.0
    for scene in selected:
        text = scene['narration_th']
        identity = {'provider': provider.name, 'voice': provider.voice, 'rate': provider.rate, 'text': text}
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        audio, cache = generated/(key+'.mp3'), generated/(key+'.json')
        valid = False
        if audio.is_file() and cache.is_file():
            try:
                meta = json.loads(cache.read_text())
                valid = digest(audio)['sha256'] == meta.get('sha256')
            except (ValueError, AttributeError):
                valid = False
        if not valid:
            meta = provider.synthesize(text, audio)
            atomic_json(cache, meta)
        # Use measured timing, never the source document's planned scene duration.
        duration = audio_duration(audio)
        asset = project.add_file(audio, 'voice', scenes=[scene['id']])
        subtitle = audio.with_suffix('.srt')
        if subtitle.is_file():
            project.add_file(subtitle, 'voice', scenes=[scene['id']])
        rows.append({'scene_id': scene['id'], 'audio_path': asset['path'], 'sha256': asset['sha256'],
                     'start_seconds': offset, 'end_seconds': offset+duration,
                     'duration_seconds': duration, 'text': text})
        offset += duration
        # Partial results survive failures in subsequent scenes.
        atomic_json(project.root/'voice_progress.json', {'completed_scenes': rows, 'total_scenes': len(scenes)})
    result = {'provider': provider.name, 'voice': provider.voice, 'rate': provider.rate,
              'script_sha256': hashlib.sha256(script_bytes).hexdigest(),
              'complete': len(rows) == len(scenes), 'scenes': rows, 'duration_seconds': offset,
              'timing_status': 'MEASURED_AUDIO', 'listening_review': 'PENDING'}
    timeline = project.root/'voice_timeline.json'
    atomic_json(timeline, result)
    project.add_file(timeline, 'timeline')
    return result
