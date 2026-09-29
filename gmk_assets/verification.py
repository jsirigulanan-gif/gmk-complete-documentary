from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil

from gmk_operations import OperationRuntime, OperationExecutionResult
from gmk_qa import QARuntime
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore


class AssetAcquisitionError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out = []
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: x['id'])


def _ref(obj: dict[str, Any]) -> dict[str, Any]:
    return {'id': obj['id'], 'version': int(obj['version'])}


def _ext(obj: dict[str, Any]) -> dict[str, Any]:
    return (obj.get('extensions') or {}).get('asset_recon') or {}


@dataclass(frozen=True)
class AcquisitionVerificationResult:
    workspace: Path
    batch_id: str
    project_state: str
    acquired_asset_refs: tuple[dict[str, Any], ...]
    pending_asset_refs: tuple[dict[str, Any], ...]
    segment_refs: tuple[dict[str, Any], ...]
    coverage_report_ref: dict[str, Any]
    coverage_result: str
    asset_catalog_transitioned: bool
    manifest_version: int
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'batch_id': self.batch_id,
            'project_state': self.project_state,
            'acquired_asset_refs': list(self.acquired_asset_refs),
            'pending_asset_refs': list(self.pending_asset_refs),
            'segment_refs': list(self.segment_refs),
            'coverage_report_ref': deepcopy(self.coverage_report_ref),
            'coverage_result': self.coverage_result,
            'asset_catalog_transitioned': self.asset_catalog_transitioned,
            'manifest_version': self.manifest_version,
            'idempotent_replay': self.idempotent_replay,
        }


