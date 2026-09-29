#!/usr/bin/env python3
from pathlib import Path
import json, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
checks=[]

def run(name,cmd,timeout=90):
    print(f'RUN {name}', flush=True)
    p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
    print(f'PASS {name}' if p.returncode==0 else f'FAIL {name}', flush=True)
    checks.append({'check':name,'ok':p.returncode==0,'stdout':p.stdout[-2000:],'stderr':p.stderr[-2000:]})
    if p.returncode!=0:
        print(json.dumps({'ok':False,'failed':name,'checks':checks},indent=2));raise SystemExit(p.returncode)

# Build 015 keeps the audit compact: the full pytest suite exercises the
# State/Dependency/Gate/Cold-start/Operations/Recovery/Render/QA/Release runtimes.
run('schema_validation',[sys.executable,'tools/validate_schemas.py'])
run('semantic_validation',[sys.executable,'tools/validate_semantics.py'])
run('repo_layout_audit',[sys.executable,'tools/repo_layout_audit.py'])
run('rough_narrative_smoke',[sys.executable,'tools/rough_narrative_smoke.py'])
run('visual_requirements_smoke',[sys.executable,'tools/visual_requirements_smoke.py'])
run('asset_recon_smoke',[sys.executable,'tools/asset_recon_smoke.py'])
run('cli_help',[sys.executable,'-m','gmk_cli','--help'])
print(json.dumps({'ok':True,'checks':[{'check':c['check'],'ok':c['ok']} for c in checks]},indent=2))
