"""Bind the Drive catalog to the existing production engine; never create a second state machine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_workspace import WorkspaceBootstrapper

from .storage import Project, StorageError, atomic_json, digest, relative_path


RUNTIME_ROOT = Path(__file__).resolve().parents[1]


class ProductionProject:
    def __init__(self, project: Project):
        self.project = project
        self.workspace = project.root / 'production'

    def _check_workspace(self):
        if self.workspace.is_symlink() or not self.workspace.resolve().is_relative_to(self.project.root):
            raise StorageError('Production workspace must be inside its project')

    def _load(self):
        self._check_workspace()
        identity = json.loads((self.workspace/'PROJECT_BINDING.json').read_text(encoding='utf-8'))
        if identity.get('drive_project_id') != self.project.read()['project_id']:
            raise StorageError('Production workspace belongs to a different Drive project')
        result = ColdStartLoader(RUNTIME_ROOT, self.workspace).load()
        binding = self.project.read().get('production_runtime')
        if binding and binding['project_ref']['id'] != result.manifest['project_ref']['id']:
            raise StorageError('Production workspace belongs to a different project')
        return result

    def initialize(self) -> dict:
        """Repeatable explicit migration for old projects; automatic on new project creation."""
        self._check_workspace()
        with self.project._lock():
            data = self.project.read()
            pointer = self.workspace / 'CURRENT_MANIFEST.json'
            if not pointer.exists():
                if data.get('production_runtime'):
                    raise StorageError('Production records are missing; restore them instead of reinitializing')
                if self.workspace.exists():
                    raise StorageError('Unrecognized production directory; refusing to overwrite it')
                with tempfile.TemporaryDirectory(dir=self.project.root, prefix='.bootstrap-') as folder:
                    staging = Path(folder) / 'workspace'
                    WorkspaceBootstrapper(RUNTIME_ROOT).init(staging, title=data['title'])
                    atomic_json(staging/'PROJECT_BINDING.json', {'drive_project_id': data['project_id']})
                    os.replace(staging, self.workspace)
            loaded = self._load()
            data['production_runtime'] = {
                'workspace': 'production', 'project_ref': loaded.manifest['project_ref'],
                'state_authority': 'production/CURRENT_MANIFEST.json',
            }
            # Remove the Build 046 hardcoded status cache. Core state is always read from its manifest.
            data.pop('production_status', None)
            data['storage_status'] = 'PENDING_UPLOAD'
            atomic_json(self.project.manifest, data)
        return self.status()

    def connect_existing(self) -> dict:
        self.initialize()
        data = self.project.read()
        source = next((a for a in data['assets'] if a['role'] == 'research'
                       and a['original_name'] != 'script.json'), None)
        if source is not None:
            self.register_research(source['path'])
        return self.status()

    def register_research(self, asset_path: str) -> dict:
        """Register exact source bytes, without asserting research/audit/script completion."""
        with self.project._lock():
            data = self.project.read()
            asset = next((a for a in data['assets'] if a['path'] == asset_path and a['role'] == 'research'), None)
            if asset is None:
                raise StorageError('Research must be registered in this project before production intake')
            source = self.project.root / relative_path(asset_path)
            if source.is_symlink() or not source.resolve().is_relative_to(self.project.root) or digest(source)['sha256'] != asset['sha256']:
                raise StorageError('Research source does not match its registered bytes')
            loaded = self._load()
            engine = loaded.engine
            marker = 'input_sha256=' + asset['sha256']
            existing = next((a for a in engine.snapshot().artifacts.values()
                             if a.get('artifact_type') == 'RESEARCH_PACK' and marker in a.get('notes', [])), None)
            if existing is None:
                reopen = engine.project_state in ('RESEARCH_AUDITED', 'ROUGH_NARRATIVE_READY', 'VISUAL_REQUIREMENTS_READY')
                if engine.project_state not in ('BOOTSTRAPPED', 'RESEARCH_INTAKE') and not reopen:
                    raise StorageError('Research revision after audit requires the core revision/invalidation workflow')
                target = self.workspace/'inputs'/'research'/source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and digest(target)['sha256'] != asset['sha256']:
                    raise StorageError('Immutable research copy mismatch')
                shutil.copyfile(source, target)
                tx = engine.begin()
                if reopen:
                    tx.reenter_stage('RESEARCH_INTAKE', actor_type='HUMAN')
                tx.create_artifact('RESEARCH_PACK', {
                    'title': asset['original_name'],
                    'research_summary': 'User-supplied research/script source registered by exact bytes. Evidence, claims and editorial audit remain pending.',
                    'source_refs': [],
                    'notes': [marker, 'input_path=' + target.relative_to(self.workspace).as_posix(),
                              'input_bytes=' + str(asset['size']), 'registration_only=true'],
                })
                if engine.project_state == 'BOOTSTRAPPED':
                    tx.transition_project_state('RESEARCH_INTAKE', actor_type='AI')
                tx.commit()
                RuntimeStore(RUNTIME_ROOT, self.workspace).persist(engine)
                data['storage_status'] = 'PENDING_UPLOAD'
                atomic_json(self.project.manifest, data)
        return self.status()

    def checkpoint(self) -> dict:
        """Freeze the persistent core records into a registered Drive asset before sync."""
        with tempfile.TemporaryDirectory(dir=self.project.root, prefix='.checkpoint-') as folder:
            archive = Path(folder) / 'production-checkpoint.zip'
            with self.project._lock():
                loaded = self._load()  # Refuse to back up corrupt/unloadable state as a valid checkpoint.
                for artifact in loaded.engine.snapshot().artifacts.values():
                    if artifact.get('artifact_type') != 'RESEARCH_PACK':
                        continue
                    notes = dict(n.split('=', 1) for n in artifact.get('notes', []) if '=' in n)
                    if 'input_path' in notes and 'input_sha256' in notes:
                        source = self.workspace / relative_path(notes['input_path'])
                        if not source.resolve().is_relative_to(self.workspace) or source.is_symlink():
                            raise StorageError('Research input escapes production workspace')
                        if digest(source)['sha256'] != notes['input_sha256']:
                            raise StorageError('Production research input checksum mismatch')
                with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as z:
                    for path in sorted(self.workspace.rglob('*')):
                        if path.is_symlink():
                            raise StorageError('Production checkpoint cannot include symlinks')
                        if not path.is_file() or path.name.endswith('.tmp'):
                            continue
                        # Fixed ZIP metadata makes unchanged checkpoints byte-identical across retries.
                        info = ZipInfo(path.relative_to(self.workspace).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                        info.compress_type = ZIP_DEFLATED
                        with path.open('rb') as source, z.open(info, 'w') as destination:
                            shutil.copyfileobj(source, destination, length=1024 * 1024)
            asset = self.project.add_file(archive, 'timeline')
        return {'asset_path': asset['path'], 'manifest_sha256': loaded.manifest_sha256}

    def status(self) -> dict:
        """Read-only; does not advance gates, run providers, or migrate existing projects."""
        self._check_workspace()
        if not (self.workspace/'CURRENT_MANIFEST.json').exists():
            if self.project.read().get('production_runtime'):
                raise StorageError('Production records are missing; restore the project checkpoint')
            return {'connected': False, 'production_state': 'NOT_CONNECTED',
                    'next_action': {'action': 'CONNECT_EXISTING_PROJECT'}, 'documentary_completed': False}
        loaded = self._load()
        engine = loaded.engine
        from .production_bridge import binding_status
        claims = {}
        for obj in engine.snapshot().objects.values():
            if obj.get('object_type') == 'CLAIM':
                previous = claims.get(obj['id'])
                if previous is None or obj['version'] > previous['version']:
                    claims[obj['id']] = obj
        return {'connected': True, 'production_state': engine.project_state,
                'story_binding': binding_status(self.project, engine.snapshot()),
                'project_ref': loaded.manifest['project_ref'], 'manifest_version': engine.manifest_version,
                'manifest_sha256': loaded.manifest_sha256,
                'research_pack_count': sum(a.get('artifact_type') == 'RESEARCH_PACK' for a in engine.snapshot().artifacts.values()),
                'claim_count': len(claims),
                'unreviewed_claim_count': sum(c['verification_state'] == 'UNREVIEWED' for c in claims.values()),
                'next_action': engine.next_legal_action(actor_type='AI').to_dict(),
                # The Drive release/export receipt adapter is still missing. A legacy core release
                # or a successful upload alone must not claim that the user's full product is done.
                'documentary_completed': False,
                'delivery_verification': 'DRIVE_RELEASE_ADAPTER_NOT_IMPLEMENTED'}
