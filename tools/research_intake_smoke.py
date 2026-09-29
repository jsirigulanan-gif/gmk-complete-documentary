#!/usr/bin/env python3
from pathlib import Path
import json, shutil, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
PACK_NAME='[Research Pack] The Ghost of P.T. & The Erasure of Hideo Kojima (LEMiNO Pipeline).docx'
PACK_CANDIDATES=[ROOT/'pilot'/'PT_WORKSPACE'/'inputs'/'research'/PACK_NAME, Path('/mnt/data')/PACK_NAME]
pack=next((p for p in PACK_CANDIDATES if p.is_file()),None)
if pack is None:
    raise SystemExit('P.T. Research Pack not found for smoke test.')
with tempfile.TemporaryDirectory(prefix='gmk-pt-intake-') as td:
    ws=Path(td)/'workspace'
    p=subprocess.run([sys.executable,'-m','gmk_cli','pilot-bootstrap','--workspace',str(ws),'--research-pack',str(pack),'--json'],cwd=ROOT,text=True,capture_output=True)
    if p.returncode:
        print(p.stdout);print(p.stderr,file=sys.stderr);raise SystemExit(p.returncode)
    out=json.loads(p.stdout)
    status=json.loads(subprocess.check_output([sys.executable,'-m','gmk_cli','status','--workspace',str(ws),'--json'],cwd=ROOT,text=True))
    replay=json.loads(subprocess.check_output([sys.executable,'-m','gmk_cli','research-intake','--workspace',str(ws),'--json'],cwd=ROOT,text=True))
    assert out['intake']['claims_created']==13
    assert out['intake']['evidence_created']==13
    assert out['intake']['source_leads_parsed']==5
    assert out['intake']['quotes_parsed']==4
    assert out['intake']['research_gaps_created']==4
    assert status['project_state']=='RESEARCH_INTAKE'
    assert status['next_legal_action']['action']=='RESOLVE_BLOCKER'
    assert replay['idempotent_replay'] is True
    print(json.dumps({'ok':True,'claims':13,'evidence':13,'source_leads':5,'quotes':4,'gaps':4,'project_state':'RESEARCH_INTAKE','next_action':'RESOLVE_BLOCKER','idempotent_replay':True},indent=2))
