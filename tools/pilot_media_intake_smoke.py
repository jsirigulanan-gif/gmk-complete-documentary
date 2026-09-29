from __future__ import annotations
from pathlib import Path
import sys, tempfile, json

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from gmk_pilot import PilotMediaIntakeRuntime
from gmk_runtime.cold_start import ColdStartLoader

PILOT=ROOT/'pilot'/'PT_WORKSPACE'

def main()->int:
    before=ColdStartLoader(ROOT,PILOT).load().engine
    mv=before.manifest_version
    out=Path(tempfile.mkdtemp(prefix='gmk-pt-media-intake-smoke-'))
    res=PilotMediaIntakeRuntime(ROOT,PILOT).init(out)
    if res.requirement_count!=2: raise SystemExit(f'Unexpected requirements: {res.requirement_count}')
    manifest=json.loads(res.manifest_path.read_text(encoding='utf-8'))
    keys={x['candidate_key'] for x in manifest['requirements']}
    if keys!={'LISA_X_DIRECT_VERIFIED','TGA_VIDEO'}: raise SystemExit(f'Unexpected slots: {keys}')
    after=ColdStartLoader(ROOT,PILOT).load().engine
    if after.project_state!='ASSET_RECON' or after.manifest_version!=mv:
        raise SystemExit('Intake init mutated real P.T. workspace')
    print('P.T. media intake smoke: PASS')
    return 0

if __name__=='__main__': raise SystemExit(main())
