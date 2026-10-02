from pathlib import Path
import os
import subprocess

from gmk_operator.app import system_check

ROOT = Path(__file__).resolve().parents[2]


def test_cachyos_scripts_present_and_executable():
    for name in ('INSTALL_GMK.sh','START_GMK.sh'):
        p=ROOT/name
        assert p.is_file()
        assert os.access(p, os.X_OK)
        subprocess.run(['bash','-n',str(p)],check=True)


def test_cachyos_installer_uses_native_packages_not_editable_pip():
    text=(ROOT/'INSTALL_GMK.sh').read_text(encoding='utf-8')
    for token in ('pacman','python-jsonschema','python-yaml','ffmpeg','tk'):
        assert token in text
    assert 'pip install -e' not in text
    assert 'pip install --editable' not in text


def test_linux_start_runs_source_directly():
    text=(ROOT/'START_GMK.sh').read_text(encoding='utf-8')
    assert '-m gmk_operator' in text
    assert 'pip install -e' not in text


def test_operator_reports_build_041_or_newer():
    check=system_check()
    assert int(check['build']) >= 41
    by={x['check']:x for x in check['checks']}
    assert by['python_3_10_plus']['ok']
    assert by['ffmpeg']['ok']
    assert by['tkinter']['ok']