class AssetAcquisitionRuntime:
    """Verifies immutable acquired bytes and creates production-bounded Segments.

    Network/provider acquisition is intentionally adapter-neutral. This runtime consumes
    bytes that an authorized acquisition adapter has placed in the workspace (or a
    bounded evidence snapshot explicitly supplied by the plan), executes the pre-planned
    DOWNLOAD Operation, checks SHA-256, advances ASSET lifecycle, and only then creates
    SEGMENT objects.

    A WEB_TEXT_SNAPSHOT is a captured evidence representation, not origin-server bytes.
    It may be cataloged for evidence traceability but remains non-production-ready unless
    a later visual capture/source-media acquisition explicitly upgrades it.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    def _asset_by_candidate(self, state, candidate_key: str) -> dict[str, Any]:
        for asset in _active_objects(state, 'ASSET'):
            if _ext(asset).get('candidate_key') == candidate_key:
                return asset
        raise AssetAcquisitionError(f'ACQUISITION_ASSET_NOT_FOUND: {candidate_key}')

    def _existing_segments(self, state, batch_id: str) -> list[dict[str, Any]]:
        return [x for x in _active_objects(state, 'SEGMENT') if ((x.get('extensions') or {}).get('asset_acquisition') or {}).get('batch_id') == batch_id]

    def _existing_coverage(self, state, batch_id: str) -> dict[str, Any] | None:
        for report in _active_objects(state, 'QA_REPORT'):
            if report.get('report_type') != 'ASSET_COVERAGE_REPORT':
                continue
            if ((report.get('extensions') or {}).get('asset_acquisition') or {}).get('batch_id') == batch_id:
                return report
        return None

    @staticmethod
    def _validate_plan(plan: dict[str, Any]) -> None:
        if not str(plan.get('batch_id') or '').strip():
            raise AssetAcquisitionError('ACQUISITION_BATCH_ID_REQUIRED')
        items = plan.get('items') or []
        if not items:
            raise AssetAcquisitionError('ACQUISITION_ITEMS_REQUIRED')
        keys = [str(x.get('candidate_key') or '') for x in items]
        if any(not k for k in keys) or len(keys) != len(set(keys)):
            raise AssetAcquisitionError('ACQUISITION_CANDIDATE_KEYS_INVALID')
        for item in items:
            mode = item.get('mode')
            if mode not in {'LOCAL_FILE', 'WEB_TEXT_SNAPSHOT', 'DEFERRED'}:
                raise AssetAcquisitionError(f'ACQUISITION_MODE_INVALID: {mode}')
            if mode == 'LOCAL_FILE' and not item.get('local_path'):
                raise AssetAcquisitionError('ACQUISITION_LOCAL_PATH_REQUIRED')
            if mode == 'WEB_TEXT_SNAPSHOT' and not str(item.get('snapshot_text') or '').strip():
                raise AssetAcquisitionError('ACQUISITION_SNAPSHOT_TEXT_REQUIRED')

    def _write_input(self, item: dict[str, Any], asset: dict[str, Any]) -> tuple[Path, str]:
        original_dir = self.workspace / 'media' / 'originals'
        original_dir.mkdir(parents=True, exist_ok=True)
        mode = item['mode']
        if mode == 'LOCAL_FILE':
            src = Path(item['local_path'])
            if not src.exists() or not src.is_file():
                raise AssetAcquisitionError(f'ACQUISITION_LOCAL_FILE_MISSING: {src}')
            suffix = src.suffix or '.bin'
            dst = original_dir / f"{asset['id']}{suffix}"
            if not dst.exists():
                shutil.copy2(src, dst)
            elif _sha256_file(dst) != _sha256_file(src):
                raise AssetAcquisitionError(f'ACQUISITION_IMMUTABLE_DEST_CONFLICT: {dst}')
            return dst, 'ORIGINAL_MEDIA'

        if mode == 'WEB_TEXT_SNAPSHOT':
            dst = original_dir / f"{asset['id']}.web-evidence.txt"
            payload = str(item['snapshot_text']).rstrip() + '\n'
            data = payload.encode('utf-8')
            if dst.exists() and dst.read_bytes() != data:
                raise AssetAcquisitionError(f'ACQUISITION_IMMUTABLE_DEST_CONFLICT: {dst}')
            if not dst.exists():
                dst.write_bytes(data)
            return dst, 'WEB_TEXT_SNAPSHOT'

        raise AssetAcquisitionError('DEFERRED_ITEM_HAS_NO_BYTES')

    def run(self, plan: dict[str, Any]) -> AcquisitionVerificationResult:
        plan = deepcopy(plan)
        self._validate_plan(plan)
        batch_id = str(plan['batch_id'])
        loaded = ColdStartLoader(self.root, self.workspace).load()
        engine = loaded.engine
        if engine.project_state not in {'ASSET_RECON', 'ASSET_CATALOG_READY'}:
            raise AssetAcquisitionError(f'ACQUISITION_STATE_INVALID: {engine.project_state}')

        state = engine.snapshot()
        existing_cov = self._existing_coverage(state, batch_id)
        if existing_cov is not None:
            acquired = [a for a in _active_objects(state, 'ASSET') if ((a.get('extensions') or {}).get('asset_acquisition') or {}).get('batch_id') == batch_id and a.get('workflow_state') in {'FILE_VERIFIED','CATALOGED','APPROVED'}]
            pending = [a for a in _active_objects(state, 'ASSET') if a.get('workflow_state') == 'ACQUISITION_PENDING']
            segs = self._existing_segments(state, batch_id)
            return AcquisitionVerificationResult(self.workspace,batch_id,engine.project_state,tuple(_ref(a) for a in acquired),tuple(_ref(a) for a in pending),tuple(_ref(s) for s in segs),_ref(existing_cov),existing_cov.get('result','FAIL'),engine.project_state=='ASSET_CATALOG_READY',engine.manifest_version,True)

        acquired_refs = []
        segment_refs = []
        for item in plan['items']:
            state = engine.snapshot()
            asset = self._asset_by_candidate(state, str(item['candidate_key']))
            if item['mode'] == 'DEFERRED':
                continue
            if asset.get('workflow_state') not in {'ACQUISITION_PENDING','ACQUIRED','FILE_VERIFIED','CATALOGED'}:
                raise AssetAcquisitionError(f"ACQUISITION_ASSET_STATE_INVALID: {asset['id']} {asset.get('workflow_state')}")

            path, representation = self._write_input(item, asset)
            checksum = _sha256_file(path)
            size = path.stat().st_size

            op_ref = asset.get('acquisition_operation_ref')
            if not op_ref:
                raise AssetAcquisitionError(f"ACQUISITION_OPERATION_MISSING: {asset['id']}")
            op_runtime = OperationRuntime(engine)
            op_state = engine.resolver().resolve(op_ref['id'], mode='HEAD')
            terminal_op_ref = deepcopy(op_ref)
            if op_state.get('workflow_state') not in {'SUCCEEDED','PARTIALLY_SUCCEEDED'}:
                outcome = op_runtime.execute(op_ref, lambda _op, p=str(path), c=checksum, s=size: OperationExecutionResult('SUCCEEDED', f'ACQUIRED {p} sha256={c}', {'path':p,'sha256':c,'size_bytes':s}))
                if outcome.get('workflow_state') != 'SUCCEEDED':
                    raise AssetAcquisitionError(f"ACQUISITION_OPERATION_FAILED: {asset['id']} {outcome}")
                terminal_op_ref = deepcopy(outcome['operation_ref'])
            else:
                terminal_op_ref = _ref(op_state)

            # Refresh active Asset because dependency projection may have updated derived fields.
            asset = engine.resolver().resolve(asset['id'], mode='ACTIVE')
            logical_uri = f"gmk://workspace/media/originals/{path.name}"
            ext = deepcopy(asset.get('extensions') or {})
            ext['asset_recon'] = {**(ext.get('asset_recon') or {}), 'production_ready': bool(item.get('production_ready', False))}
            ext['asset_acquisition'] = {
                'batch_id': batch_id,
                'representation': representation,
                'origin_bytes': representation == 'ORIGINAL_MEDIA',
                'source_url': item.get('source_url'),
                'verified_sha256': checksum,
                'acquisition_method': item.get('acquisition_method'),
                'production_ready': bool(item.get('production_ready', False)),
            }
            technical = deepcopy(asset.get('technical') or {})
            technical['file_size_bytes'] = size
            if item.get('technical'):
                technical.update(deepcopy(item['technical']))

            tx = engine.begin()
            v1 = tx.create_version(asset['id'], base_version=asset['version'], patch={
                'workflow_state':'ACQUIRED',
                'acquisition_operation_ref': terminal_op_ref,
                'original_file': {'uri':logical_uri,'checksum':checksum,'immutable':True},
                'technical': technical,
                'extensions': ext,
            })
            tx.promote_active_version(asset['id'], v1['version'], confirm_locked_impact=True)
            tx.commit()
            asset = engine.resolver().resolve(asset['id'], mode='ACTIVE')

            tx = engine.begin()
            v2 = tx.create_version(asset['id'], base_version=asset['version'], patch={'workflow_state':'FILE_VERIFIED'})
            tx.promote_active_version(asset['id'], v2['version'], confirm_locked_impact=True)
            tx.commit()
            asset = engine.resolver().resolve(asset['id'], mode='ACTIVE')

            if bool(item.get('catalog', True)):
                tx = engine.begin()
                v3 = tx.create_version(asset['id'], base_version=asset['version'], patch={'workflow_state':'CATALOGED'})
                tx.promote_active_version(asset['id'], v3['version'], confirm_locked_impact=True)
                tx.commit()
                asset = engine.resolver().resolve(asset['id'], mode='ACTIVE')

            acquired_refs.append(_ref(asset))

            segspec = item.get('segment')
            if segspec:
                tx = engine.begin()
                spayload = {
                    'asset_ref': _ref(asset),
                    'selector': deepcopy(segspec.get('selector') or {'type':'FULL_ASSET'}),
                    'source_locator': deepcopy(segspec.get('source_locator') or {'type':'FULL_SOURCE'}),
                    'visual_content': segspec['visual_content'],
                    'match_type': segspec.get('match_type','DIRECT'),
                    'match_reason': segspec.get('match_reason','Acquired evidence representation supports the Beat.'),
                    'production_state': 'VERIFIED',
                    'extensions': {'asset_acquisition': {'batch_id':batch_id,'candidate_key':item['candidate_key'],'production_ready':bool(item.get('production_ready',False))}},
                }
                sref = tx.create_object('SEGMENT', spayload)
                tx.commit()
                segment_refs.append(sref)

        # Coverage QA is intentionally strict: non-production-ready representations do not satisfy visual coverage.
        state = engine.snapshot()
        beats = _active_objects(state, 'NARRATION_BEAT')
        segs = _active_objects(state, 'SEGMENT')
        prod_by_beat = {}
        for seg in segs:
            se = (seg.get('extensions') or {}).get('asset_acquisition') or {}
            if not se.get('production_ready'):
                continue
            asset = state.objects.get((seg['asset_ref']['id'], int(seg['asset_ref']['version'])))
            if not asset:
                continue
            beat_key = _ext(asset).get('beat_key')
            if beat_key:
                prod_by_beat.setdefault(str(beat_key), []).append(seg)

        findings = []
        for beat in beats:
            beat_key = ((beat.get('extensions') or {}).get('rough_narrative') or {}).get('key')
            if not beat_key:
                continue
            if not prod_by_beat.get(str(beat_key)):
                priority = (beat.get('visual_requirement') or {}).get('priority','STANDARD')
                sev = 'MAJOR' if priority in {'CRITICAL','MAJOR'} else 'MINOR'
                findings.append({
                    'severity':sev,
                    'code':'PRODUCTION_READY_VISUAL_MISSING',
                    'target':_ref(beat),
                    'description':f'{beat_key} has no production-ready verified Segment yet.',
                    'root_cause':{'state':'IDENTIFIED','category':'ASSET'},
                })

        project = _active_objects(state, 'PROJECT')
        if not project:
            raise AssetAcquisitionError('ACQUISITION_PROJECT_MISSING')
        qa = QARuntime(engine).evaluate(report_type='ASSET_COVERAGE_REPORT', scope=_ref(project[0]), findings=findings)
        report = engine.resolver().resolve(qa['report_ref']['id'], mode='ACTIVE')
        tx = engine.begin()
        qv = tx.create_version(report['id'], base_version=report['version'], patch={'extensions':{'asset_acquisition':{'batch_id':batch_id,'production_ready_beat_count':len(prod_by_beat),'total_beat_count':len(beats),'verified_segment_count':len(segment_refs)}}})
        tx.promote_active_version(report['id'], qv['version'], confirm_locked_impact=True)
        tx.commit()

        # A successful coverage retest resolves older open coverage blockers.
        # Without this lifecycle step, historical Build 017 QA issues remain active
        # blockers even after the exact missing production-ready Segments exist.
        if qa['result'] in {'PASS','WARN'}:
            current_report = engine.resolver().resolve(report['id'], mode='ACTIVE')
            state_after_report = engine.snapshot()
            open_coverage_issues = [
                issue for issue in _active_objects(state_after_report, 'QA_ISSUE')
                if issue.get('workflow_state') == 'OPEN'
                and (issue.get('qa_domain') == 'ASSET_COVERAGE_REPORT'
                     or issue.get('code') == 'PRODUCTION_READY_VISUAL_MISSING')
            ]
            qa_runtime = QARuntime(engine)
            for issue in open_coverage_issues:
                qa_runtime.resolve_issue(_ref(issue), _ref(current_report))

        # Only transition once every selected Asset is cataloged and coverage passes.
        state = engine.snapshot()
        selected_assets = [a for a in _active_objects(state,'ASSET') if _ext(a).get('selection_batch_id')]
        all_cataloged = bool(selected_assets) and all(a.get('workflow_state') in {'CATALOGED','APPROVED'} for a in selected_assets)
        transitioned = False
        if all_cataloged and qa['result'] in {'PASS','WARN'} and engine.project_state == 'ASSET_RECON':
            try:
                tx = engine.begin()
                tx.transition_project_state('ASSET_CATALOG_READY', actor_type='AI', human_confirmed=False)
                tx.commit()
                transitioned = True
            except Exception:
                transitioned = False

        manifest = RuntimeStore(self.root, self.workspace).persist(engine)
        loaded2 = ColdStartLoader(self.root, self.workspace).load()
        state2 = loaded2.engine.snapshot()
        acquired = [a for a in _active_objects(state2,'ASSET') if ((a.get('extensions') or {}).get('asset_acquisition') or {}).get('batch_id') == batch_id and a.get('workflow_state') in {'FILE_VERIFIED','CATALOGED','APPROVED'}]
        pending = [a for a in _active_objects(state2,'ASSET') if a.get('workflow_state') == 'ACQUISITION_PENDING']
        segs2 = self._existing_segments(state2,batch_id)
        cov = self._existing_coverage(state2,batch_id)
        if cov is None:
            raise AssetAcquisitionError('ACQUISITION_COVERAGE_REPORT_MISSING_AFTER_PERSIST')
        return AcquisitionVerificationResult(self.workspace,batch_id,loaded2.engine.project_state,tuple(_ref(a) for a in acquired),tuple(_ref(a) for a in pending),tuple(_ref(s) for s in segs2),_ref(cov),cov.get('result','FAIL'),transitioned,manifest['manifest_version'],False)
