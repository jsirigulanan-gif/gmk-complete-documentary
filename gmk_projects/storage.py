from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Any
from uuid import uuid4


class StorageError(RuntimeError):
    pass


ROLES = {'research', 'footage', 'voice', 'music', 'timeline', 'exports'}


def digest(path: Path) -> dict:
    sha, md5 = hashlib.sha256(), hashlib.md5()
    size = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return {'sha256': sha.hexdigest(), 'md5': md5.hexdigest(), 'size': size}


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.write-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def relative_path(value: str) -> str:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')) or '\\' in value or ':' in value:
        raise StorageError('Invalid project path')
    return str(p)


class RcloneDrive:
    """Copy immutable files; never sync/delete unrelated Drive files or share them."""

    def __init__(self, remote: str = 'gdrive:', root: str = 'GMK Documentary Projects', *, executable: str = 'rclone'):
        if not re.fullmatch(r'[A-Za-z0-9_-]+:', remote):
            raise StorageError('Expected a configured rclone remote, e.g. gdrive:')
        self.remote, self.root, self.executable = remote, relative_path(root), executable

    def _run(self, *args: str, timeout: int = 3600) -> str:
        try:
            p = subprocess.run([self.executable, *args, '--contimeout', '15s', '--timeout', '60s',
                                '--retries', '2', '--low-level-retries', '2'],
                               capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StorageError('Drive transfer unavailable or timed out; local files are retained') from exc
        if p.returncode or re.search(r'\bERROR\s*:', p.stderr):
            # Do not persist stderr: backend diagnostics can contain credential-bearing URLs.
            if any(marker in p.stderr.lower() for marker in ('quota exceeded', 'ratelimitexceeded', 'rate_limit_exceeded')):
                raise StorageError('Drive API quota exceeded. Local files are retained; retry later or configure your own Google OAuth client in rclone.')
            raise StorageError(f'Drive command {args[0]} failed (exit {p.returncode}); local files are retained')
        return p.stdout

    def target(self, path: str) -> str:
        return self.remote + self.root + '/' + relative_path(path)

    def put(self, local: Path, path: str, expected: dict) -> dict:
        dest = self.target(path)
        self._run('copyto', str(local.resolve()), dest, '--checksum', '--immutable', '--drive-skip-gdocs')
        stat = json.loads(self._run('lsjson', dest, '--stat', '--hash', '--drive-skip-gdocs', timeout=120))
        hashes = {k.lower(): v.lower() for k, v in (stat.get('Hashes') or {}).items()}
        if stat.get('IsDir') or stat.get('Size') != expected['size'] or hashes.get('md5') != expected['md5'] or not stat.get('ID'):
            raise StorageError('Drive checksum/size verification failed; local files are retained')
        return {'id': stat['ID'], 'path': dest, 'md5': hashes['md5'], 'size': stat['Size']}

    def list_scripts(self) -> list[dict]:
        rows = json.loads(self._run('lsjson', self.remote, '--files-only', '--drive-export-formats', 'docx', timeout=120))
        return [r for r in rows if r.get('Name', '').lower().startswith('[lemino script]') and r.get('ID')]

    def fetch_script(self, file_id: str, dest: Path) -> None:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
            raise StorageError('Invalid Google document ID')
        self._run('backend', 'copyid', self.remote, file_id, str(dest.resolve()), '--drive-export-formats', 'docx')
        if not dest.is_file():
            raise StorageError('Google document export did not produce a file')


class Project:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.manifest = self.root / 'project.json'

    @contextmanager
    def _lock(self):
        # Serialize imports and transfers across GUI/CLI processes.
        with (self.root / '.project.lock').open('a+b') as stream:
            if os.name == 'nt':
                import msvcrt
                if stream.tell() == 0:
                    stream.write(b'0')
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self) -> dict:
        return json.loads(self.manifest.read_text(encoding='utf-8'))

    @classmethod
    def create(cls, base: Path, title: str, *, source_url: str = '', remote: str = 'gdrive:', drive_root: str = 'GMK Documentary Projects') -> Project:
        if not title.strip():
            raise StorageError('Project title is required')
        RcloneDrive(remote, drive_root)  # Validate settings before creating anything.
        key = 'project-' + uuid4().hex[:16]
        p = cls(Path(base) / key)
        p.root.mkdir(parents=True, exist_ok=False)
        for role in sorted(ROLES):
            (p.root / role).mkdir()
        atomic_json(p.manifest, {'version': 1, 'project_id': key, 'title': title.strip(),
                    'source_url': source_url, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'drive': {'remote': remote, 'root': drive_root}, 'assets': [],
                    'storage_status': 'LOCAL_ONLY',
                    'last_snapshot': None})
        from .production import ProductionProject
        ProductionProject(p).initialize()
        return p

    def add_file(self, source: Path, role: str, *, source_url: str = '', scenes: list[str] | None = None) -> dict:
        if role not in ROLES:
            raise StorageError('Unknown asset role')
        source = Path(source).resolve(strict=True)
        if not source.is_file():
            raise StorageError('Asset must be a regular file')
        # Copy first, then hash the frozen copy, so callers can subsequently edit their source.
        with self._lock():
            data = self.read()
            fd, temp_name = tempfile.mkstemp(dir=self.root / role, suffix='.tmp')
            os.close(fd)
            tmp = Path(temp_name)
            try:
                shutil.copyfile(source, tmp)
                meta = digest(tmp)
                suffix = source.suffix.lower()
                if not re.fullmatch(r'\.[a-z0-9]{1,10}', suffix):
                    suffix = '.bin'
                path = f'{role}/{meta["sha256"]}{suffix}'
                match = next((a for a in data['assets'] if a['path'] == path), None)
                if match:
                    match['scene_ids'] = sorted(set(match['scene_ids']) | set(scenes or []))
                    match['source_urls'] = sorted(set(match['source_urls']) | ({source_url} if source_url else set()))
                    data['storage_status'] = 'PENDING_UPLOAD'
                    atomic_json(self.manifest, data)
                    return match
                os.replace(tmp, self.root / path)
                asset = {**meta, 'path': path, 'role': role, 'original_name': source.name,
                         'source_urls': [source_url] if source_url else [], 'scene_ids': sorted(set(scenes or [])),
                         'upload_status': 'PENDING', 'drive_file': None}
                data['assets'].append(asset)
                data['storage_status'] = 'PENDING_UPLOAD'
                atomic_json(self.manifest, data)
                return asset
            finally:
                tmp.unlink(missing_ok=True)

    def sync(self, drive: RcloneDrive | None = None) -> dict:
        checkpoint = None
        edit_checkpoint = self.add_file(self.root/'edit.json', 'timeline') if (self.root/'edit.json').is_file() else None
        if self.read().get('production_runtime'):
            from .production import ProductionProject
            checkpoint = ProductionProject(self).checkpoint()
        with self._lock():
            data = self.read()
            if checkpoint:
                pointer = json.loads((self.root/'production'/'CURRENT_MANIFEST.json').read_text(encoding='utf-8'))
                if pointer['sha256'] != checkpoint['manifest_sha256']:
                    raise StorageError('Production changed while checkpointing; retry sync before claiming current backup')
            if edit_checkpoint:
                if digest(self.root/'edit.json')['sha256'] != edit_checkpoint['sha256']:
                    raise StorageError('Edit changed while checkpointing; retry sync before claiming current backup')
                data['active_edit_asset'] = {'path': edit_checkpoint['path'], 'sha256': edit_checkpoint['sha256']}
            drive = drive or RcloneDrive(**data['drive'])
            data['storage_status'] = 'UPLOADING'
            atomic_json(self.manifest, data)
            try:
                for a in data['assets']:
                    local = self.root / relative_path(a['path'])
                    if not local.resolve().is_relative_to(self.root) or local.is_symlink():
                        raise StorageError('Asset escapes project directory')
                    actual = digest(local)
                    if any(actual[k] != a[k] for k in ('sha256', 'md5', 'size')):
                        raise StorageError('Local asset changed; register the new version before uploading')
                    # Recheck even previously uploaded files: a user may have removed a Drive copy.
                    receipt = drive.put(local, data['project_id'] + '/' + a['path'], actual)
                    a.update(upload_status='VERIFIED', drive_file=receipt)
                    atomic_json(self.manifest, data)
                snapshot = {k: v for k, v in data.items() if k not in ('last_snapshot', 'storage_status', 'last_error')}
                snapshot['storage_status'] = 'ASSETS_VERIFIED'
                snap_path = self.root / '.snapshot.json'
                atomic_json(snap_path, snapshot)
                meta = digest(snap_path)
                receipt = drive.put(snap_path, data['project_id'] + '/manifests/' + meta['sha256'] + '.json', meta)
                data.update(storage_status='VERIFIED', last_snapshot=receipt)
                data.pop('last_error', None)
            except Exception:
                data['storage_status'] = 'UPLOAD_FAILED'
                data['last_error'] = 'Transfer or verification failed. Retry sync; local files are retained.'
                atomic_json(self.manifest, data)
                raise
            atomic_json(self.manifest, data)
            return data


class ProjectAcquirer:
    """Archive every downloaded candidate, including footage later rejected by matching."""

    def __init__(self, project: Project, acquirer=None, drive: RcloneDrive | None = None):
        from gmk_footage.acquire import YouTubeAcquirer
        self.project, self.acquirer, self.drive = project, acquirer or YouTubeAcquirer(), drive

    def acquire(self, candidate, output_dir: Path):
        acquired = self.acquirer.acquire(candidate, output_dir)
        self.project.add_file(acquired.local_path, 'footage', source_url=candidate.webpage_url)
        self.project.add_file(acquired.receipt_path, 'research', source_url=candidate.webpage_url)
        self.project.sync(self.drive)
        return acquired
