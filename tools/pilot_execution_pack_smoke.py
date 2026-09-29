from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from gmk_pilot import PilotExecutionRuntime
from gmk_runtime.cold_start import ColdStartLoader

PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def main() -> int:
    before=ColdStartLoader(ROOT,PILOT).load().engine
    if before.project_state!='ASSET_RECON':
        raise SystemExit(f'Unexpected P.T. state: {before.project_state}')
    mv=before.manifest_version
    out=Path(tempfile.mkdtemp(prefix='gmk-pt-execution-pack-smoke-'))
    res=PilotExecutionRuntime(ROOT,PILOT).prepare(out)
    keys={x['candidate_key'] for x in res.requirements}
    if keys!={'LISA_X_DIRECT_VERIFIED','TGA_VIDEO'}:
        raise SystemExit(f'Unexpected requirements: {sorted(keys)}')
    if not all(p.is_file() for p in (res.execution_manifest_path,res.handoff_template_path,res.runbook_path)):
        raise SystemExit('Execution pack files missing')
    after=ColdStartLoader(ROOT,PILOT).load().engine
    if after.project_state!='ASSET_RECON' or after.manifest_version!=mv:
        raise SystemExit('Execution pack preparation mutated the real P.T. workspace')
    print('P.T. execution pack smoke: PASS')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
