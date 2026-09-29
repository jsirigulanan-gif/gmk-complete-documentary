from __future__ import annotations
from pathlib import Path
import json, shutil, subprocess
import pytest

from gmk_pilot import (
    PilotMediaIntakeRuntime, PilotMediaProcessRuntime, PilotMediaProcessError,
    PilotExecutionResult,
)
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]

def _copy_pilot(tmp_path: Path)->Path:
    ws=tmp_path/'PT_WORKSPACE';shutil.copytree(ROOT/'pilot'/'PT_WORKSPACE',ws);return ws

def _video(path: Path,seconds: float=2.2)->None:
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i',f'color=size=160x90:rate=1:duration={seconds}','-c:v','mpeg4',str(path)],check=True)

def _ready_intake(ws: Path,tmp_path: Path):
    intake=tmp_path/'intake';init=PilotMediaIntakeRuntime(ROOT,ws).init(intake)
    _video(intake/'LISA_X_DIRECT_VERIFIED'/'lisa.mp4')
    _video(intake/'TGA_VIDEO'/'tga.mp4')
    ins=json.loads(init.worksheet_path.read_text())
    for x in ins['items']:
        x.update({'operator':'tester','inspection_note':'Inspected the exact local bytes.','visual_content':'Source-locked visual content inspected by human.','match_reason':'Human inspection matches the candidate purpose and source lock.'})
        if x['candidate_key']=='LISA_X_DIRECT_VERIFIED':
            x.update({'start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0})
        else:
            x.update({'start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8})
    return intake,ins

def test_default_process_builds_receipt_and_preflight_without_mutation(tmp_path):
    ws=_copy_pilot(tmp_path);intake,ins=_ready_intake(ws,tmp_path)
    before=ColdStartLoader(ROOT,ws).load().engine
    res=PilotMediaProcessRuntime(ROOT,ws).run(intake,ins,output_dir=tmp_path/'out')
    assert res.ready is True and res.execute_requested is False and res.mutated is False
    assert res.starting_state=='ASSET_RECON' and res.project_state=='ASSET_RECON'
    assert res.preflight['ready'] is True and res.execution is None
    assert res.report_path.is_file()
    after=ColdStartLoader(ROOT,ws).load().engine
    assert after.manifest_version==before.manifest_version and after.project_state=='ASSET_RECON'

def test_explicit_execute_delegates_only_after_passing_preflight(tmp_path,monkeypatch):
    ws=_copy_pilot(tmp_path);intake,ins=_ready_intake(ws,tmp_path)
    called=[]
    def fake_execute(self,plan):
        called.append(plan['batch_id'])
        return PilotExecutionResult(self.workspace,'ASSET_RECON','VISUAL_COVERAGE_READY',{'ok':True},{'ok':True},122,False)
    monkeypatch.setattr('gmk_pilot.process.PilotExecutionRuntime.execute',fake_execute)
    res=PilotMediaProcessRuntime(ROOT,ws).run(intake,ins,execute=True,output_dir=tmp_path/'out')
    assert called==['PT_MEDIA_HANDOFF_037']
    assert res.project_state=='VISUAL_COVERAGE_READY' and res.execute_requested is True
    assert res.preflight['ready'] is True and res.execution['project_state']=='VISUAL_COVERAGE_READY'

def test_completed_state_replay_skips_intake_and_mutation(tmp_path,monkeypatch):
    ws=_copy_pilot(tmp_path);rt=PilotMediaProcessRuntime(ROOT,ws)
    monkeypatch.setattr(rt,'_snapshot',lambda:('VISUAL_COVERAGE_READY',122,'abc'))
    monkeypatch.setattr('gmk_pilot.process.PilotMediaIntakeRuntime.build',lambda *a,**k: (_ for _ in ()).throw(AssertionError('must not build intake on replay')))
    res=rt.run(tmp_path/'does-not-matter',{},execute=True,output_dir=tmp_path/'out')
    assert res.project_state=='VISUAL_COVERAGE_READY' and res.mutated is False
    assert res.preflight['replay'] is True

def test_incomplete_inspection_fails_before_workspace_mutation(tmp_path):
    ws=_copy_pilot(tmp_path);intake,ins=_ready_intake(ws,tmp_path)
    next(x for x in ins['items'] if x['candidate_key']=='LISA_X_DIRECT_VERIFIED')['operator']=''
    before=ColdStartLoader(ROOT,ws).load().engine.manifest_version
    with pytest.raises(PilotMediaProcessError,match='INTAKE_FAILED'):
        PilotMediaProcessRuntime(ROOT,ws).run(intake,ins,execute=True)
    after=ColdStartLoader(ROOT,ws).load().engine
    assert after.project_state=='ASSET_RECON' and after.manifest_version==before

def test_cli_registers_pilot_media_process():
    from gmk_cli.cli import parser
    p=parser();choices=p._subparsers._group_actions[0].choices
    assert 'pilot-media-process' in choices
