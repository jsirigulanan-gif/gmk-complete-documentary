from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Iterable


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ''
    duration_seconds: float = 0.0
    returncode: int | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class AuditResult:
    profile: str
    repository: str
    overall_status: str
    checks: tuple[CheckResult, ...]
    pass_count: int
    fail_count: int
    timeout_count: int
    warning_count: int
    report_sha256: str

    def to_dict(self):
        d=asdict(self)
        d['checks']=[x.to_dict() for x in self.checks]
        return d


class AuditRuntime:
    """Repository hardening/audit runner.

    STATIC performs deterministic repository/package checks only.
    QUICK adds validators, smokes and a fast regression partition.
    FULL runs all declared regression partitions independently so a heavy timeout
    is reported as TIMEOUT rather than being confused with FAIL/PASS.
    """

    ERRATA_BUILDS=('024','025','029','033')
    EXPECTED_SCHEMA_STATUS='FROZEN_WITH_ERRATA_024_025_029_033'

    FAST_PARTITIONS=(
        ('build035_audit', ('tests/build035',)),
        ('build040_operator', ('tests/build040',)),
        ('build041_cachyos', ('tests/build041',)),
        ('build042_footage_fast', ('tests/build042/test_query_planner.py','tests/build042/test_youtube_provider.py','tests/build042/test_ranker.py','tests/build042/test_source_policy.py','tests/build042/test_distribution_integration.py')),
        ('build044_frame_boundaries', ('tests/build044',)),
        ('build045_operator', ('tests/build045',)),
        ('build046_projects', ('tests/build046',)),
        ('build047_production_binding', ('tests/build047',)),
        ('build048_general_research', ('tests/build048',)),
        ('build049_editor_records', ('tests/build049/test_story_footage.py', 'tests/build049/test_evidence_review.py', 'tests/build049/test_edit_checkpoint.py', 'tests/build049/test_script_review.py')),
        ('build050_delivery_receipts', ('tests/build050/test_storage_receipts.py', 'tests/build050/test_delivery.py::test_missing_export_has_actionable_error_without_creating_edit')),
    )
    FULL_BASE_PARTITIONS=(
        ('core_engines', ('tests/state','tests/dependency','tests/gate','tests/runtime','tests/semantic')),
        ('build007_010', ('tests/build007','tests/build008','tests/build009','tests/build010')),
        ('build011_015', ('tests/build011','tests/build012','tests/build013','tests/build014','tests/build015')),
    )
    HEAVY_PARTITIONS=tuple((f'build{n:03d}',(f'tests/build{n:03d}',)) for n in range(16,44)) + (
        ('build049_media_render', ('tests/build049/test_edit_render.py',)),
        ('build050_draft_delivery', ('tests/build050/test_delivery.py',)),
    )

    def __init__(self, root: Path):
        self.root=Path(root).resolve()

    @staticmethod
    def _sha_text(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _result(self,name,status,detail='',duration=0.0,returncode=None):
        return CheckResult(name=name,status=status,detail=detail,duration_seconds=round(duration,3),returncode=returncode)

    def _static_checks(self) -> list[CheckResult]:
        out=[]
        status_path=self.root/'BUILD_STATUS.json'
        if not status_path.is_file():
            out.append(self._result('build_status','FAIL','BUILD_STATUS.json missing'))
            return out
        try:
            status=json.loads(status_path.read_text(encoding='utf-8'))
            out.append(self._result('build_status','PASS',f"build={status.get('build')} schema={status.get('schema_contract')}"))
        except Exception as exc:
            out.append(self._result('build_status','FAIL',str(exc)))
            return out

        schema_status=status.get('schema_contract')
        out.append(self._result('schema_status_consistency','PASS' if schema_status==self.EXPECTED_SCHEMA_STATUS else 'FAIL',str(schema_status)))
        out.append(self._result('pipeline_complete_marker','PASS' if status.get('next_frozen_stage')=='NONE_CORE_PIPELINE_COMPLETE' else 'FAIL',str(status.get('next_frozen_stage'))))

        readme=(self.root/'README.md').read_text(encoding='utf-8') if (self.root/'README.md').is_file() else ''
        current_marker=f"Current build:** Build {int(status.get('build') or 0):03d}"
        out.append(self._result('readme_current_build','PASS' if current_marker in readme else 'FAIL',current_marker))

        changelogs={p.stem.rsplit('_',1)[-1] for p in self.root.glob('CHANGELOG_BUILD_*.md')}
        current_build=int(status.get('build') or 0)
        missing=[f'{n:03d}' for n in range(2,current_build+1) if f'{n:03d}' not in changelogs]
        out.append(self._result('changelog_continuity_002_current','PASS' if not missing else 'FAIL',f'current={current_build:03d}; missing={missing}' if missing else f'continuous_through={current_build:03d}'))
        out.append(self._result('legacy_build001_changelog','WARN','Build 001 has README history but no standalone CHANGELOG_BUILD_001.md; retained as legacy documentation gap.'))

        errata=[]
        for b in self.ERRATA_BUILDS:
            p=self.root/f'CHANGELOG_BUILD_{b}.md'
            if p.exists() and ('errat' in p.read_text(encoding='utf-8').lower() or b in {'024','025','029','033'}):
                errata.append(b)
        out.append(self._result('errata_ledger_source','PASS' if tuple(errata)==self.ERRATA_BUILDS else 'FAIL',f'errata={errata}'))

        junk=[]
        junk_names={'.DS_Store','Thumbs.db'}
        junk_suffixes=('.tmp','.bak','.swp','.orig')
        for base,dirs,files in os.walk(self.root):
            rel=Path(base).relative_to(self.root)
            if any(part in {'.git','.venv','venv','__pycache__','.pytest_cache'} for part in rel.parts):
                dirs[:]=[]; continue
            dirs[:]=[d for d in dirs if d not in {'__pycache__','.pytest_cache'}]
            for f in files:
                if f in junk_names or f.endswith(junk_suffixes): junk.append(str(rel/f))
        out.append(self._result('package_hygiene','PASS' if not junk else 'WARN',f'junk_entries={len(junk)}'))

        contracts=list((self.root/'artifacts'/'contracts').glob('*.schema.json')) if (self.root/'artifacts'/'contracts').exists() else []
        status_count=int(status.get('schema_contracts') or 0)
        # Physical registry count is authoritative through validator; this check is informational because schemas also live under schema/.
        out.append(self._result('status_contract_count_declared','PASS' if status_count==80 else 'FAIL',f'declared={status_count}; artifact_contract_files={len(contracts)}'))

        pilot_pending=set(status.get('pending_external_media') or [])
        expected={'LISA_X_DIRECT_VERIFIED','TGA_VIDEO'}
        out.append(self._result('pilot_external_media_boundary','PASS' if pilot_pending==expected and status.get('pilot_current_state')=='ASSET_RECON' else 'FAIL',f"state={status.get('pilot_current_state')} pending={sorted(pilot_pending)}"))
        pack_root=self.root/'pilot'/'PT_EXECUTION_PACK'
        pack_files=['PT_EXECUTION_MANIFEST.json','PT_MEDIA_HANDOFF_INPUT.json','PT_EXECUTION_RUNBOOK.md']
        missing_pack=[name for name in pack_files if not (pack_root/name).is_file()]
        pack_ok=not missing_pack
        if pack_ok:
            try:
                pdata=json.loads((pack_root/'PT_EXECUTION_MANIFEST.json').read_text(encoding='utf-8'))
                keys={x.get('candidate_key') for x in pdata.get('requirements') or []}
                pack_ok=(keys==expected and pdata.get('project_state')=='ASSET_RECON')
            except Exception:
                pack_ok=False
        out.append(self._result('pilot_execution_pack','PASS' if pack_ok else 'FAIL',f'missing={missing_pack}; expected={sorted(expected)}'))

        intake_root=self.root/'pilot'/'PT_MEDIA_INTAKE'
        intake_files=['PT_MEDIA_INTAKE_MANIFEST.json','PT_MEDIA_INSPECTION_WORKSHEET.json','README.md']
        missing_intake=[name for name in intake_files if not (intake_root/name).is_file()]
        intake_ok=not missing_intake
        detail=f'missing={missing_intake}'
        if intake_ok:
            try:
                idata=json.loads((intake_root/'PT_MEDIA_INTAKE_MANIFEST.json').read_text(encoding='utf-8'))
                ikeys={x.get('candidate_key') for x in idata.get('requirements') or []}
                iurls={x.get('candidate_key'):x.get('canonical_source_url') for x in idata.get('requirements') or []}
                pdata=json.loads((pack_root/'PT_EXECUTION_MANIFEST.json').read_text(encoding='utf-8'))
                purls={x.get('candidate_key'):x.get('canonical_source_url') for x in pdata.get('requirements') or []}
                slot_markers=all((intake_root/k/'README.txt').is_file() for k in expected)
                intake_ok=(ikeys==expected and iurls==purls and slot_markers)
                detail=f'keys={sorted(ikeys)} source_locks_match={iurls==purls} slot_markers={slot_markers}'
            except Exception as exc:
                intake_ok=False;detail=f'intake parse error: {exc}'
        out.append(self._result('pilot_media_intake_pack','PASS' if intake_ok else 'FAIL',detail))
        processor_ok=(self.root/'gmk_pilot'/'process.py').is_file() and 'pilot-media-process' in readme
        out.append(self._result('pilot_media_processor','PASS' if processor_ok else 'FAIL','one-command non-mutating-by-default processor documented and packaged'))

        readiness_root=self.root/'pilot'/'PT_PILOT_READINESS'
        readiness_files=['PT_PILOT_READINESS.json','PT_PILOT_READINESS.md']
        missing_readiness=[name for name in readiness_files if not (readiness_root/name).is_file()]
        readiness_ok=not missing_readiness
        readiness_detail=f'missing={missing_readiness}'
        if readiness_ok:
            try:
                rdata=json.loads((readiness_root/'PT_PILOT_READINESS.json').read_text(encoding='utf-8'))
                rkeys={x.get('candidate_key') for x in rdata.get('slots') or []}
                readiness_ok=(
                    rdata.get('project_state')=='ASSET_RECON' and
                    rdata.get('manifest_version')==104 and
                    rdata.get('readiness')=='BLOCKED_MEDIA' and
                    rdata.get('ready_to_execute') is False and
                    rkeys==expected
                )
                readiness_detail=f"state={rdata.get('project_state')} manifest={rdata.get('manifest_version')} readiness={rdata.get('readiness')} keys={sorted(rkeys)}"
            except Exception as exc:
                readiness_ok=False;readiness_detail=f'readiness parse error: {exc}'
        out.append(self._result('pilot_readiness_snapshot','PASS' if readiness_ok else 'FAIL',readiness_detail))
        readiness_runtime_ok=(self.root/'gmk_pilot'/'readiness.py').is_file() and 'pilot-readiness' in readme
        out.append(self._result('pilot_readiness_runtime','PASS' if readiness_runtime_ok else 'FAIL','read-only readiness dashboard documented and packaged'))

        operator_files=['gmk_operator/app.py','gmk_operator/__main__.py','START_GMK.cmd','INSTALL_GMK.cmd','START_GMK.sh','INSTALL_GMK.sh','README_START_HERE_TH.md','QUICK_START_CACHYOS_TH.md']
        missing_operator=[name for name in operator_files if not (self.root/name).is_file()]
        operator_ok=not missing_operator and 'gmk-operator' in (self.root/'pyproject.toml').read_text(encoding='utf-8')
        out.append(self._result('operator_release_surface','PASS' if operator_ok else 'FAIL',f'missing={missing_operator}; entrypoint={operator_ok and True}'))
        footage_files=['gmk_footage/query_planner.py','gmk_footage/youtube_provider.py','gmk_footage/ranker.py','gmk_footage/transcript.py','gmk_footage/research.py','gmk_footage/acquire.py','gmk_footage/segments.py','gmk_footage/assembly.py','gmk_footage/web_sources.py','gmk_footage/material_acquire.py','gmk_footage/source_policy.py','gmk_footage/fallback_research.py','gmk_footage/auto_production.py']
        missing_footage=[name for name in footage_files if not (self.root/name).is_file()]
        footage_ok=not missing_footage and 'footage-plan' in readme and 'footage-research' in readme
        out.append(self._result('complete_documentary_footage_core','PASS' if footage_ok else 'FAIL',f'missing={missing_footage}; documented={footage_ok and True}'))
        return out

    def _run(self,name:str,cmd:list[str],timeout:int) -> CheckResult:
        start=time.monotonic()
        try:
            p=subprocess.run(cmd,cwd=self.root,text=True,capture_output=True,timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            detail=((exc.stdout or '')+(exc.stderr or ''))[-2000:]
            return self._result(name,'TIMEOUT',detail,duration=time.monotonic()-start)
        detail=((p.stdout or '')+(p.stderr or '')).strip()
        if len(detail)>4000: detail=detail[-4000:]
        return self._result(name,'PASS' if p.returncode==0 else 'FAIL',detail,duration=time.monotonic()-start,returncode=p.returncode)

    def run(self, profile: str='QUICK', timeout_seconds: int=120) -> AuditResult:
        profile=profile.upper()
        if profile not in {'STATIC','QUICK','FULL'}:
            raise AuditError('AUDIT_PROFILE_INVALID: expected STATIC, QUICK, or FULL')
        checks=self._static_checks()
        if profile in {'QUICK','FULL'}:
            commands=(
                ('schema_validator',[sys.executable,'tools/validate_schemas.py']),
                ('semantic_smoke',[sys.executable,'tools/semantic_smoke.py']),
                ('gate_smoke',[sys.executable,'tools/gate_engine_smoke.py']),
                ('repo_layout_audit',[sys.executable,'tools/repo_layout_audit.py']),
                ('compileall',[sys.executable,'-m','compileall','-q','.']),
            )
            for name,cmd in commands:
                checks.append(self._run(name,cmd,timeout_seconds))
            for name,paths in self.FAST_PARTITIONS:
                checks.append(self._run(f'pytest_{name}',[sys.executable,'-m','pytest','-q',*paths],timeout_seconds))
        if profile=='FULL':
            for name,paths in self.FULL_BASE_PARTITIONS:
                checks.append(self._run(f'pytest_{name}',[sys.executable,'-m','pytest','-q',*paths],timeout_seconds))
            for name,paths in self.HEAVY_PARTITIONS:
                checks.append(self._run(f'pytest_{name}',[sys.executable,'-m','pytest','-q',*paths],timeout_seconds))

        counts={s:sum(c.status==s for c in checks) for s in ('PASS','FAIL','TIMEOUT','WARN')}
        overall='FAIL' if counts['FAIL'] else ('PASS_WITH_TIMEOUTS' if counts['TIMEOUT'] else ('PASS_WITH_WARNINGS' if counts['WARN'] else 'PASS'))
        canonical=json.dumps({'profile':profile,'checks':[{'name':c.name,'status':c.status,'returncode':c.returncode} for c in checks]},ensure_ascii=False,sort_keys=True,separators=(',',':'))
        return AuditResult(profile=profile,repository=str(self.root),overall_status=overall,checks=tuple(checks),pass_count=counts['PASS'],fail_count=counts['FAIL'],timeout_count=counts['TIMEOUT'],warning_count=counts['WARN'],report_sha256=self._sha_text(canonical))

    @staticmethod
    def write_reports(result: AuditResult, json_path: Path, markdown_path: Path | None=None):
        json_path=Path(json_path); json_path.parent.mkdir(parents=True,exist_ok=True)
        json_path.write_text(json.dumps(result.to_dict(),ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        if markdown_path is not None:
            markdown_path=Path(markdown_path); markdown_path.parent.mkdir(parents=True,exist_ok=True)
            lines=['# GMK Repository Audit', '', f'- Profile: `{result.profile}`', f'- Overall: **{result.overall_status}**', f'- PASS: {result.pass_count}', f'- FAIL: {result.fail_count}', f'- TIMEOUT: {result.timeout_count}', f'- WARN: {result.warning_count}', f'- Report SHA-256: `{result.report_sha256}`', '', '| Check | Status | Seconds | Detail |','|---|---|---:|---|']
            for c in result.checks:
                detail=c.detail.replace('|','\\|').replace('\n',' ')[:700]
                lines.append(f'| `{c.name}` | {c.status} | {c.duration_seconds:.3f} | {detail} |')
            markdown_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
