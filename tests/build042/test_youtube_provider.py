from pathlib import Path
import json
import os
import stat
import tempfile

import pytest

from gmk_footage.youtube_provider import YouTubeDiscoveryProvider, YouTubeProviderError


def _fake_ytdlp(tmp: Path, payload: dict, rc: int = 0) -> Path:
    path = tmp / "yt-dlp"
    raw = json.dumps(payload)
    script = f'''#!/usr/bin/env python3
import sys
if {rc}:
    print("fake failure", file=sys.stderr)
    raise SystemExit({rc})
print({raw!r})
'''
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_provider_normalizes_metadata_without_media_download():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        exe=_fake_ytdlp(tmp,{"entries":[
            {"id":"abc123","title":"P.T. Gamescom 2014 reveal","channel":"Archive Channel","duration":91,"view_count":1000},
            {"id":"def456","title":"Hideo Kojima P.T. interview","uploader":"Interview Channel","url":"https://www.youtube.com/watch?v=def456"},
        ]})
        p=YouTubeDiscoveryProvider(exe)
        rows=p.search("P.T. Gamescom 2014",family="EVENT_ARCHIVE",limit=5)
        assert len(rows)==2
        assert rows[0].video_id=="abc123"
        assert rows[0].webpage_url=="https://www.youtube.com/watch?v=abc123"
        assert rows[0].provider_rank==1
        assert rows[1].channel=="Interview Channel"
        cmd=p._command("P.T. Gamescom 2014",5)
        assert "--skip-download" in cmd
        assert "--flat-playlist" in cmd
        assert not any(x in cmd for x in ["-o","--output"])


def test_provider_deduplicates_and_requires_title_and_id():
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        exe=_fake_ytdlp(tmp,{"entries":[
            {"id":"x","title":"one"},{"id":"x","title":"duplicate"},{"id":"","title":"bad"},{"id":"y","title":"two"}
        ]})
        rows=YouTubeDiscoveryProvider(exe).search("query",family="EXACT_ENTITY")
        assert [x.video_id for x in rows]==["x","y"]


def test_provider_fail_closed_when_executable_missing_or_command_fails():
    with pytest.raises(YouTubeProviderError,match="YOUTUBE_YTDLP_NOT_FOUND"):
        YouTubeDiscoveryProvider("/definitely/missing/yt-dlp").search("q",family="EXACT_ENTITY")
    with tempfile.TemporaryDirectory() as td:
        exe=_fake_ytdlp(Path(td),{},rc=7)
        with pytest.raises(YouTubeProviderError,match="YOUTUBE_DISCOVERY_FAILED"):
            YouTubeDiscoveryProvider(exe).search("q",family="EXACT_ENTITY")
