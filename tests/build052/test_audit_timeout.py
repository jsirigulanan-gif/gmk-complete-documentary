import subprocess

from gmk_audit import AuditRuntime


def test_timeout_reports_partial_output_instead_of_crashing(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('fixture-command', 1, output=b'partial stdout\xff', stderr='partial stderr')
    monkeypatch.setattr(subprocess, 'run', timeout)
    result=AuditRuntime(tmp_path)._run('slow fixture', ['fixture-command'], 1)
    assert result.status=='TIMEOUT' and result.returncode is None
    assert 'partial stdout' in result.detail and 'partial stderr' in result.detail
