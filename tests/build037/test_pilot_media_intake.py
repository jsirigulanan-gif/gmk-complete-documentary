from __future__ import annotations
from pathlib import Path
import json, shutil, subprocess
import pytest

from gmk_pilot import PilotMediaIntakeRuntime, PilotMediaIntakeError, PilotExecutionRuntime
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]

def _copy_pilot(tmp_path: Path)->Path:
    ws=tmp_path/'PT_WORKSPACE';shutil.copytree(ROOT/'pilot'/'PT_WORKSPACE',ws);return ws

def _video(path: Path, seconds: float=2.2)->None:
    # Low frame rate keeps long duration boundary fixtures fast while remaining real probeable video.
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i',f'color=size=160x90:rate=1:duration={seconds}','-c:v','mpeg4',str(path)],check=True)

def _filled(ws: Path,tmp_path: Path):
    intake=tmp_path/'intake';rt=PilotMediaIntakeRuntime(ROOT,ws);init=rt.init(intake)
    _video(intake/'LISA_X_DIRECT_VERIFIED'/'lisa.mp4')
    _video(intake/'TGA_VIDEO'/'tga.mp4')
    ins=json.loads(init.worksheet_path.read_text())
    for x in ins['items']:
        x.update({'operator':'tester','inspection_note':'Inspected actual local test media.','visual_content':'Inspected source-locked media for runtime validation.','match_reason':'Human inspection recorded for the exact candidate slot.'})
        if x['candidate_key']=='LISA_X_DIRECT_VERIFIED':
            x.update({'start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0})
        else:
            x.update({'start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8})
    return rt,init,ins

def test_init_creates_exact_source_locked_slots_without_workspace_mutation(tmp_path):
    ws=_copy_pilot(tmp_path);before=ColdStartLoader(ROOT,ws).load().engine
    rt=PilotMediaIntakeRuntime(ROOT,ws);res=rt.init(tmp_path/'intake')
    assert res.requirement_count==2
    by={x['candidate_key']:x for x in res.slots}
    assert by['LISA_X_DIRECT_VERIFIED']['canonical_source_url']=='https://twitter.com/manfightdragon/status/1170860592233472001'
    assert by['TGA_VIDEO']['locked_locator']['end_seconds']==135
    assert (tmp_path/'intake'/'LISA_X_DIRECT_VERIFIED'/'README.txt').is_file()
    after=ColdStartLoader(ROOT,ws).load().engine
    assert after.project_state=='ASSET_RECON' and after.manifest_version==before.manifest_version

def test_build_requires_exactly_one_media_per_slot(tmp_path):
    ws=_copy_pilot(tmp_path);rt=PilotMediaIntakeRuntime(ROOT,ws);init=rt.init(tmp_path/'intake')
    ins=json.loads(init.worksheet_path.read_text())
    with pytest.raises(PilotMediaIntakeError,match='MEDIA_MISSING'):
        rt.build(tmp_path/'intake',ins)

def test_build_probes_hashes_receipts_and_generates_preflight_ready_plan_without_mutation(tmp_path):
    ws=_copy_pilot(tmp_path);before=ColdStartLoader(ROOT,ws).load().engine
    rt,init,ins=_filled(ws,tmp_path);res=rt.build(init.intake_dir,ins)
    assert res.ready and res.item_count==2
    plan=json.loads(res.handoff_plan_path.read_text());receipt=json.loads(res.receipt_path.read_text())
    assert len(plan['items'])==2 and len(receipt['items'])==2
    assert all(len(x['sha256'])==64 and x['technical']['duration_seconds']>0 for x in receipt['items'])
    assert all(x['expected_sha256'] for x in plan['items'])
    pf=PilotExecutionRuntime(ROOT,ws).preflight(plan)
    assert pf.ready and len(pf.validated_items)==2
    after=ColdStartLoader(ROOT,ws).load().engine
    assert after.project_state=='ASSET_RECON' and after.manifest_version==before.manifest_version

def test_build_rejects_incomplete_human_inspection(tmp_path):
    ws=_copy_pilot(tmp_path);rt,init,ins=_filled(ws,tmp_path)
    next(x for x in ins['items'] if x['candidate_key']=='LISA_X_DIRECT_VERIFIED')['operator']=''
    with pytest.raises(PilotMediaIntakeError,match='OPERATOR_REQUIRED'):
        rt.build(init.intake_dir,ins)

def test_build_rejects_range_outside_source_lock_via_authoritative_handoff_validation(tmp_path):
    ws=_copy_pilot(tmp_path);rt,init,ins=_filled(ws,tmp_path)
    # Use longer test media so the local file itself allows the range; source lock must reject it.
    _video(init.intake_dir/'TGA_VIDEO'/'tga.mp4',seconds=140.0)
    tga=next(x for x in ins['items'] if x['candidate_key']=='TGA_VIDEO')
    tga.update({'start_seconds':130.0,'end_seconds':138.0,'key_seconds':134.0})
    with pytest.raises(PilotMediaIntakeError,match='SOURCE_LOCK_RANGE_EXCEEDED'):
        rt.build(init.intake_dir,ins)

def test_static_audit_requires_matching_intake_and_execution_source_locks():
    from gmk_audit import AuditRuntime
    result=AuditRuntime(ROOT).run('STATIC')
    by={x.name:x for x in result.checks}
    assert result.fail_count==0
    assert by['pilot_media_intake_pack'].status=='PASS'
