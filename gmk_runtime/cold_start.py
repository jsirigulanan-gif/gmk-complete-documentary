from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import hashlib, json, yaml

from gmk_semantics.model import sha256_json
from gmk_state import StateEngine
from gmk_state.models import RegistrySnapshot, TransactionAudit
from gmk_state.artifact_registry import ArtifactRegistrySnapshot, ARTIFACT_REGISTRY_ID, artifact_payload_sha256
from gmk_state.constants import STANDARD_REGISTRY_IDS
from gmk_state.schema_validation import StructuralValidator
from .manifest import ProjectManifestBuilder


class ColdStartError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Any=None):
        super().__init__(f'{code}: {message}');self.code=code;self.details=details


@dataclass(frozen=True)
class ColdStartResult:
    engine: StateEngine
    manifest: dict[str,Any]
    manifest_sha256: str
    loaded_objects: int
    loaded_artifacts: int
    dependency_summary: dict[str,Any]
    next_legal_action: dict[str,Any]


class ColdStartLoader:
    """Fail-closed reconstruction from the Project Manifest and pinned registries."""
    def __init__(self, schema_root: Path, workspace: Path):
        self.schema_root=Path(schema_root);self.workspace=Path(workspace);self.structural=StructuralValidator(self.schema_root)

    @staticmethod
    def _read_json(path:Path):
        try:return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError as exc:raise ColdStartError('RUNTIME_FILE_MISSING',f'Missing {path}.') from exc

    def _load_manifest(self):
        pointer=self._read_json(self.workspace/'CURRENT_MANIFEST.json')
        path=self.workspace/pointer['path'];manifest=self._read_json(path)
        actual=sha256_json(manifest)
        if actual!=pointer.get('sha256'):raise ColdStartError('MANIFEST_HASH_MISMATCH','Current Manifest hash does not match pointer.',details={'expected':pointer.get('sha256'),'actual':actual})
        if int(manifest.get('manifest_version',0))!=int(pointer.get('manifest_version',-1)):raise ColdStartError('MANIFEST_VERSION_POINTER_MISMATCH','Manifest version does not match current pointer.')
        issues=self.structural.validate_manifest(manifest)
        if issues:raise ColdStartError('MANIFEST_STRUCTURAL_INVALID','Persisted Project Manifest failed JSON Schema validation.',details=[x.to_dict() if hasattr(x,'to_dict') else str(x) for x in issues])
        return manifest,actual

    def _verify_system_pins(self,manifest):
        if manifest['system']['schema_version']!='1.0.0':raise ColdStartError('SCHEMA_VERSION_INCOMPATIBLE',f"Expected Schema 1.0.0, found {manifest['system']['schema_version']}.")
        path=self.schema_root/'config'/'gmk_policy_bundle.yaml';raw=yaml.safe_load(path.read_text(encoding='utf-8')) or {};ref=manifest['system']['policy_bundle_ref']
        actual_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        if str(raw.get('config_id'))!=ref['config_id'] or str(raw.get('version'))!=ref['version'] or actual_hash!=ref['sha256']:
            raise ColdStartError('POLICY_BUNDLE_MISMATCH','Pinned GMK Policy Bundle does not match the installed runtime.',details={'manifest':ref,'installed':{'config_id':raw.get('config_id'),'version':str(raw.get('version')),'sha256':actual_hash}})

    def _load_registries(self,manifest):
        pointers=manifest['registries'];required=set(STANDARD_REGISTRY_IDS)|{ARTIFACT_REGISTRY_ID};missing=sorted(required-set(pointers))
        if missing:raise ColdStartError('REGISTRY_MISSING','Manifest is missing standard registry pointer(s).',details=missing)
        core={};artifact=None
        for rid in sorted(required):
            ptr=pointers[rid];path=self.workspace/'registries'/rid/f"v{ptr['version']}.json";data=self._read_json(path)
            if data.get('registry_id')!=rid or int(data.get('version',0))!=int(ptr['version']):raise ColdStartError('REGISTRY_ID_VERSION_MISMATCH',f'{rid} persisted snapshot identity/version mismatch.')
            body={k:v for k,v in data.items() if k!='sha256'};actual=sha256_json(body)
            if actual!=ptr['sha256'] or data.get('sha256')!=actual:raise ColdStartError('REGISTRY_HASH_MISMATCH',f'{rid}@{ptr["version"]} checksum mismatch.')
            if rid==ARTIFACT_REGISTRY_ID:artifact=ArtifactRegistrySnapshot.from_dict(data)
            else:core[rid]=RegistrySnapshot.from_dict(data)
        return core,artifact

    def _load_objects(self,registries):
        objects=[]
        for rid,reg in registries.items():
            for oid,entry in reg.entries.items():
                for v,loc in entry.versions.items():
                    legacy=self.workspace/'objects'/oid/f'v{v}.json'
                    obj=self._read_json(legacy)
                    if sha256_json(obj)!=loc.record_sha256:
                        exact=self.workspace/'objects'/oid/'records'/f'v{v}'/f'{loc.record_sha256}.json'
                        if not exact.exists():
                            raise ColdStartError('OBJECT_RECORD_HASH_MISMATCH',f'{oid}@{v} record checksum mismatch and no content-addressed live record exists.',details={'legacy':str(legacy),'expected_record_sha256':loc.record_sha256})
                        obj=self._read_json(exact)
                    if obj.get('id')!=oid or int(obj.get('version',0))!=v or obj.get('object_type')!=entry.object_type:raise ColdStartError('OBJECT_IDENTITY_MISMATCH',f'{oid}@{v} record does not match Registry.')
                    if sha256_json(obj)!=loc.record_sha256:raise ColdStartError('OBJECT_RECORD_HASH_MISMATCH',f'{oid}@{v} exact record checksum mismatch.')
                    objects.append(obj)
        return objects

    def _load_artifacts(self,registry):
        artifacts=[]
        for aid,entry in registry.entries.items():
            for v,loc in entry.versions.items():
                a=self._read_json(self.workspace/'artifacts'/'records'/aid/f'v{v}.json')
                if a.get('artifact_id')!=aid or int(a.get('version',0))!=v or a.get('artifact_type')!=entry.artifact_type:raise ColdStartError('ARTIFACT_IDENTITY_MISMATCH',f'{aid}@{v} record does not match Artifact Registry.')
                if sha256_json(a)!=loc.record_sha256:raise ColdStartError('ARTIFACT_RECORD_HASH_MISMATCH',f'{aid}@{v} record checksum mismatch.')
                if a.get('sha256')!=loc.artifact_sha256:raise ColdStartError('ARTIFACT_CONTENT_HASH_MISMATCH',f'{aid}@{v} artifact checksum does not match Artifact Registry.')
                if a.get('schema_header') and artifact_payload_sha256(a)!=a.get('sha256'):raise ColdStartError('ARTIFACT_CONTENT_HASH_MISMATCH',f'{aid}@{v} managed artifact payload checksum mismatch.')
                artifacts.append(a)
        return artifacts

    def _load_sidecars(self):
        ap=self.workspace/'state'/'audit-log.json';gp=self.workspace/'state'/'gate-history.json'
        audits=self._read_json(ap) if ap.exists() else []
        gates=self._read_json(gp) if gp.exists() else []
        configs=[]
        croot=self.workspace/'configs'
        if croot.exists():
            for p in sorted(croot.glob('*/*.json')):configs.append(self._read_json(p))
        return audits,gates,configs

    @staticmethod
    def _assert_current_refs(manifest, objects, artifacts):
        om={(o['id'],int(o['version'])):o for o in objects};am={(a['artifact_id'],int(a['version'])):a for a in artifacts}
        p=manifest['project_ref']
        if (p['id'],int(p['version'])) not in om:raise ColdStartError('PROJECT_REF_UNRESOLVED','Manifest project_ref does not resolve.')
        for name,ref in (manifest.get('current') or {}).items():
            if 'artifact_id' in ref:
                a=am.get((ref['artifact_id'],int(ref['version'])))
                if not a:raise ColdStartError('CURRENT_ARTIFACT_REF_UNRESOLVED',f'Manifest current.{name} does not resolve.')
                if a.get('sha256')!=ref.get('sha256'):raise ColdStartError('CURRENT_ARTIFACT_HASH_MISMATCH',f'Manifest current.{name} hash mismatch.')
            else:
                if (ref['id'],int(ref['version'])) not in om:raise ColdStartError('CURRENT_OBJECT_REF_UNRESOLVED',f'Manifest current.{name} does not resolve.')
        cr=(manifest.get('current') or {}).get('current_release')
        if cr and om[(cr['id'],int(cr['version']))].get('state')!='RELEASED':raise ColdStartError('CURRENT_RELEASE_NOT_RELEASED','Manifest current_release must resolve to a RELEASED Release.')

    def load(self, *, clock: Callable[[],Any]|None=None) -> ColdStartResult:
        manifest,mhash=self._load_manifest();self._verify_system_pins(manifest)
        registries,artifact_registry=self._load_registries(manifest)
        objects=self._load_objects(registries);artifacts=self._load_artifacts(artifact_registry)
        self._assert_current_refs(manifest,objects,artifacts)
        audits,gates,configs=self._load_sidecars()
        engine=StateEngine(
            self.schema_root,objects=objects,artifacts=artifacts,configs=configs,registries=registries,artifact_registry=artifact_registry,
            manifest_version=int(manifest['manifest_version']),project_state=manifest['project_state']['current'],project_state_entered_at=manifest['project_state']['entered_at'],
            audit_log=audits,gate_evaluations=gates,clock=clock,
        )
        # Fail closed on dependency-integrity corruption. Incident-derived safety
        # modes are legitimate reconstructed project state and must survive restart.
        if engine.dependency_integrity_issues():
            raise ColdStartError('COLD_START_DEPENDENCY_INTEGRITY_FAILED','Cold Start reconstructed state in READ_ONLY due to dependency projection integrity failure.',details=engine.dependency_integrity_issues())
        # Exact registry versions/hashes must remain unchanged after reconstruction.
        snap=engine.snapshot()
        for rid,ptr in manifest['registries'].items():
            if rid==ARTIFACT_REGISTRY_ID:reg=snap.artifact_registry
            else:reg=snap.registries[rid]
            if int(reg.version)!=int(ptr['version']) or reg.sha256!=ptr['sha256']:
                raise ColdStartError('COLD_START_REGISTRY_DRIFT',f'{rid} changed during reconstruction.',details={'manifest':ptr,'reconstructed':reg.to_dict()})
        nla=engine.next_legal_action(actor_type='SYSTEM').to_dict()
        return ColdStartResult(engine,manifest,mhash,len(objects),len(artifacts),engine.cold_start_dependency_summary(),nla)
