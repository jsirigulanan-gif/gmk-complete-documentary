#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_narrative import VisualRequirementsRuntime
from gmk_runtime.cold_start import ColdStartLoader

ws=ROOT/'pilot'/'PT_WORKSPACE'
plan=json.loads((ROOT/'pilot'/'PT_VISUAL_REQUIREMENTS_INPUT.json').read_text(encoding='utf-8'))
res=VisualRequirementsRuntime(ROOT,ws).run(plan)
loaded=ColdStartLoader(ROOT,ws).load()
assert res.project_state in {'VISUAL_REQUIREMENTS_READY','ASSET_RECON'}
assert res.gate_result=='PASS'
assert res.requirement_count==10
assert loaded.engine.project_state in {'VISUAL_REQUIREMENTS_READY','ASSET_RECON'}
assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
assert loaded.next_legal_action['target_state'] in {'ASSET_RECON','ASSET_CATALOG_READY'}
st=loaded.engine.snapshot();beats=[]
for reg in st.registries.values():
    for oid,e in reg.entries.items():
        if e.object_type=='NARRATION_BEAT' and e.active_version is not None:
            beats.append(st.objects[(oid,int(e.active_version))])
assert len(beats)==10
assert all(b.get('workflow_state')=='VISUAL_REQUIREMENT_READY' for b in beats)
assert all(b.get('visual_requirement') for b in beats)
assert all('narration' not in b for b in beats)
print(json.dumps({
    'ok':True,
    'project_state':res.project_state,
    'manifest_version':res.manifest_version,
    'visual_requirements':res.requirement_count,
    'priority_counts':res.priority_counts,
    'asset_need_counts':res.asset_need_counts,
    'gate_result':res.gate_result,
    'next_target':loaded.next_legal_action['target_state'],
    'idempotent_replay':res.idempotent_replay,
},ensure_ascii=False,indent=2,sort_keys=True))
