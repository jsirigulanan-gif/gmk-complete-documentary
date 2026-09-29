from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import tempfile

from gmk_runtime.cold_start import ColdStartLoader
from .intake import PilotMediaIntakeRuntime, PilotMediaIntakeError


class PilotReadinessError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


@dataclass(frozen=True)
class PilotReadinessResult:
    workspace: Path
    intake_dir: Path
    project_state: str
    manifest_version: int
    readiness: str
    ready_to_execute: bool
    slots: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]
    next_action: str
    workspace_mutated: bool
    report_json: Path | None = None
    report_markdown: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'intake_dir': str(self.intake_dir),
            'project_state': self.project_state,
            'manifest_version': self.manifest_version,
            'readiness': self.readiness,
            'ready_to_execute': self.ready_to_execute,
            'slots': [deepcopy(x) for x in self.slots],
            'blockers': list(self.blockers),
            'next_action': self.next_action,
            'workspace_mutated': self.workspace_mutated,
            'report_json': str(self.report_json) if self.report_json else None,
            'report_markdown': str(self.report_markdown) if self.report_markdown else None,
        }


class PilotReadinessRuntime:
    """Read-only readiness dashboard for the real P.T. media boundary.

    It never mutates PT_WORKSPACE. It inspects the current pending source locks,
    intake slots and worksheet completeness. When all local inputs exist it runs
    the authoritative intake + media preflight in a temporary output directory,
    so READY_TO_EXECUTE means the same source-lock/checksum/range rules used by
    execution have passed.
    """

    _IGNORED = {'README.txt', '.DS_Store', 'Thumbs.db'}
    _ADVANCED = {
        'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY', 'SCRIPT_READY', 'TTS_READY',
        'VOICE_LOCKED', 'DESIGN_DNA_APPROVED', 'SCENE_PLAN_READY', 'SHOT_PLAN_READY',
        'HTML_REVIEW', 'HTML_APPROVED', 'PRODUCTION_RENDER', 'SHOT_QA_PASSED',
        'SCENE_QA_PASSED', 'FULL_FILM_QA_PASSED', 'DELIVERY_READY', 'PROJECT_COMPLETED',
    }

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    def _snapshot(self) -> tuple[str, int, str]:
        state = ColdStartLoader(self.root, self.workspace).load().engine
        pointer = self.workspace / 'CURRENT_MANIFEST.json'
        sha = _sha256_file(pointer) if pointer.is_file() else ''
        return state.project_state, state.manifest_version, sha

    @staticmethod
    def _worksheet(intake_dir: Path) -> dict[str, Any] | None:
        path = intake_dir / 'PT_MEDIA_INSPECTION_WORKSHEET.json'
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    @classmethod
    def _media_files(cls, slot: Path) -> list[Path]:
        if not slot.is_dir():
            return []
        return [
            p for p in slot.iterdir()
            if p.is_file() and p.name not in cls._IGNORED and not p.name.startswith('.')
        ]

    @staticmethod
    def _inspection_status(item: dict[str, Any] | None) -> tuple[bool, list[str]]:
        if not item:
            return False, ['inspection entry missing']
        missing = []
        for field in ('operator', 'inspection_note', 'visual_content', 'match_reason'):
            if not str(item.get(field) or '').strip():
                missing.append(field)
        for field in ('start_seconds', 'end_seconds'):
            if item.get(field) is None:
                missing.append(field)
        return not missing, missing

    def inspect(self, intake_dir: Path, output_dir: Path | None = None) -> PilotReadinessResult:
        intake = Path(intake_dir)
        before_state, before_version, before_sha = self._snapshot()

        if before_state in self._ADVANCED:
            readiness = 'ALREADY_ADVANCED'
            next_action = (
                'Media acquisition is already past ASSET_RECON. Continue from the current project state; '
                'do not rescan or re-import the two source-locked videos.'
            )
            result = PilotReadinessResult(
                self.workspace, intake, before_state, before_version, readiness, True,
                tuple(), tuple(), next_action, False,
            )
            return self._emit(result, output_dir)

        if before_state != 'ASSET_RECON':
            raise PilotReadinessError(f'PILOT_READINESS_STATE_INVALID: {before_state}')

        manifest_path = intake / 'PT_MEDIA_INTAKE_MANIFEST.json'
        if not manifest_path.is_file():
            raise PilotReadinessError('PILOT_READINESS_INTAKE_MANIFEST_REQUIRED')
        try:
            intake_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception as exc:
            raise PilotReadinessError(f'PILOT_READINESS_INTAKE_MANIFEST_INVALID: {exc}') from exc
        requirements = tuple(deepcopy(x) for x in (intake_manifest.get('requirements') or []))
        if not requirements:
            raise PilotReadinessError('PILOT_READINESS_NO_PENDING_REQUIREMENTS')

        worksheet = self._worksheet(intake)
        inspection_items = {}
        worksheet_batch = ''
        worksheet_error = None
        if worksheet is None:
            worksheet_error = 'PT_MEDIA_INSPECTION_WORKSHEET.json missing or invalid'
        else:
            worksheet_batch = str(worksheet.get('batch_id') or '').strip()
            for item in worksheet.get('items') or []:
                key = str(item.get('candidate_key') or '').strip()
                if key and key not in inspection_items:
                    inspection_items[key] = item

        slots = []
        blockers: list[str] = []
        media_complete = True
        inspection_complete = worksheet_error is None and bool(worksheet_batch)

        if worksheet_error:
            blockers.append(f'WORKSHEET:{worksheet_error}')
        elif not worksheet_batch:
            blockers.append('WORKSHEET:batch_id missing')
            inspection_complete = False

        for req in requirements:
            key = req['candidate_key']
            slot = intake / key
            files = self._media_files(slot)
            if len(files) == 0:
                media_state = 'MISSING'
                media_complete = False
                blockers.append(f'MEDIA_MISSING:{key}')
            elif len(files) > 1:
                media_state = 'MULTIPLE'
                media_complete = False
                blockers.append(f'MEDIA_MULTIPLE:{key}:{len(files)}')
            else:
                media_state = 'PRESENT'

            item = inspection_items.get(key)
            insp_ok, missing_fields = self._inspection_status(item)
            if not insp_ok:
                inspection_complete = False
                blockers.append(f'INSPECTION_INCOMPLETE:{key}:{"|".join(missing_fields)}')

            source_ok = bool(item) and str(item.get('source_url') or '').strip() == req['canonical_source_url']
            if item and not source_ok:
                inspection_complete = False
                blockers.append(f'SOURCE_URL_MISMATCH:{key}')

            slots.append({
                'candidate_key': key,
                'canonical_source_url': req['canonical_source_url'],
                'slot_dir': str(slot),
                'media_state': media_state,
                'media_file': str(files[0]) if len(files) == 1 else None,
                'inspection_complete': insp_ok and source_ok,
                'inspection_missing_fields': missing_fields,
                'source_url_matches_lock': source_ok,
                'locked_locator': deepcopy(req.get('locked_locator')),
                'asset_ref': deepcopy(req.get('asset_ref')),
                'source_result_ref': deepcopy(req.get('source_result_ref')),
            })

        preflight_error = None
        preflight_ready = False
        if media_complete and inspection_complete and worksheet is not None:
            try:
                # PilotMediaIntakeRuntime.build delegates to MediaHandoffRuntime.validate_plan,
                # which is the authoritative source-lock/range/checksum/ffprobe validation.
                # Do not immediately run PilotExecutionRuntime.preflight again; that would
                # repeat the same expensive validation without adding a new safety boundary.
                with tempfile.TemporaryDirectory(prefix='gmk-pt-readiness-') as td:
                    built = PilotMediaIntakeRuntime(self.root, self.workspace).build(intake, worksheet, Path(td))
                    preflight_ready = bool(built.ready)
            except Exception as exc:
                preflight_error = str(exc)
                blockers.append(f'PREFLIGHT:{preflight_error}')

        if not media_complete:
            readiness = 'BLOCKED_MEDIA'
            next_action = 'Place exactly one authorized source-locked video in every missing intake slot.'
        elif not inspection_complete:
            readiness = 'BLOCKED_INSPECTION'
            next_action = 'Complete the human inspection worksheet for both videos, including exact usable time ranges.'
        elif not preflight_ready:
            readiness = 'BLOCKED_PREFLIGHT'
            next_action = 'Fix the reported source-lock, checksum, technical-media, or time-range preflight error before execution.'
        else:
            readiness = 'READY_TO_EXECUTE'
            next_action = 'Run pilot-media-process with explicit --execute after reviewing the generated readiness report.'

        pointer = self.workspace / 'CURRENT_MANIFEST.json'
        after_sha = _sha256_file(pointer) if pointer.is_file() else ''
        if before_sha != after_sha:
            raise PilotReadinessError('PILOT_READINESS_NON_MUTATING_GUARD_FAILED')

        result = PilotReadinessResult(
            self.workspace, intake, before_state, before_version, readiness,
            readiness == 'READY_TO_EXECUTE', tuple(slots), tuple(blockers), next_action, False,
        )
        return self._emit(result, output_dir)

    def _emit(self, result: PilotReadinessResult, output_dir: Path | None) -> PilotReadinessResult:
        if output_dir is None:
            return result
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        json_path = out / 'PT_PILOT_READINESS.json'
        md_path = out / 'PT_PILOT_READINESS.md'
        payload = result.to_dict()
        payload['build'] = '039'
        payload['report_json'] = str(json_path)
        payload['report_markdown'] = str(md_path)
        _write_json(json_path, payload)
        lines = [
            '# P.T. Pilot Readiness — Build 039', '',
            f"- Project state: `{result.project_state}`",
            f"- Manifest version: `{result.manifest_version}`",
            f"- Readiness: **{result.readiness}**",
            f"- Ready to execute: **{'YES' if result.ready_to_execute else 'NO'}**", '',
            '## Media slots', '',
        ]
        for s in result.slots:
            lines += [
                f"### `{s['candidate_key']}`",
                f"- Media: `{s['media_state']}`",
                f"- Inspection complete: `{s['inspection_complete']}`",
                f"- Source lock: {s['canonical_source_url']}",
                f"- Slot: `{s['slot_dir']}`", '',
            ]
        if result.blockers:
            lines += ['## Blockers', ''] + [f'- `{x}`' for x in result.blockers] + ['']
        lines += ['## Next action', '', result.next_action, '',
                  '> This report is read-only. It does not mutate PT_WORKSPACE.', '']
        md_path.write_text('\n'.join(lines), encoding='utf-8')
        return PilotReadinessResult(
            result.workspace, result.intake_dir, result.project_state, result.manifest_version,
            result.readiness, result.ready_to_execute, result.slots, result.blockers,
            result.next_action, result.workspace_mutated, json_path, md_path,
        )
