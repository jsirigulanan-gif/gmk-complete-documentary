from __future__ import annotations
from pathlib import Path
import hashlib
import json
import os

from gmk_operator.app import ROOT, WORKSPACE, INTAKE, system_check, headless_status
from gmk_runtime.media_tools import resolve_ffprobe


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_operator_headless_status_is_non_mutating():
    pointer=WORKSPACE/'CURRENT_MANIFEST.json'
    before=_sha(pointer)
    status=headless_status()
    after=_sha(pointer)
    assert status['project_state']=='ASSET_RECON'
    assert status['manifest_version']==104
    assert status['readiness']=='BLOCKED_MEDIA'
    assert status['workspace_mutated'] is False
    assert before==after


def test_operator_system_check_has_core_paths():
    check=system_check()
    by={x['check']:x for x in check['checks']}
    assert int(check['build']) >= 40
    assert by['python_3_10_plus']['ok']
    assert by['workspace_present']['ok']
    assert by['intake_present']['ok']
    assert by['worksheet_present']['ok']
    assert by['ffprobe']['ok']


def test_media_tool_env_override(monkeypatch, tmp_path):
    fake=tmp_path/('ffprobe.exe' if os.name=='nt' else 'ffprobe')
    fake.write_text('fake',encoding='utf-8')
    monkeypatch.setenv('GMK_FFPROBE',str(fake))
    assert Path(resolve_ffprobe())==fake.resolve()


def test_operator_distribution_files_present():
    required=['START_GMK.cmd','INSTALL_GMK.cmd','README_START_HERE_TH.md','gmk_operator/app.py']
    assert all((ROOT/name).is_file() for name in required)
    pyproject=(ROOT/'pyproject.toml').read_text(encoding='utf-8')
    assert 'gmk-operator = "gmk_operator.app:main"' in pyproject
