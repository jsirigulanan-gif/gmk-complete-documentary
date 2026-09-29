from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from gmk_assets import MediaHandoffRuntime, MediaHandoffError, VisualCoverageRuntime
from gmk_runtime.cold_start import ColdStartLoader


class PilotExecutionError(RuntimeError):
    pass


def _stable_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


_DOWNSTREAM_STATES = {
    'VISUAL_COVERAGE_READY', 'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED',
    'DESIGN_DNA_APPROVED', 'SCENE_PLAN_READY', 'SHOT_PLAN_READY', 'HTML_REVIEW',
    'HTML_APPROVED', 'PRODUCTION_RENDER', 'SHOT_QA_PASSED', 'SCENE_QA_PASSED',
    'FULL_FILM_QA_PASSED', 'DELIVERY_READY', 'PROJECT_COMPLETED',
}


@dataclass(frozen=True)
class PilotExecutionPackResult:
    workspace: Path
    project_state: str
    requirement_count: int
    requirements: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]
    execution_manifest_path: Path
    handoff_template_path: Path
    runbook_path: Path
    manifest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'project_state': self.project_state,
            'requirement_count': self.requirement_count,
            'requirements': [deepcopy(x) for x in self.requirements],
            'blockers': list(self.blockers),
            'execution_manifest_path': str(self.execution_manifest_path),
            'handoff_template_path': str(self.handoff_template_path),
            'runbook_path': str(self.runbook_path),
            'manifest_sha256': self.manifest_sha256,
        }


@dataclass(frozen=True)
class PilotExecutionPreflightResult:
    workspace: Path
    project_state: str
    requirement_count: int
    supplied_count: int
    ready: bool
    blockers: tuple[str, ...]
    validated_items: tuple[dict[str, Any], ...]
    plan_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'project_state': self.project_state,
            'requirement_count': self.requirement_count,
            'supplied_count': self.supplied_count,
            'ready': self.ready,
            'blockers': list(self.blockers),
            'validated_items': [deepcopy(x) for x in self.validated_items],
            'plan_sha256': self.plan_sha256,
        }


@dataclass(frozen=True)
class PilotExecutionResult:
    workspace: Path
    starting_state: str
    project_state: str
    handoff_result: dict[str, Any] | None
    visual_coverage_result: dict[str, Any] | None
    manifest_version: int
    idempotent_replay: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'starting_state': self.starting_state,
            'project_state': self.project_state,
            'handoff_result': deepcopy(self.handoff_result),
            'visual_coverage_result': deepcopy(self.visual_coverage_result),
            'manifest_version': self.manifest_version,
            'idempotent_replay': self.idempotent_replay,
        }


