from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

from .frames import FrameSampler, FrameInspectionBundle
from .query_planner import BeatSearchIntent


class VisualSemanticError(RuntimeError):
    pass


def _tokens(text: str) -> set[str]:
    vals = re.findall(r"[A-Za-z0-9][A-Za-z0-9._'-]*", str(text or "").casefold())
    stop = {"the", "and", "for", "with", "from", "that", "this", "video", "footage", "image", "frame", "shows", "showing"}
    return {x.strip("._'-") for x in vals if len(x.strip("._'-")) >= 2 and x not in stop}


def _coverage(target: set[str], text: str) -> float:
    if not target:
        return 0.0
    got = _tokens(text)
    return len(target & got) / len(target)


@dataclass(frozen=True)
class VisualObservation:
    frame_path: Path
    timestamp: float
    description: str
    provider: str
    provider_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_path": str(self.frame_path),
            "timestamp": self.timestamp,
            "description": self.description,
            "provider": self.provider,
            "provider_confidence": self.provider_confidence,
        }


class VisionProvider(Protocol):
    name: str

    def describe(self, frame_path: Path, *, prompt: str) -> VisualObservation:
        ...


class OllamaVisionProvider:
    """Pixel-grounded local vision provider via Ollama's localhost HTTP API.

    The model is explicit rather than guessed. Set GMK_VISION_MODEL or pass model=.
    No external credentials, cookies, DRM/access-control bypass, or remote upload is used.
    """

    name = "OLLAMA_VISION"

    def __init__(self, model: str | None = None, endpoint: str | None = None, timeout: float = 90.0):
        self.model = str(model or os.environ.get("GMK_VISION_MODEL") or "").strip()
        self.endpoint = str(endpoint or os.environ.get("GMK_OLLAMA_ENDPOINT") or "http://127.0.0.1:11434/api/generate").strip()
        self.timeout = float(timeout)
        if not self.model:
            raise VisualSemanticError("VISION_MODEL_REQUIRED: set GMK_VISION_MODEL or pass model=")

    def describe(self, frame_path: Path, *, prompt: str) -> VisualObservation:
        p = Path(frame_path)
        if not p.is_file():
            raise VisualSemanticError(f"VISION_FRAME_MISSING: {p}")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [base64.b64encode(p.read_bytes()).decode("ascii")],
            "stream": False,
            "options": {"temperature": 0},
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise VisualSemanticError(f"VISION_PROVIDER_FAILED: {exc}") from exc
        desc = str(data.get("response") or "").strip()
        if not desc:
            raise VisualSemanticError("VISION_PROVIDER_EMPTY_RESPONSE")
        return VisualObservation(p, 0.0, desc, self.name, None)


class SidecarVisionProvider:
    """Deterministic provider for fixtures/offline QA.

    Reads `<frame>.vision.txt`. It never claims to inspect pixels and is intentionally
    named SIDE_CAR_FIXTURE in manifests so test evidence cannot be confused with real vision.
    """

    name = "SIDE_CAR_FIXTURE"

    def describe(self, frame_path: Path, *, prompt: str) -> VisualObservation:
        p = Path(frame_path)
        side = p.with_suffix(p.suffix + ".vision.txt")
        if not side.is_file():
            raise VisualSemanticError(f"VISION_SIDECAR_MISSING: {side}")
        return VisualObservation(p, 0.0, side.read_text(encoding="utf-8").strip(), self.name, None)


@dataclass(frozen=True)
class VisualFrameScore:
    timestamp: float
    frame_path: Path
    description: str
    score: float
    score_breakdown: dict[str, float]
    provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "frame_path": str(self.frame_path),
            "description": self.description,
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "provider": self.provider,
        }


@dataclass(frozen=True)
class VisualTimestampMatch:
    start: float
    end: float
    key_time: float
    score: float
    description: str
    provider: str
    frame_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "key_time": self.key_time,
            "score": self.score,
            "description": self.description,
            "provider": self.provider,
            "frame_path": str(self.frame_path),
        }


@dataclass(frozen=True)
class VisualMatchReport:
    source_path: Path
    beat_key: str
    frames: tuple[VisualFrameScore, ...]
    matches: tuple[VisualTimestampMatch, ...]
    inspection_manifest: Path
    match_manifest: Path
    report_sha256: str


