from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import subprocess

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.media_tools import resolve_ffprobe, MediaToolNotFound
from .verification import AssetAcquisitionRuntime, AcquisitionVerificationResult


class MediaHandoffError(RuntimeError):
    pass


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out = []
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: x['id'])


def _ext(obj: dict[str, Any]) -> dict[str, Any]:
    return (obj.get('extensions') or {}).get('asset_recon') or {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
    cmd = [
        resolve_ffprobe(), '-v', 'error', '-print_format', 'json',
        '-show_format', '-show_streams', str(path),
    ]
    try:
        cp = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, MediaToolNotFound) as exc:
        raise MediaHandoffError('MEDIA_HANDOFF_FFPROBE_NOT_INSTALLED') from exc
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or '').strip()
        raise MediaHandoffError(f'MEDIA_HANDOFF_FFPROBE_FAILED: {path}: {msg[:300]}') from exc
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise MediaHandoffError(f'MEDIA_HANDOFF_FFPROBE_INVALID_JSON: {path}') from exc


@dataclass(frozen=True)
class MediaHandoffRequirement:
    asset_id: str
    asset_version: int
    candidate_key: str
    beat_key: str
    media_type: str
    rights_status: str
    attribution_required: bool
    source_result_id: str
    source_result_version: int
    canonical_source_url: str
    source_family: str
    source_title: str
    candidate_locator: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            'asset_ref': {'id': self.asset_id, 'version': self.asset_version},
            'candidate_key': self.candidate_key,
            'beat_key': self.beat_key,
            'media_type': self.media_type,
            'rights_status': self.rights_status,
            'attribution_required': self.attribution_required,
            'source_result_ref': {'id': self.source_result_id, 'version': self.source_result_version},
            'canonical_source_url': self.canonical_source_url,
            'source_family': self.source_family,
            'source_title': self.source_title,
            'candidate_locator': deepcopy(self.candidate_locator),
        }


@dataclass(frozen=True)
class MediaHandoffResult:
    requirements: tuple[MediaHandoffRequirement, ...]
    acquisition: AcquisitionVerificationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'requirements': [x.to_dict() for x in self.requirements],
            'acquisition': self.acquisition.to_dict() if self.acquisition else None,
        }


