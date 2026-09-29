from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import shutil
import subprocess


class YouTubeProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeCandidate:
    video_id: str
    title: str
    webpage_url: str
    channel: str
    channel_id: str | None
    duration_seconds: float | None
    description: str
    upload_date: str | None
    view_count: int | None
    availability: str | None
    query: str
    query_family: str
    provider_rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "webpage_url": self.webpage_url,
            "channel": self.channel,
            "channel_id": self.channel_id,
            "duration_seconds": self.duration_seconds,
            "description": self.description,
            "upload_date": self.upload_date,
            "view_count": self.view_count,
            "availability": self.availability,
            "query": self.query,
            "query_family": self.query_family,
            "provider_rank": self.provider_rank,
        }


class YouTubeDiscoveryProvider:
    """Read-only YouTube discovery via yt-dlp search metadata.

    This layer never downloads media. Its only job is search-result discovery and
    normalization so ranking can be tested independently from acquisition.
    """

    def __init__(self, executable: str | Path = "yt-dlp", *, timeout_seconds: int = 45):
        self.executable = str(executable)
        self.timeout_seconds = int(timeout_seconds)

    def available(self) -> bool:
        if Path(self.executable).is_file():
            return True
        return shutil.which(self.executable) is not None

    def _command(self, query: str, limit: int) -> list[str]:
        return [
            self.executable,
            "--dump-single-json",
            "--flat-playlist",
            "--skip-download",
            "--no-warnings",
            "--no-playlist",
            f"ytsearch{int(limit)}:{query}",
        ]

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def search(self, query: str, *, family: str, limit: int = 8) -> tuple[YouTubeCandidate, ...]:
        query = str(query or "").strip()
        if not query:
            raise YouTubeProviderError("YOUTUBE_QUERY_REQUIRED")
        if limit < 1 or limit > 50:
            raise YouTubeProviderError(f"YOUTUBE_LIMIT_INVALID: {limit}")
        if not self.available():
            raise YouTubeProviderError(f"YOUTUBE_YTDLP_NOT_FOUND: {self.executable}")
        try:
            proc = subprocess.run(
                self._command(query, limit),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise YouTubeProviderError(f"YOUTUBE_DISCOVERY_TIMEOUT: {query}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise YouTubeProviderError(f"YOUTUBE_DISCOVERY_FAILED: rc={proc.returncode}: {detail}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise YouTubeProviderError("YOUTUBE_DISCOVERY_JSON_INVALID") from exc

        entries = payload.get("entries") or []
        out: list[YouTubeCandidate] = []
        seen: set[str] = set()
        for idx, item in enumerate(entries, start=1):
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not video_id or not title or video_id in seen:
                continue
            seen.add(video_id)
            url = str(item.get("webpage_url") or item.get("url") or "").strip()
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={video_id}"
            channel = str(item.get("channel") or item.get("uploader") or "").strip()
            out.append(YouTubeCandidate(
                video_id=video_id,
                title=title,
                webpage_url=url,
                channel=channel,
                channel_id=(str(item.get("channel_id")).strip() if item.get("channel_id") else None),
                duration_seconds=self._to_float(item.get("duration")),
                description=str(item.get("description") or "").strip(),
                upload_date=(str(item.get("upload_date")).strip() if item.get("upload_date") else None),
                view_count=self._to_int(item.get("view_count")),
                availability=(str(item.get("availability")).strip() if item.get("availability") else None),
                query=query,
                query_family=str(family),
                provider_rank=idx,
            ))
        return tuple(out)
