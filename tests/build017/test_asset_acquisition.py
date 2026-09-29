from pathlib import Path
import json, shutil

from gmk_assets import AssetAcquisitionRuntime
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'
PLAN=ROOT/'pilot'/'PT_ASSET_ACQUISITION_INPUT.json'


def test_pt_asset_acquisition_persisted_and_cold_starts():
    loaded=ColdStartLoader(ROOT,PILOT).load()
    state=loaded.engine.snapshot()
    assets=[]
    segments=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.active_version is None: continue
            obj=state.objects[(oid,int(e.active_version))]
            if obj.get('object_type')=='ASSET': assets.append(obj)
            if obj.get('object_type')=='SEGMENT': segments.append(obj)
    assert sum(a.get('workflow_state')=='CATALOGED' for a in assets)==8
    assert sum(a.get('workflow_state')=='ACQUISITION_PENDING' for a in assets)==2
    assert len(segments)==8
    for a in assets:
        if a.get('workflow_state')=='CATALOGED':
            assert len(a['original_file']['checksum'])==64
            assert a['original_file']['immutable'] is True


def test_acquisition_replay_is_idempotent(tmp_path):
    ws=tmp_path/'PT_WORKSPACE'
    shutil.copytree(PILOT,ws)
    plan=json.loads(PLAN.read_text(encoding='utf-8'))
    result=AssetAcquisitionRuntime(ROOT,ws).run(plan)
    assert result.idempotent_replay is True
    assert len(result.acquired_asset_refs)==8
    assert len(result.pending_asset_refs)==2
    assert len(result.segment_refs)==8


def test_search_result_lifecycle_revision_is_non_production():
    loaded=ColdStartLoader(ROOT,PILOT).load()
    state=loaded.engine.snapshot()
    before=state.objects[('SR_000002',2)]
    after=state.objects[('SR_000002',3)]
    change=loaded.engine.dependency.changes_between(before,after,loaded.engine.semantic)
    assert change.impact_tags==('NON_PRODUCTION',)
