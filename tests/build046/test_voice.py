import json
import shutil
import subprocess

import pytest

from gmk_projects.storage import Project, atomic_json, digest
from gmk_projects.voice import VoiceError, audio_duration, generate_voice


class TestVoiceProvider:
    __test__ = False
    name, voice, rate = 'TEST_ONLY', 'test', '+0%'

    def __init__(self):
        self.calls = 0
        self.fail_at = None

    def synthesize(self, text, dest):
        self.calls += 1
        if self.calls == self.fail_at:
            raise VoiceError('service unavailable')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.3',
                        str(dest)], check=True, capture_output=True)
        return {'duration_seconds': audio_duration(dest), **digest(dest)}


@pytest.fixture
def project(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('ffmpeg/ffprobe required for actual audio timing tests')
    p = Project.create(tmp_path, 'Voice timing test')
    atomic_json(p.root/'script.json', {'scenes': [
        {'id': 'SHOT-001', 'narration_th': 'ทดสอบฉากแรก', 'planned_seconds': 90},
        {'id': 'SHOT-002', 'narration_th': 'ทดสอบฉากสอง', 'planned_seconds': 120}]})
    return p


def test_measured_timing_and_cache_resume(project):
    provider = TestVoiceProvider()
    r = generate_voice(project, provider)
    assert r['complete']
    assert 0 < r['duration_seconds'] < 2  # Source planned times were 210 seconds.
    assert r['scenes'][0]['end_seconds'] == r['scenes'][1]['start_seconds']
    assert r['listening_review'] == 'PENDING'
    generate_voice(project, provider)
    assert provider.calls == 2
    audio = next((project.root/'generated_voice').glob('*.mp3'))
    audio.write_bytes(b'corrupted')
    generate_voice(project, provider)
    assert provider.calls == 3


def test_partial_voice_survives_failure(project):
    provider = TestVoiceProvider()
    provider.fail_at = 2
    with pytest.raises(VoiceError):
        generate_voice(project, provider)
    progress = json.loads((project.root/'voice_progress.json').read_text())
    assert len(progress['completed_scenes']) == 1
    assert not (project.root/'voice_timeline.json').exists()
    provider.fail_at = None
    result = generate_voice(project, provider)
    assert result['complete']
    assert provider.calls == 3  # Retry uses cached first scene.


def test_preview_not_marked_complete(project):
    assert generate_voice(project, TestVoiceProvider(), limit=1)['complete'] is False
