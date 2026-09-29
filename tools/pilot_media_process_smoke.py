#!/usr/bin/env python3
from pathlib import Path
import json, shutil, subprocess, tempfile

ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from gmk_pilot import PilotMediaIntakeRuntime, PilotMediaProcessRuntime
from gmk_runtime.cold_start import ColdStartLoader


def video(path: Path):
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i','color=size=160x90:rate=1:duration=2.2','-c:v','mpeg4',str(path)],check=True)

with tempfile.TemporaryDirectory(prefix='gmk-media-process-smoke-') as td:
    td=Path(td)
    ws=td/'PT_WORKSPACE';shutil.copytree(ROOT/'pilot'/'PT_WORKSPACE',ws)
    intake=td/'intake';init=PilotMediaIntakeRuntime(ROOT,ws).init(intake)
    video(intake/'LISA_X_DIRECT_VERIFIED'/'lisa.mp4')
    video(intake/'TGA_VIDEO'/'tga.mp4')
    ins=json.loads(init.worksheet_path.read_text(encoding='utf-8'))
    for item in ins['items']:
        item.update({'operator':'smoke','inspection_note':'Smoke inspection of exact local fixture bytes.','visual_content':'Source-locked media fixture for non-mutating smoke.','match_reason':'Exercises intake receipt and authoritative handoff preflight only.'})
        if item['candidate_key']=='LISA_X_DIRECT_VERIFIED':
            item.update({'start_seconds':0.1,'end_seconds':1.5,'key_seconds':1.0})
        else:
            item.update({'start_seconds':0.2,'end_seconds':1.7,'key_seconds':0.8})
    before=ColdStartLoader(ROOT,ws).load().engine
    result=PilotMediaProcessRuntime(ROOT,ws).run(intake,ins,execute=False,output_dir=td/'out')
    after=ColdStartLoader(ROOT,ws).load().engine
    assert result.ready and not result.mutated and result.project_state=='ASSET_RECON'
    assert before.manifest_version==after.manifest_version
    print(json.dumps({'ok':True,'ready':result.ready,'mutated':result.mutated,'state':result.project_state},indent=2))
