import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('git_kind', ['checkout', 'worktree', 'archive'])
def test_layout_audit_accepts_checkout_worktree_and_archive(tmp_path, git_kind):
    root = tmp_path / 'source'
    root.mkdir()
    for entry in ROOT.iterdir():
        if entry.name in {'.git', '__pycache__', '.pytest_cache'}:
            continue
        if entry.name == 'tools':
            (root / 'tools').mkdir()
            shutil.copy2(entry / 'repo_layout_audit.py', root / 'tools')
        else:
            (root / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    if git_kind == 'checkout':
        (root / '.git').mkdir()
    elif git_kind == 'worktree':
        (root / '.git').write_text('gitdir: /unused/worktree\n')
    result = subprocess.run([sys.executable, str(root / 'tools/repo_layout_audit.py')],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['ok'] is True

    (root / 'CURRENT_MANIFEST.json').write_text('{}')
    failed = subprocess.run([sys.executable, str(root / 'tools/repo_layout_audit.py')],
                            capture_output=True, text=True)
    assert failed.returncode == 1
    checks = {row['check']: row['ok'] for row in json.loads(failed.stdout)['checks']}
    assert checks['no_current_manifest_in_source_root'] is False
