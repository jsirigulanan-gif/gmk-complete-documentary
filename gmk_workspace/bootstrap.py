from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib, json, shutil

from gmk_state import StateEngine
from gmk_runtime.persistence import RuntimeStore


class WorkspaceBootstrapError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def _write_once(path: Path, data: dict[str,Any]):
    payload=(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=payload:
            raise WorkspaceBootstrapError(f'WORKSPACE_METADATA_CONFLICT: {path}')
        return
    path.write_bytes(payload)


@dataclass(frozen=True)
class WorkspaceBootstrapResult:
    workspace: Path
    project_ref: dict[str,Any]
    research_pack_ref: dict[str,Any] | None
    manifest: dict[str,Any]
    input_copy: Path | None
    input_sha256: str | None


class WorkspaceBootstrapper:
    """Create a new GMK workspace without bypassing State Engine authority.

    WORKSPACE.json is launcher metadata only. PROJECT_MANIFEST remains the
    authoritative live resume pointer after bootstrap.
    """
    def __init__(self, runtime_root: Path):
        self.runtime_root=Path(runtime_root)

    def init(self, workspace: Path, *, title: str, narration_language: str='th-TH', target_format: str='LONGFORM_DOCUMENTARY', runtime_min: float=20.0, runtime_max: float=40.0, working_title: str|None=None, research_pack: Path|None=None) -> WorkspaceBootstrapResult:
        workspace=Path(workspace)
        if (workspace/'CURRENT_MANIFEST.json').exists():
            raise WorkspaceBootstrapError('WORKSPACE_ALREADY_INITIALIZED')
        if runtime_min>runtime_max:
            raise WorkspaceBootstrapError('PROJECT_RUNTIME_RANGE_INVALID')
        workspace.mkdir(parents=True,exist_ok=True)

        engine=StateEngine(self.runtime_root)
        tx=engine.begin()
        project_payload={
            'title':title,
            'language':{'narration':narration_language},
            'target':{'format':target_format,'runtime_minutes':{'min':float(runtime_min),'max':float(runtime_max)}},
        }
        if working_title:
            project_payload['working_title']=working_title
        project_ref=tx.create_object('PROJECT',project_payload)
        research_ref=None; input_copy=None; input_hash=None
        if research_pack is not None:
            rp=Path(research_pack)
            if not rp.is_file():
                raise WorkspaceBootstrapError(f'RESEARCH_PACK_NOT_FOUND: {rp}')
            input_hash=_sha256_file(rp)
            safe_name=rp.name
            input_copy=workspace/'inputs'/'research'/safe_name
            input_copy.parent.mkdir(parents=True,exist_ok=True)
            if input_copy.exists():
                if _sha256_file(input_copy)!=input_hash:
                    raise WorkspaceBootstrapError(f'RESEARCH_PACK_COPY_CONFLICT: {input_copy}')
            else:
                shutil.copy2(rp,input_copy)
            research_ref=tx.create_artifact('RESEARCH_PACK',{
                'title':rp.stem,
                'research_summary':'Bootstrap research pack registered as an immutable pilot input. Domain ingestion and Research Audit are still pending.',
                'source_refs':[],
                'notes':[
                    f'input_path={input_copy.relative_to(workspace).as_posix()}',
                    f'input_sha256={input_hash}',
                    f'input_bytes={input_copy.stat().st_size}',
                    'bootstrap_registration_only=true',
                ],
            })
        tx.commit()
        manifest=RuntimeStore(self.runtime_root,workspace).persist(engine)
        meta={
            'workspace_format':'GMK_WORKSPACE_V1',
            'schema_version':'1.0.0',
            'project_ref':project_ref,
            'manifest_id':manifest['manifest_id'],
            'authoritative_resume_pointer':'CURRENT_MANIFEST.json',
            'notes':['WORKSPACE.json is non-authoritative launcher metadata; PROJECT_MANIFEST is authoritative.'],
        }
        if research_ref:
            meta['bootstrap_research_pack_ref']=research_ref
            meta['bootstrap_input_sha256']=input_hash
        _write_once(workspace/'WORKSPACE.json',meta)
        return WorkspaceBootstrapResult(workspace,project_ref,research_ref,manifest,input_copy,input_hash)
