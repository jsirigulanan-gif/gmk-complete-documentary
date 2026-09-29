from __future__ import annotations
from pathlib import Path
import json, shutil, subprocess

from gmk_pilot import PilotMediaIntakeRuntime, PilotReadinessRuntime
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]

def _copy_pilot(tmp_path: Path)->Path:
    ws=tmp_path/'PT_WORKSPACE';shutil.copytree(ROOT/'pilot'/'PT_WORKSPACE',ws);return ws

def _video(path: Path,seconds: float=2.2)->None:
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i',f'color=size=160x90:rate=1:duration={seconds}','-c:v','mpeg4',str(path)],check=True)

def _fill_worksheet(path: Path)->dict:
    ins=json.loads(path.read_text())
    for x in ins['items']:
        x.update({'operator':'tester','inspection_note':'Inspected actual local bytes.','visual_content':'Source-locked media visually inspected.','match_reason':'Human inspection matches the candidate purpose and locked source.'})
        if x['candidate_key']=='LISA_X_DIRECT_VERIFIED':
            x.update({'start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0})
        else:
            x.update({'start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8})
    path.write_text(json.dumps(ins,indent=2)+'\n')
    return ins

def test_empty_intake_reports_blocked_media_without_workspace_mutation(tmp_path):
    ws=_copy_pilot(tmp_path);intake=tmp_path/'intake';PilotMediaIntakeRuntime(ROOT,ws).init(intake)
    before=ColdStartLoader(ROOT,ws).load().engine
    res=PilotReadinessRuntime(ROOT,ws).inspect(intake,tmp_path/'out')
    assert res.readiness=='BLOCKED_MEDIA' and not res.ready_to_execute
    assert {x['media_state'] for x in res.slots}=={'MISSING'}
    assert res.report_json.is_file() and res.report_markdown.is_file()
    after=ColdStartLoader(ROOT,ws).load().engine
    assert after.project_state=='ASSET_RECON' and after.manifest_version==before.manifest_version

def test_media_present_but_worksheet_incomplete_reports_blocked_inspection(tmp_path):
    ws=_copy_pilot(tmp_path);intake=tmp_path/'intake';PilotMediaIntakeRuntime(ROOT,ws).init(intake)
    _video(intake/'LISA_X_DIRECT_VERIFIED'/'lisa.mp4');_video(intake/'TGA_VIDEO'/'tga.mp4')
    res=PilotReadinessRuntime(ROOT,ws).inspect(intake)
    assert res.readiness=='BLOCKED_INSPECTION' and not res.ready_to_execute
    assert all(x['media_state']=='PRESENT' for x in res.slots)
    assert any(x.startswith('INSPECTION_INCOMPLETE:') for x in res.blockers)

def test_complete_intake_runs_authoritative_preflight_and_reports_ready(tmp_path):
    ws=_copy_pilot(tmp_path);intake=tmp_path/'intake';init=PilotMediaIntakeRuntime(ROOT,ws).init(intake)
    _video(intake/'LISA_X_DIRECT_VERIFIED'/'lisa.mp4');_video(intake/'TGA_VIDEO'/'tga.mp4')
    _fill_worksheet(init.worksheet_path)
    before=(ws/'CURRENT_MANIFEST.json').read_bytes()
    res=PilotReadinessRuntime(ROOT,ws).inspect(intake,tmp_path/'out')
    assert res.readiness=='READY_TO_EXECUTE' and res.ready_to_execute
    assert not res.blockers and res.workspace_mutated is False
    assert (ws/'CURRENT_MANIFEST.json').read_bytes()==before

def test_source_url_mismatch_is_visible_before_preflight(tmp_path):
    ws=_copy_pilot(tmp_path);intake=tmp_path/'intake';init=PilotMediaIntakeRuntime(ROOT,ws).init(intake)
    _video(intake/'LISA_X_DIRECT_VERIFIED'/'lisa.mp4');_video(intake/'TGA_VIDEO'/'tga.mp4')
    ins=_fill_worksheet(init.worksheet_path)
    ins['items'][0]['source_url']='https://example.invalid/wrong'
    init.worksheet_path.write_text(json.dumps(ins,indent=2)+'\n')
    res=PilotReadinessRuntime(ROOT,ws).inspect(intake)
    assert res.readiness=='BLOCKED_INSPECTION'
    assert any(x.startswith('SOURCE_URL_MISMATCH:') for x in res.blockers)

def test_cli_registers_pilot_readiness():
    from gmk_cli.cli import parser
    choices=parser()._subparsers._group_actions[0].choices
    assert 'pilot-readiness' in choices
