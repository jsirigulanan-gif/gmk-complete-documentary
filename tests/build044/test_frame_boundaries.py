import json
import subprocess

import pytest

from gmk_footage.frames import FrameSampler, FrameSamplingError


@pytest.fixture
def video(tmp_path):
    source = tmp_path / 'ten-seconds.mp4'
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
        '-i', 'testsrc=size=64x64:rate=2', '-t', '10',
        '-pix_fmt', 'yuv420p', '-y', str(source),
    ], check=True)
    return source


@pytest.mark.parametrize('end', [None, 10.0, 12.0])
def test_duration_is_exclusive_even_when_interval_lands_on_eof(video, tmp_path, end):
    result = FrameSampler().sample(video, tmp_path / 'frames', interval=5, end=end)
    assert [frame.timestamp for frame in result.frames] == [0.0, 5.0]
    assert all(frame.path.read_bytes().startswith(b'\xff\xd8') for frame in result.frames)
    manifest = json.loads(result.manifest_path.read_text())
    assert [frame['timestamp'] for frame in manifest['frames']] == [0.0, 5.0]


def test_user_end_before_duration_remains_inclusive(video, tmp_path):
    result = FrameSampler().sample(video, tmp_path / 'frames', interval=5, end=5)
    assert [frame.timestamp for frame in result.frames] == [0.0, 5.0]


@pytest.mark.parametrize('interval', [float('nan'), float('inf'), -1, 0])
def test_invalid_interval_fails_before_frame_extraction(video, tmp_path, interval):
    output = tmp_path / 'frames'
    with pytest.raises(FrameSamplingError, match='FRAME_SAMPLING_CONFIG_INVALID'):
        FrameSampler().sample(video, output, interval=interval)
    assert not output.exists()
