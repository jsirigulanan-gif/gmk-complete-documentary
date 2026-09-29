from __future__ import annotations
from pathlib import Path
from typing import Any
import json, os, tempfile

from gmk_semantics.model import sha256_json
from gmk_state.errors import StateEngineError
from .manifest import ProjectManifestBuilder


class PersistenceError(RuntimeError):
    pass


def _json_bytes(data: Any) -> bytes:
    return (json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2,separators=(',', ': '))+'\n').encode('utf-8')


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


class RuntimeStore:
    """Filesystem persistence for GMK v1 runtime snapshots.

    Authoritative object decisions and Artifact versions are immutable. LIVE derived
    object-record revisions are stored content-addressed so historical Registry snapshots
    remain reconstructable. Project Manifest pins exact Registry snapshot hashes.
    """
    def __init__(self, schema_root: Path, workspace: Path, *, environment_mode='PRODUCTION'):
        self.schema_root=Path(schema_root);self.workspace=Path(workspace)
        self.builder=ProjectManifestBuilder(self.schema_root,environment_mode=environment_mode)

    def _write_immutable_json(self,path:Path,data:dict[str,Any]):
        content=_json_bytes(data)
        if path.exists():
            if path.read_bytes()!=content:raise PersistenceError(f'IMMUTABLE_RECORD_CONFLICT: {path}')
            return
        _atomic_write(path,content)

    def _write_object_record(self, engine, path:Path, obj:dict[str,Any]):
        """Persist one exact object version without mutating its authoritative decision history.

        Core-object decision content is immutable, while LIVE derived/operational fields
        (for example stale/approval summaries) may be recomputed without a new object
        decision version.  If the live record changes but the decision hash is identical,
        preserve the original version file and store the new record content-addressed by
        its record hash.  Registry snapshots select the exact record hash.
        """
        content=_json_bytes(obj)
        if not path.exists():
            _atomic_write(path,content);return
        if path.read_bytes()==content:return
        try: existing=json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc: raise PersistenceError(f'OBJECT_RECORD_BASE_INVALID: {path}: {exc}') from exc
        if engine.semantic.decision_hash(existing)!=engine.semantic.decision_hash(obj):
            raise PersistenceError(f'IMMUTABLE_DECISION_CONFLICT: {path}')
        record_sha=sha256_json(obj)
        alt=path.parent/'records'/path.stem/f'{record_sha}.json'
        self._write_immutable_json(alt,obj)

    def persist(self, engine) -> dict[str,Any]:
        state=engine.snapshot()
        manifest=self.builder.build(state,engine.gates)
        issues=engine.structural.validate_manifest(manifest)
        if issues:raise PersistenceError('MANIFEST_STRUCTURAL_INVALID: '+'; '.join(x.message for x in issues))

        for (oid,v),obj in sorted(state.objects.items()):
            self._write_object_record(engine,self.workspace/'objects'/oid/f'v{v}.json',obj)
        for (aid,v),artifact in sorted(state.artifacts.items()):
            self._write_immutable_json(self.workspace/'artifacts'/'records'/aid/f'v{v}.json',artifact)
        for (cid,ver),cfg in sorted(state.configs.items()):
            self._write_immutable_json(self.workspace/'configs'/cid/f'{ver}.json',cfg)

        for rid,reg in sorted(state.registries.items()):
            self._write_immutable_json(self.workspace/'registries'/rid/f'v{reg.version}.json',reg.to_dict())
        ar=state.artifact_registry
        self._write_immutable_json(self.workspace/'registries'/ar.registry_id/f'v{ar.version}.json',ar.to_dict())

        _atomic_write(self.workspace/'state'/'audit-log.json',_json_bytes([x.to_dict() for x in state.audit_log]))
        _atomic_write(self.workspace/'state'/'gate-history.json',_json_bytes(list(state.gate_evaluations)))

        mpath=self.workspace/'manifests'/manifest['manifest_id']/f"v{manifest['manifest_version']}.json"
        self._write_immutable_json(mpath,manifest)
        pointer={
            'manifest_id':manifest['manifest_id'],'manifest_version':manifest['manifest_version'],
            'path':str(mpath.relative_to(self.workspace)).replace('\\','/'),
            'sha256':sha256_json(manifest),
        }
        _atomic_write(self.workspace/'CURRENT_MANIFEST.json',_json_bytes(pointer))
        return manifest