class PilotExecutionRuntime:
    """Operational bridge from the real P.T. external-media boundary.

    Build 036 does not invent or download media. It packages the exact current
    source locks, preflights externally supplied files without mutation, and—
    only after a complete passing preflight—delegates to the existing media
    handoff/acquisition runtime. The only automatic downstream transition is the
    frozen AI-with-rules Visual Coverage step. Human-approval stages remain
    separate and untouched.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    def _state(self):
        return ColdStartLoader(self.root, self.workspace).load().engine

    def _requirements(self) -> tuple[dict[str, Any], ...]:
        reqs = MediaHandoffRuntime(self.root, self.workspace).requirements()
        return tuple(x.to_dict() for x in reqs)

    @staticmethod
    def _template_item(req: dict[str, Any]) -> dict[str, Any]:
        key = req['candidate_key']
        loc = deepcopy(req.get('candidate_locator') or {'type': 'FULL_SOURCE'})
        if loc.get('type') == 'VIDEO_TIME_RANGE':
            selector = {
                'type': 'VIDEO_TIME_RANGE',
                'start_seconds': loc.get('start_seconds'),
                'end_seconds': loc.get('end_seconds'),
                'key_seconds': loc.get('key_seconds'),
            }
            range_note = 'Replace with a tighter inspected range if desired; it must remain inside the locked range.'
        else:
            selector = {
                'type': 'VIDEO_TIME_RANGE',
                'start_seconds': None,
                'end_seconds': None,
                'key_seconds': None,
            }
            range_note = 'Inspect the supplied media and fill the exact usable moment before preflight/execute.'
        return {
            'candidate_key': key,
            'local_path': f'REPLACE_WITH_AUTHORIZED_LOCAL_FILE_FOR_{key}',
            'source_url': req['canonical_source_url'],
            'acquisition_method': 'AUTHORIZED_MANUAL_EXPORT',
            'expected_sha256': '',
            'operator_note': range_note,
            'segment': {
                'selector': selector,
                'source_locator': {'type': 'FULL_SOURCE'},
                'visual_content': (
                    'Original creator camera-hack media showing Lisa following behind the player.'
                    if key == 'LISA_X_DIRECT_VERIFIED'
                    else 'Audiovisual Game Awards stage statement preserving speaker, venue, and attribution context.'
                ),
                'match_type': 'DIRECT',
                'match_reason': (
                    'Verified source-locked media bytes directly depict the Lisa camera-hack relationship required by the Beat.'
                    if key == 'LISA_X_DIRECT_VERIFIED'
                    else 'Verified source-locked media bytes directly depict the selected stage statement required by the Beat.'
                ),
            },
        }

    def prepare(self, output_dir: Path) -> PilotExecutionPackResult:
        engine = self._state()
        state = engine.project_state
        if state not in {'ASSET_RECON', 'ASSET_CATALOG_READY'} and state not in _DOWNSTREAM_STATES:
            raise PilotExecutionError(f'PILOT_EXECUTION_STATE_INVALID: {state}')
        reqs = self._requirements()
        blockers: list[str] = []
        if state == 'ASSET_RECON':
            if not reqs:
                blockers.append('ASSET_RECON has no pending source-locked video requirement; inspect workspace consistency.')
            for req in reqs:
                blockers.append(f"MEDIA_REQUIRED:{req['candidate_key']}")
        elif state == 'ASSET_CATALOG_READY':
            blockers.append('MEDIA_ACQUIRED_VISUAL_COVERAGE_NOT_YET_ADVANCED')

        manifest = {
            'build': '036',
            'purpose': 'P.T. source-locked external-media execution pack',
            'workspace': str(self.workspace),
            'project_state': state,
            'schema_status': 'FROZEN_WITH_ERRATA_024_025_029_033',
            'requirements': [deepcopy(x) for x in reqs],
            'blockers': list(blockers),
            'allowed_automatic_progression': ['ASSET_RECON', 'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY'],
            'human_boundary_note': 'No Human Approval stage is auto-executed by this pack.',
        }
        manifest['execution_manifest_sha256'] = _stable_sha(manifest)
        template = {
            'batch_id': 'PT_MEDIA_HANDOFF_036',
            'items': [self._template_item(x) for x in reqs],
        }

        out = Path(output_dir)
        manifest_path = out / 'PT_EXECUTION_MANIFEST.json'
        template_path = out / 'PT_MEDIA_HANDOFF_INPUT.json'
        runbook_path = out / 'PT_EXECUTION_RUNBOOK.md'
        _write_json(manifest_path, manifest)
        _write_json(template_path, template)
        runbook = self._runbook(manifest, template_path.name)
        runbook_path.parent.mkdir(parents=True, exist_ok=True)
        runbook_path.write_text(runbook, encoding='utf-8')
        return PilotExecutionPackResult(
            self.workspace, state, len(reqs), reqs, tuple(blockers),
            manifest_path, template_path, runbook_path, manifest['execution_manifest_sha256'],
        )

    def _runbook(self, manifest: dict[str, Any], input_name: str) -> str:
        lines = [
            '# P.T. Pilot Execution Runbook — Build 036', '',
            f"Current state: `{manifest['project_state']}`", '',
            '## Hard boundary', '',
            'Do not substitute screenshots, webpage text, metadata, unrelated reuploads, or synthetic test media for the two source-locked videos.', '',
            '## Required media', '',
        ]
        for req in manifest['requirements']:
            lines += [
                f"### `{req['candidate_key']}`",
                f"- Asset: `{req['asset_ref']['id']}@{req['asset_ref']['version']}`",
                f"- Source result: `{req['source_result_ref']['id']}@{req['source_result_ref']['version']}`",
                f"- Canonical source: {req['canonical_source_url']}",
                f"- Source family: `{req['source_family']}`",
                f"- Rights status: `{req['rights_status']}`",
                f"- Locked locator: `{json.dumps(req['candidate_locator'], ensure_ascii=False, sort_keys=True)}`",
                '',
            ]
        lines += [
            '## Procedure', '',
            f'1. Copy `{input_name}` and replace each `local_path` with an authorized local video file.',
            '2. Inspect the exact usable moment. Fill `start_seconds`, `end_seconds`, and `key_seconds`; do not guess.',
            '3. Optionally fill `expected_sha256` from an independently recorded checksum.',
            '4. Run preflight. It performs ffprobe, range, source-lock, and checksum checks without mutating the workspace.',
            '5. Only after preflight reports `ready: true`, run execute.',
            '',
            '```bash',
            f'python -m gmk_cli pilot-media-preflight --workspace pilot/PT_WORKSPACE --input {input_name} --json',
            f'python -m gmk_cli pilot-media-execute --workspace pilot/PT_WORKSPACE --input {input_name} --json',
            '```', '',
            'A successful execute closes the two media acquisitions and automatically advances only through `VISUAL_COVERAGE_READY`. Script/TTS/Voice and every Human Approval boundary remain separate.', '',
        ]
        return '\n'.join(lines)

    def preflight(self, plan: dict[str, Any]) -> PilotExecutionPreflightResult:
        engine = self._state()
        state = engine.project_state
        normalized = deepcopy(plan)
        plan_sha = _stable_sha(normalized)
        if state in _DOWNSTREAM_STATES:
            return PilotExecutionPreflightResult(self.workspace, state, 0, len(plan.get('items') or []), True, tuple(), tuple(), plan_sha)
        if state not in {'ASSET_RECON', 'ASSET_CATALOG_READY'}:
            return PilotExecutionPreflightResult(self.workspace, state, 0, len(plan.get('items') or []), False, (f'STATE_INVALID:{state}',), tuple(), plan_sha)
        if state == 'ASSET_CATALOG_READY':
            return PilotExecutionPreflightResult(self.workspace, state, 0, len(plan.get('items') or []), True, tuple(), tuple(), plan_sha)

        handoff = MediaHandoffRuntime(self.root, self.workspace)
        items = plan.get('items') or []
        blockers: list[str] = []
        validated: list[dict[str, Any]] = []
        requirement_count = 0
        try:
            reqs, compiled_items = handoff.validate_plan(plan)
            requirement_count = len(reqs)
            for compiled in compiled_items:
                validated.append({
                    'candidate_key': compiled['candidate_key'],
                    'local_path': compiled['local_path'],
                    'source_url': compiled['source_url'],
                    'technical': deepcopy(compiled['technical']),
                    'selector': deepcopy(compiled['segment']['selector']),
                })
        except (MediaHandoffError, OSError, ValueError) as exc:
            blockers.append(str(exc))
            try:
                requirement_count = len(handoff.requirements())
            except Exception:
                requirement_count = 0
        return PilotExecutionPreflightResult(
            self.workspace, state, requirement_count, len(items), not blockers,
            tuple(blockers), tuple(validated), plan_sha,
        )

    def execute(self, plan: dict[str, Any]) -> PilotExecutionResult:
        # Cold Start once at entry. Later stage runtimes return the exact committed
        # state/version, so reloading after every transition is redundant and can
        # become expensive as manifest history grows.
        engine = self._state()
        starting = engine.project_state
        if starting in _DOWNSTREAM_STATES:
            return PilotExecutionResult(self.workspace, starting, starting, None, None, engine.manifest_version, True)
        if starting not in {'ASSET_RECON', 'ASSET_CATALOG_READY'}:
            raise PilotExecutionError(f'PILOT_EXECUTION_STATE_INVALID: {starting}')

        handoff_result = None
        current_state = starting
        current_manifest_version = engine.manifest_version
        if starting == 'ASSET_RECON':
            try:
                handoff_obj = MediaHandoffRuntime(self.root, self.workspace).run(plan)
                handoff_result = handoff_obj.to_dict()
            except MediaHandoffError as exc:
                raise PilotExecutionError(f'PILOT_EXECUTION_PREFLIGHT_FAILED: {exc}') from exc
            acquisition = handoff_obj.acquisition
            if acquisition is None:
                raise PilotExecutionError('PILOT_EXECUTION_HANDOFF_ACQUISITION_RESULT_REQUIRED')
            current_state = acquisition.project_state
            current_manifest_version = acquisition.manifest_version
            if current_state != 'ASSET_CATALOG_READY':
                raise PilotExecutionError(f'PILOT_EXECUTION_HANDOFF_DID_NOT_REACH_ASSET_CATALOG_READY: {current_state}')

        coverage_result = None
        if current_state == 'ASSET_CATALOG_READY':
            coverage_obj = VisualCoverageRuntime(self.root, self.workspace).run()
            coverage_result = coverage_obj.to_dict()
            current_state = coverage_obj.project_state
            current_manifest_version = coverage_obj.manifest_version
        if current_state != 'VISUAL_COVERAGE_READY':
            raise PilotExecutionError(f'PILOT_EXECUTION_DID_NOT_REACH_VISUAL_COVERAGE_READY: {current_state}')
        return PilotExecutionResult(
            self.workspace, starting, current_state, handoff_result,
            coverage_result, current_manifest_version, False,
        )