class MediaHandoffRuntime:
    """Validates externally supplied original media before normal acquisition.

    This runtime never downloads media and never treats a webpage, embed locator,
    or metadata record as original bytes. It accepts files supplied through an
    authorized/manual acquisition path, validates them with ffprobe, validates the
    exact video time range, computes an immutable SHA-256, and then delegates to
    AssetAcquisitionRuntime's existing LOCAL_FILE path.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    def requirements(self) -> tuple[MediaHandoffRequirement, ...]:
        loaded = ColdStartLoader(self.root, self.workspace).load()
        state = loaded.engine.snapshot()
        out: list[MediaHandoffRequirement] = []
        for asset in _active_objects(state, 'ASSET'):
            if asset.get('workflow_state') != 'ACQUISITION_PENDING':
                continue
            if asset.get('media_type') != 'VIDEO':
                continue
            ex = _ext(asset)
            rights = asset.get('rights') or {}
            sr_ref = asset.get('origin_search_result_ref') or {}
            sr_id = str(sr_ref.get('id') or '')
            sr_ver = int(sr_ref.get('version') or 0)
            if not sr_id or sr_ver <= 0 or (sr_id, sr_ver) not in state.objects:
                raise MediaHandoffError(f'MEDIA_HANDOFF_ORIGIN_SEARCH_RESULT_REQUIRED: {asset["id"]}')
            sr = state.objects[(sr_id, sr_ver)]
            locator = sr.get('discovery_locator') or {}
            if locator.get('type') != 'WEB_URI' or not str(locator.get('value') or '').strip():
                raise MediaHandoffError(f'MEDIA_HANDOFF_CANONICAL_WEB_SOURCE_REQUIRED: {asset["id"]}')
            inspection = sr.get('inspection') or {}
            out.append(MediaHandoffRequirement(
                asset_id=asset['id'],
                asset_version=int(asset['version']),
                candidate_key=str(ex.get('candidate_key') or ''),
                beat_key=str(ex.get('beat_key') or ''),
                media_type='VIDEO',
                rights_status=str(rights.get('status') or 'UNKNOWN'),
                attribution_required=bool(rights.get('attribution_required', False)),
                source_result_id=sr_id,
                source_result_version=sr_ver,
                canonical_source_url=str(locator['value']),
                source_family=str(sr.get('source_family') or 'UNKNOWN'),
                source_title=str(sr.get('title') or ''),
                candidate_locator=deepcopy(inspection.get('candidate_locator') or {'type':'FULL_SOURCE'}),
            ))
        return tuple(out)

    def _compile_item(self, item: dict[str, Any], allowed: dict[str, MediaHandoffRequirement]) -> dict[str, Any]:
        key = str(item.get('candidate_key') or '')
        if key not in allowed:
            raise MediaHandoffError(f'MEDIA_HANDOFF_CANDIDATE_NOT_PENDING_VIDEO: {key}')
        local_path = Path(str(item.get('local_path') or ''))
        if not local_path.exists() or not local_path.is_file():
            raise MediaHandoffError(f'MEDIA_HANDOFF_FILE_MISSING: {local_path}')
        if local_path.stat().st_size <= 0:
            raise MediaHandoffError(f'MEDIA_HANDOFF_FILE_EMPTY: {local_path}')

        probe = _ffprobe(local_path)
        streams = probe.get('streams') or []
        vstreams = [s for s in streams if s.get('codec_type') == 'video']
        if not vstreams:
            raise MediaHandoffError(f'MEDIA_HANDOFF_VIDEO_STREAM_REQUIRED: {local_path}')
        fmt = probe.get('format') or {}
        try:
            duration = float(fmt.get('duration'))
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0:
            # Some containers expose duration only at stream level.
            vals = []
            for s in vstreams:
                try:
                    vals.append(float(s.get('duration')))
                except (TypeError, ValueError):
                    pass
            duration = max(vals) if vals else 0.0
        if duration <= 0:
            raise MediaHandoffError(f'MEDIA_HANDOFF_DURATION_REQUIRED: {local_path}')

        segment = deepcopy(item.get('segment') or {})
        selector = deepcopy(segment.get('selector') or {})
        if selector.get('type') != 'VIDEO_TIME_RANGE':
            raise MediaHandoffError(f'MEDIA_HANDOFF_VIDEO_TIME_RANGE_REQUIRED: {key}')
        try:
            start = float(selector['start_seconds'])
            end = float(selector['end_seconds'])
        except (KeyError, TypeError, ValueError) as exc:
            raise MediaHandoffError(f'MEDIA_HANDOFF_VIDEO_RANGE_INVALID: {key}') from exc
        if start < 0 or end <= start or end > duration + 0.050:
            raise MediaHandoffError(
                f'MEDIA_HANDOFF_VIDEO_RANGE_OUT_OF_BOUNDS: {key} start={start} end={end} duration={duration}'
            )
        key_sec = selector.get('key_seconds')
        if key_sec is not None:
            try:
                key_val = float(key_sec)
            except (TypeError, ValueError) as exc:
                raise MediaHandoffError(f'MEDIA_HANDOFF_KEY_SECONDS_INVALID: {key}') from exc
            if not (start <= key_val <= end):
                raise MediaHandoffError(f'MEDIA_HANDOFF_KEY_SECONDS_OUT_OF_RANGE: {key}')

        if not str(segment.get('visual_content') or '').strip():
            raise MediaHandoffError(f'MEDIA_HANDOFF_VISUAL_CONTENT_REQUIRED: {key}')
        if not str(segment.get('match_reason') or '').strip():
            raise MediaHandoffError(f'MEDIA_HANDOFF_MATCH_REASON_REQUIRED: {key}')
        if not str(item.get('source_url') or '').strip():
            raise MediaHandoffError(f'MEDIA_HANDOFF_SOURCE_URL_REQUIRED: {key}')
        supplied_url = str(item['source_url']).strip()
        expected_url = str(allowed[key].canonical_source_url).strip()
        if supplied_url != expected_url:
            raise MediaHandoffError(
                f'MEDIA_HANDOFF_SOURCE_LOCK_MISMATCH: {key} expected={expected_url} got={supplied_url}'
            )
        locked_locator = allowed[key].candidate_locator or {}
        if locked_locator.get('type') == 'VIDEO_TIME_RANGE':
            try:
                locked_start = float(locked_locator['start_seconds'])
                locked_end = float(locked_locator['end_seconds'])
            except (KeyError, TypeError, ValueError) as exc:
                raise MediaHandoffError(f'MEDIA_HANDOFF_SOURCE_LOCK_RANGE_INVALID: {key}') from exc
            if start < locked_start - 0.050 or end > locked_end + 0.050:
                raise MediaHandoffError(
                    f'MEDIA_HANDOFF_SOURCE_LOCK_RANGE_EXCEEDED: {key} '
                    f'allowed={locked_start}-{locked_end} got={start}-{end}'
                )
        if not str(item.get('acquisition_method') or '').strip():
            raise MediaHandoffError(f'MEDIA_HANDOFF_ACQUISITION_METHOD_REQUIRED: {key}')

        checksum = _sha256(local_path)
        expected = str(item.get('expected_sha256') or '').strip().lower()
        if expected and expected != checksum:
            raise MediaHandoffError(f'MEDIA_HANDOFF_SHA256_MISMATCH: {key}')

        vs = vstreams[0]
        technical = {
            'container': str(fmt.get('format_name') or 'unknown'),
            'duration_seconds': round(duration, 6),
            'codec': str(vs.get('codec_name') or 'unknown'),
            'width': int(vs.get('width') or 1),
            'height': int(vs.get('height') or 1),
            'audio_present': any(s.get('codec_type') == 'audio' for s in streams),
        }
        return {
            'candidate_key': key,
            'mode': 'LOCAL_FILE',
            'local_path': str(local_path),
            'source_url': str(item['source_url']),
            'acquisition_method': str(item['acquisition_method']),
            'production_ready': True,
            'catalog': True,
            'technical': technical,
            'segment': {
                'selector': selector,
                'source_locator': deepcopy(segment.get('source_locator') or {'type': 'FULL_SOURCE'}),
                'visual_content': str(segment['visual_content']),
                'match_type': str(segment.get('match_type') or 'DIRECT'),
                'match_reason': str(segment['match_reason']),
            },
        }

    def _validate_with_requirements(self, plan: dict[str, Any], requirements: tuple[MediaHandoffRequirement, ...]) -> tuple[dict[str, Any], ...]:
        batch_id = str(plan.get('batch_id') or '').strip()
        if not batch_id:
            raise MediaHandoffError('MEDIA_HANDOFF_BATCH_ID_REQUIRED')
        allowed = {r.candidate_key: r for r in requirements}
        if not allowed:
            raise MediaHandoffError('MEDIA_HANDOFF_NO_PENDING_VIDEO_REQUIREMENTS')
        items = plan.get('items') or []
        keys = [str(x.get('candidate_key') or '') for x in items]
        if set(keys) != set(allowed) or len(keys) != len(set(keys)):
            raise MediaHandoffError(
                f'MEDIA_HANDOFF_COMPLETE_PENDING_SET_REQUIRED: expected={sorted(allowed)} got={sorted(keys)}'
            )
        return tuple(self._compile_item(item, allowed) for item in items)

    def validate_plan(self, plan: dict[str, Any]) -> tuple[tuple[MediaHandoffRequirement, ...], tuple[dict[str, Any], ...]]:
        """Validate a complete handoff plan without mutating workspace state."""
        requirements = self.requirements()
        compiled = self._validate_with_requirements(plan, requirements)
        return requirements, compiled

    def run(self, plan: dict[str, Any]) -> MediaHandoffResult:
        requirements = self.requirements()
        if not requirements:
            loaded = ColdStartLoader(self.root, self.workspace).load()
            if loaded.engine.project_state == 'ASSET_CATALOG_READY':
                return MediaHandoffResult(requirements, None)
            raise MediaHandoffError('MEDIA_HANDOFF_NO_PENDING_VIDEO_REQUIREMENTS')
        compiled = self._validate_with_requirements(plan, requirements)
        acquisition = AssetAcquisitionRuntime(self.root, self.workspace).run({
            'batch_id': str(plan['batch_id']).strip(),
            'items': list(compiled),
        })
        return MediaHandoffResult(requirements, acquisition)
