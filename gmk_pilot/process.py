from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from gmk_runtime.cold_start import ColdStartLoader
from .intake import PilotMediaIntakeRuntime, PilotMediaIntakeError
from .execution import PilotExecutionRuntime, PilotExecutionError


class PilotMediaProcessError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path,payload: Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')


@dataclass(frozen=True)
class PilotMediaProcessResult:
    workspace: Path
    intake_dir: Path
    execute_requested: bool
    starting_state: str
    project_state: str
    manifest_version_before: int
    manifest_version_after: int
    manifest_pointer_sha256_before: str
    manifest_pointer_sha256_after: str
    intake_build: dict[str,Any]
    preflight: dict[str,Any]
    execution: dict[str,Any] | None
    mutated: bool
    ready: bool
    report_path: Path

    def to_dict(self)->dict[str,Any]:
        return {
            'workspace':str(self.workspace),
            'intake_dir':str(self.intake_dir),
            'execute_requested':self.execute_requested,
            'starting_state':self.starting_state,
            'project_state':self.project_state,
            'manifest_version_before':self.manifest_version_before,
            'manifest_version_after':self.manifest_version_after,
            'manifest_pointer_sha256_before':self.manifest_pointer_sha256_before,
            'manifest_pointer_sha256_after':self.manifest_pointer_sha256_after,
            'intake_build':deepcopy(self.intake_build),
            'preflight':deepcopy(self.preflight),
            'execution':deepcopy(self.execution),
            'mutated':self.mutated,
            'ready':self.ready,
            'report_path':str(self.report_path),
        }


