from pathlib import Path
import json

from gmk_audit import AuditRuntime

ROOT=Path(__file__).resolve().parents[2]


def test_static_audit_passes_with_documented_legacy_warning():
    r=AuditRuntime(ROOT).run('STATIC')
    assert r.fail_count==0
    assert r.timeout_count==0
    assert r.overall_status=='PASS_WITH_WARNINGS'
    by={x.name:x for x in r.checks}
    assert by['pipeline_complete_marker'].status=='PASS'
    assert by['legacy_build001_changelog'].status=='WARN'
    assert by['pilot_external_media_boundary'].status=='PASS'


def test_audit_report_is_deterministic_for_same_static_tree(tmp_path):
    a=AuditRuntime(ROOT).run('STATIC')
    b=AuditRuntime(ROOT).run('STATIC')
    assert a.report_sha256==b.report_sha256
    jp=tmp_path/'audit.json'; mp=tmp_path/'audit.md'
    AuditRuntime.write_reports(a,jp,mp)
    data=json.loads(jp.read_text(encoding='utf-8'))
    assert data['report_sha256']==a.report_sha256
    assert 'GMK Repository Audit' in mp.read_text(encoding='utf-8')


def test_full_profile_declares_heavy_build_partitions_independently():
    parts=dict(AuditRuntime.HEAVY_PARTITIONS)
    assert 'build018' in parts
    assert 'build028' in parts
    assert parts['build018']==('tests/build018',)
