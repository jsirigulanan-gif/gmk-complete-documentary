#!/usr/bin/env python3
from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_narrative import RoughNarrativeRuntime
from gmk_runtime.cold_start import ColdStartLoader

ws=ROOT/'pilot'/'PT_WORKSPACE'
plan=json.loads((ROOT/'pilot'/'PT_ROUGH_NARRATIVE_INPUT.json').read_text(encoding='utf-8'))
res=RoughNarrativeRuntime(ROOT,ws).run(plan)
loaded=ColdStartLoader(ROOT,ws).load()
assert res.idempotent_replay is True
assert res.project_state in {'ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY','ASSET_RECON'}
assert res.gate_result=='PASS'
assert loaded.engine.project_state in {'ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY','ASSET_RECON'}
assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
assert len(res.act_refs)==5 and len(res.scene_refs)==7 and len(res.beat_refs)==10
print(json.dumps({'ok':True,'project_state':res.project_state,'manifest_version':res.manifest_version,'acts':len(res.act_refs),'scenes':len(res.scene_refs),'beats':len(res.beat_refs),'idempotent_replay':res.idempotent_replay},indent=2))
