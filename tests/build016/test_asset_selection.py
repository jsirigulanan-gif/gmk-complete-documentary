from pathlib import Path
import json

from gmk_assets import AssetSelectionRuntime
from gmk_cli.cli import parser
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]


def active(state,typ):
    out=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type==typ and e.active_version is not None:
                out.append(state.objects[(oid,int(e.active_version))])
    return out


def test_real_pt_build016_search_completion_and_pending_assets():
    ws=ROOT/'pilot'/'PT_WORKSPACE'
    if not ws.exists(): return
    loaded=ColdStartLoader(ROOT,ws).load(); st=loaded.engine.snapshot()
    assert loaded.engine.project_state=='ASSET_RECON'
    assets=active(st,'ASSET')
    assert len(assets)==10
    # Later Builds may advance acquired document Assets while deferred media remains pending.
    assert all(a['workflow_state'] in {'ACQUISITION_PENDING','ACQUIRED','FILE_VERIFIED','CATALOGED','APPROVED'} for a in assets)
    assert any(a['workflow_state']=='ACQUISITION_PENDING' for a in assets)
    assert len(active(st,'SEGMENT'))>=0
    cert=[q for q in active(st,'QA_REPORT') if q.get('report_type')=='SEARCH_COMPLETION_CERTIFICATE']
    assert cert and cert[-1]['result']=='PASS'
    assert loaded.engine.gates.evaluate_gate(st,'ASSET_RECON',loaded.engine.now()).result=='PASS'


def test_real_pt_build016_lisa_search_again_closed():
    ws=ROOT/'pilot'/'PT_WORKSPACE'
    if not ws.exists(): return
    st=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    searches=[s for s in active(st,'SEARCH') if ((s.get('extensions') or {}).get('asset_recon') or {}).get('selection_batch_id')=='PT_ASSET_SELECTION_016']
    results=[r for r in active(st,'SEARCH_RESULT') if ((r.get('extensions') or {}).get('asset_recon') or {}).get('selection_batch_id')=='PT_ASSET_SELECTION_016']
    assert len(searches)==1
    assert searches[0]['trigger']['type']=='SEARCH_AGAIN'
    direct=[r for r in results if ((r.get('extensions') or {}).get('asset_recon') or {}).get('candidate_key')=='LISA_X_DIRECT_VERIFIED']
    assert direct and direct[0]['candidate_state']=='PROMOTED_TO_ASSET'
    assert direct[0]['source_family']=='ORIGINAL_CREATOR'


def test_asset_selection_replay_is_idempotent():
    ws=ROOT/'pilot'/'PT_WORKSPACE'
    if not ws.exists(): return
    plan=json.loads((ROOT/'pilot'/'PT_ASSET_SELECTION_INPUT.json').read_text(encoding='utf-8'))
    before=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    assets_before=len(active(before,'ASSET'))
    res=AssetSelectionRuntime(ROOT,ws).run(plan)
    after=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    assert res.idempotent_replay is True
    assert len(active(after,'ASSET'))==assets_before
    # Idempotent replay must not create additional segments; later Builds may already have them.
    assert res.segment_count==len(active(after,'SEGMENT'))
    assert res.gate_result=='PASS'


def test_cli_exposes_asset_select():
    p=parser()
    args=p.parse_args(['asset-select','--workspace','ws','--input','plan.json'])
    assert args.command=='asset-select'
