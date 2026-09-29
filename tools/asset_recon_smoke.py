#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_assets import AssetReconRuntime
from gmk_runtime.cold_start import ColdStartLoader

ws=ROOT/'pilot'/'PT_WORKSPACE'
plan=json.loads((ROOT/'pilot'/'PT_ASSET_RECON_INPUT.json').read_text(encoding='utf-8'))
res=AssetReconRuntime(ROOT,ws).run(plan)
loaded=ColdStartLoader(ROOT,ws).load(); st=loaded.engine.snapshot()
assert res.idempotent_replay is True
assert res.project_state=='ASSET_RECON'
assert res.search_count==20
assert res.candidate_count==30
assert res.viable_count==28
assert res.inspection_required_count==2
assert res.search_again_beats==('BEAT_LISA_FINDING',)
assert len(res.meet_target_beats)==9
assert res.gate_result=='FAIL'
assert loaded.engine.project_state=='ASSET_RECON'
assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
assert loaded.next_legal_action['target_state']=='ASSET_CATALOG_READY'
assert 'SEARCH_COMPLETION_CERTIFICATE' in ' '.join(loaded.next_legal_action.get('missing_requirements') or [])

def active_count(object_type):
    n=0
    for reg in st.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type==object_type and e.active_version is not None:n+=1
    return n
assert active_count('SEARCH')==20
assert active_count('SEARCH_RESULT')==30
assert active_count('ASSET')==0
assert active_count('SEGMENT')==0
assert sum(1 for a in st.artifacts.values() if a.get('artifact_type')=='CANDIDATE_COMPARISON')==10
print(json.dumps({
  'ok':True,'project_state':res.project_state,'manifest_version':res.manifest_version,
  'searches':res.search_count,'candidates':res.candidate_count,'viable':res.viable_count,
  'inspection_required':res.inspection_required_count,'meets_target':len(res.meet_target_beats),
  'search_again_beats':list(res.search_again_beats),'asset_objects':active_count('ASSET'),
  'segment_objects':active_count('SEGMENT'),'gate_result':res.gate_result,
  'idempotent_replay':res.idempotent_replay
},ensure_ascii=False,indent=2,sort_keys=True))