class PilotMediaProcessRuntime:
    """One-command operator wrapper for the Build 037 intake/execution path.

    Default operation is deliberately non-mutating: build a checksum/technical
    receipt from the two source-locked intake slots, compile the exact handoff
    plan and run the authoritative media preflight. State mutation only occurs
    when execute=True is explicit. The wrapper does not download media, infer
    visual identity, fill human inspection fields, or cross a Human Approval
    boundary.
    """

    def __init__(self,schema_root: Path,workspace: Path):
        self.root=Path(schema_root)
        self.workspace=Path(workspace)

    def _snapshot(self)->tuple[str,int,str]:
        state=ColdStartLoader(self.root,self.workspace).load().engine
        pointer=self.workspace/'CURRENT_MANIFEST.json'
        pointer_sha=_sha256_file(pointer) if pointer.is_file() else ''
        return state.project_state,state.manifest_version,pointer_sha

    def run(self,intake_dir: Path,inspection: dict[str,Any],*,execute: bool=False,output_dir: Path|None=None)->PilotMediaProcessResult:
        intake_dir=Path(intake_dir)
        out=Path(output_dir) if output_dir is not None else intake_dir
        starting_state,before_version,before_sha=self._snapshot()
        if starting_state not in {'ASSET_RECON','ASSET_CATALOG_READY','VISUAL_COVERAGE_READY'}:
            raise PilotMediaProcessError(f'PILOT_MEDIA_PROCESS_STATE_INVALID: {starting_state}')

        # If acquisition already completed, do not rescan now-non-pending slots.
        if starting_state=='ASSET_CATALOG_READY':
            execution_dict=None
            final_state=starting_state
            after_version=before_version
            after_sha=before_sha
            if execute:
                execution_obj=PilotExecutionRuntime(self.root,self.workspace).execute({'batch_id':'PT_MEDIA_PROCESS_POST_ACQUISITION','items':[]})
                execution_dict=execution_obj.to_dict()
                final_state=execution_obj.project_state
                after_version=execution_obj.manifest_version
                pointer=self.workspace/'CURRENT_MANIFEST.json'
                after_sha=_sha256_file(pointer) if pointer.is_file() else ''
            report_path=out/'PT_MEDIA_PROCESS_REPORT.json'
            preflight={'ready':True,'already_acquired':True,'next_state':'VISUAL_COVERAGE_READY'}
            payload={
                'build':'038','workspace':str(self.workspace),'intake_dir':str(intake_dir),
                'execute_requested':execute,'starting_state':starting_state,'project_state':final_state,
                'manifest_version_before':before_version,'manifest_version_after':after_version,
                'manifest_pointer_sha256_before':before_sha,'manifest_pointer_sha256_after':after_sha,
                'intake_build':{},'preflight':preflight,'execution':execution_dict,
                'mutated':before_version!=after_version or before_sha!=after_sha,'ready':True,
                'statement':'Media already acquired; intake rescan skipped. Visual Coverage executed only when explicitly requested.',
            }
            _write_json(report_path,payload)
            return PilotMediaProcessResult(self.workspace,intake_dir,execute,starting_state,final_state,before_version,after_version,before_sha,after_sha,{},preflight,execution_dict,payload['mutated'],True,report_path)

        # A completed/replayed pilot should not need to rescan now-non-pending slots.
        if starting_state=='VISUAL_COVERAGE_READY':
            report_path=out/'PT_MEDIA_PROCESS_REPORT.json'
            payload={
                'build':'038','workspace':str(self.workspace),'intake_dir':str(intake_dir),
                'execute_requested':execute,'starting_state':starting_state,'project_state':starting_state,
                'manifest_version_before':before_version,'manifest_version_after':before_version,
                'manifest_pointer_sha256_before':before_sha,'manifest_pointer_sha256_after':before_sha,
                'intake_build':{},'preflight':{'ready':True,'replay':True},'execution':None,
                'mutated':False,'ready':True,'statement':'Already at VISUAL_COVERAGE_READY; no intake rescan or state mutation performed.',
            }
            _write_json(report_path,payload)
            return PilotMediaProcessResult(self.workspace,intake_dir,execute,starting_state,starting_state,before_version,before_version,before_sha,before_sha,{},payload['preflight'],None,False,True,report_path)

        try:
            intake_res=PilotMediaIntakeRuntime(self.root,self.workspace).build(intake_dir,inspection,out)
        except PilotMediaIntakeError as exc:
            raise PilotMediaProcessError(f'PILOT_MEDIA_PROCESS_INTAKE_FAILED: {exc}') from exc
        intake_dict=intake_res.to_dict()
        plan=json.loads(intake_res.handoff_plan_path.read_text(encoding='utf-8'))
        preflight=PilotExecutionRuntime(self.root,self.workspace).preflight(plan)
        preflight_dict=preflight.to_dict()
        if not preflight.ready:
            raise PilotMediaProcessError(f'PILOT_MEDIA_PROCESS_PREFLIGHT_FAILED: {list(preflight.blockers)}')

        execution_dict=None
        if execute:
            try:
                execution_obj=PilotExecutionRuntime(self.root,self.workspace).execute(plan)
                execution_dict=execution_obj.to_dict()
            except PilotExecutionError as exc:
                raise PilotMediaProcessError(f'PILOT_MEDIA_PROCESS_EXECUTION_FAILED: {exc}') from exc
            final_state=execution_obj.project_state
            after_version=execution_obj.manifest_version
            pointer=self.workspace/'CURRENT_MANIFEST.json'
            after_sha=_sha256_file(pointer) if pointer.is_file() else ''
        else:
            final_state=starting_state
            after_version=before_version
            after_sha=before_sha
        mutated=(before_version!=after_version or before_sha!=after_sha)
        if not execute and mutated:
            raise PilotMediaProcessError('PILOT_MEDIA_PROCESS_NON_MUTATING_GUARD_FAILED')
        if execute and final_state!='VISUAL_COVERAGE_READY':
            raise PilotMediaProcessError(f'PILOT_MEDIA_PROCESS_EXECUTION_TARGET_NOT_REACHED: {final_state}')

        report_path=out/'PT_MEDIA_PROCESS_REPORT.json'
        payload={
            'build':'038','workspace':str(self.workspace),'intake_dir':str(intake_dir),
            'execute_requested':execute,'starting_state':starting_state,'project_state':final_state,
            'manifest_version_before':before_version,'manifest_version_after':after_version,
            'manifest_pointer_sha256_before':before_sha,'manifest_pointer_sha256_after':after_sha,
            'intake_build':intake_dict,'preflight':preflight_dict,'execution':execution_dict,
            'mutated':mutated,'ready':preflight.ready,
            'statement':(
                'Validated intake was executed through VISUAL_COVERAGE_READY.' if execute
                else 'Validated intake is ready. Workspace was not mutated; rerun explicitly with execute enabled to acquire media.'
            ),
        }
        _write_json(report_path,payload)
        return PilotMediaProcessResult(
            self.workspace,intake_dir,execute,starting_state,final_state,before_version,after_version,before_sha,after_sha,
            intake_dict,preflight_dict,execution_dict,mutated,preflight.ready,report_path,
        )
