from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gmk_orchestrator import GMKOrchestrator
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore


class VisualCoverageError(RuntimeError):
    pass


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out=[]
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: x['id'])


def _ref(obj: dict[str, Any]) -> dict[str, Any]:
    return {'id': obj['id'], 'version': int(obj['version'])}


@dataclass(frozen=True)
class VisualCoverageResult:
    workspace: Path
    project_state: str
    coverage_report_ref: dict[str, Any]
    coverage_result: str
    total_beats: int
    covered_beats: int
    verified_segments: int
    transitioned: bool
    manifest_version: int
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'project_state': self.project_state,
            'coverage_report_ref': dict(self.coverage_report_ref),
            'coverage_result': self.coverage_result,
            'total_beats': self.total_beats,
            'covered_beats': self.covered_beats,
            'verified_segments': self.verified_segments,
            'transitioned': self.transitioned,
            'manifest_version': self.manifest_version,
            'idempotent_replay': self.idempotent_replay,
        }


class VisualCoverageRuntime:
    """Gate-controlled transition from Asset Catalog to Visual Coverage readiness.

    This runtime does not create or upgrade Assets/Segments. It independently
    verifies that the active ASSET_COVERAGE_REPORT is passable and that every
    active Narration Beat has at least one production-ready VERIFIED Segment,
    then advances through the frozen VISUAL_COVERAGE Gate.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root=Path(schema_root)
        self.workspace=Path(workspace)

    @staticmethod
    def _coverage_report(state) -> dict[str, Any]:
        reports=[x for x in _active_objects(state,'QA_REPORT') if x.get('report_type')=='ASSET_COVERAGE_REPORT']
        if not reports:
            raise VisualCoverageError('VISUAL_COVERAGE_REPORT_MISSING')
        return reports[-1]

    @staticmethod
    def _compute(state) -> tuple[int,int,int]:
        beats=_active_objects(state,'NARRATION_BEAT')
        segs=_active_objects(state,'SEGMENT')
        covered=set()
        verified=0
        for seg in segs:
            if seg.get('production_state') != 'VERIFIED':
                continue
            ext=(seg.get('extensions') or {}).get('asset_acquisition') or {}
            if not ext.get('production_ready'):
                continue
            asset=state.objects.get((seg['asset_ref']['id'], int(seg['asset_ref']['version'])))
            if not asset:
                continue
            beat_key=((asset.get('extensions') or {}).get('asset_recon') or {}).get('beat_key')
            if beat_key:
                covered.add(str(beat_key)); verified+=1
        beat_keys=[]
        for beat in beats:
            key=((beat.get('extensions') or {}).get('rough_narrative') or {}).get('key')
            if key: beat_keys.append(str(key))
        return len(beat_keys), len(set(beat_keys) & covered), verified

    def run(self) -> VisualCoverageResult:
        loaded=ColdStartLoader(self.root,self.workspace).load()
        engine=loaded.engine
        if engine.project_state == 'VISUAL_COVERAGE_READY':
            state=engine.snapshot(); report=self._coverage_report(state)
            total,covered,verified=self._compute(state)
            return VisualCoverageResult(self.workspace,engine.project_state,_ref(report),report.get('result','FAIL'),total,covered,verified,False,engine.manifest_version,True)
        if engine.project_state != 'ASSET_CATALOG_READY':
            raise VisualCoverageError(f'VISUAL_COVERAGE_STATE_INVALID: {engine.project_state}')

        state=engine.snapshot(); report=self._coverage_report(state)
        result=report.get('result','FAIL')
        if result not in {'PASS','WARN'}:
            raise VisualCoverageError(f'VISUAL_COVERAGE_REPORT_NOT_PASSABLE: {result}')
        total,covered,verified=self._compute(state)
        if total == 0:
            raise VisualCoverageError('VISUAL_COVERAGE_NO_ACTIVE_BEATS')
        if covered != total:
            raise VisualCoverageError(f'VISUAL_COVERAGE_INCOMPLETE: {covered}/{total}')

        before=engine.project_state
        status=GMKOrchestrator(engine,workspace=self.workspace).advance(actor_type='AI')
        if engine.project_state != 'VISUAL_COVERAGE_READY':
            raise VisualCoverageError(f'VISUAL_COVERAGE_TRANSITION_FAILED: {status}')
        manifest=RuntimeStore(self.root,self.workspace).persist(engine)
        loaded2=ColdStartLoader(self.root,self.workspace).load()
        return VisualCoverageResult(self.workspace,loaded2.engine.project_state,_ref(report),result,total,covered,verified,before!=loaded2.engine.project_state,manifest['manifest_version'],False)