class VisualSemanticMatcher:
    """Ground visual-only candidates in sampled pixels through a configurable vision model.

    Metadata is not accepted as visual proof. The provider receives actual sampled image
    bytes (or an explicit fixture sidecar in tests), descriptions are scored against the
    Narration Beat visual intent, and only threshold-passing frames nominate timestamps.
    """

    def __init__(self, provider: VisionProvider, *, sampler: FrameSampler | None = None):
        self.provider = provider
        self.sampler = sampler or FrameSampler()

    @staticmethod
    def _prompt(intent: BeatSearchIntent) -> str:
        return (
            "Describe only what is visibly present in this documentary frame. "
            "Do not infer off-screen events or rely on filenames. Be concrete about people, "
            "objects, locations, text/signage, actions, and composition. "
            f"The editor is looking for visual evidence matching: {intent.viewer_must_see}. "
            f"Context only: {intent.viewer_takeaway}."
        )

    @staticmethod
    def _score(intent: BeatSearchIntent, description: str) -> tuple[float, dict[str, float]]:
        visual = _coverage(_tokens(intent.viewer_must_see), description)
        entity = _coverage(_tokens(" ".join(intent.entity_terms)), description)
        claims = _coverage(_tokens(" ".join(intent.claim_texts)), description)
        takeaway = _coverage(_tokens(intent.viewer_takeaway), description)
        # Visual target dominates because this stage exists specifically to prove imagery.
        score = min(1.0, visual * 0.58 + entity * 0.22 + claims * 0.12 + takeaway * 0.08)
        return round(score, 6), {
            "visual_coverage": round(visual, 6),
            "entity_coverage": round(entity, 6),
            "claim_coverage": round(claims, 6),
            "takeaway_coverage": round(takeaway, 6),
        }

    def match(
        self,
        intent: BeatSearchIntent,
        source_path: Path,
        output_dir: Path,
        *,
        interval: float = 5.0,
        max_frames: int = 60,
        threshold: float = 0.28,
        clip_seconds: float = 5.0,
        top_k: int = 3,
    ) -> VisualMatchReport:
        if not (0.0 <= threshold <= 1.0) or clip_seconds <= 0 or top_k < 1:
            raise VisualSemanticError("VISION_MATCH_CONFIG_INVALID")
        out = Path(output_dir)
        frames_dir = out / "frames"
        bundle: FrameInspectionBundle = self.sampler.sample(source_path, frames_dir, interval=interval, max_frames=max_frames)
        scored: list[VisualFrameScore] = []
        prompt = self._prompt(intent)
        for fr in bundle.frames:
            obs = self.provider.describe(fr.path, prompt=prompt)
            desc = obs.description.strip()
            score, breakdown = self._score(intent, desc)
            scored.append(VisualFrameScore(fr.timestamp, fr.path, desc, score, breakdown, obs.provider))

        eligible = [x for x in scored if x.score >= threshold]
        eligible.sort(key=lambda x: (-x.score, x.timestamp, str(x.frame_path)))
        matches: list[VisualTimestampMatch] = []
        half = clip_seconds / 2.0
        for row in eligible[:top_k]:
            start = max(0.0, row.timestamp - half)
            end = min(bundle.duration_seconds, row.timestamp + half)
            if end <= start:
                continue
            matches.append(VisualTimestampMatch(start, end, row.timestamp, row.score, row.description, row.provider, row.frame_path))

        body = {
            "beat_key": intent.beat_key,
            "source_path": str(Path(source_path).resolve()),
            "source_sha256": hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
            "provider": getattr(self.provider, "name", type(self.provider).__name__),
            "threshold": threshold,
            "interval": interval,
            "clip_seconds": clip_seconds,
            "frames": [x.to_dict() for x in scored],
            "matches": [x.to_dict() for x in matches],
            "inspection_manifest": str(bundle.manifest_path),
        }
        sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        body["report_sha256"] = sha
        out.mkdir(parents=True, exist_ok=True)
        manifest = out / "VISUAL_SEMANTIC_MATCH.json"
        manifest.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return VisualMatchReport(Path(source_path), intent.beat_key, tuple(scored), tuple(matches), bundle.manifest_path, manifest, sha)
