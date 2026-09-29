from pathlib import Path
from tempfile import TemporaryDirectory
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine, ResolverMode
from gmk_runtime import RuntimeStore, ColdStartLoader

FIXED='2026-09-27T07:45:00Z'
e=StateEngine(ROOT,clock=lambda:FIXED)
tx=e.begin();p=tx.create_object('PROJECT',{'title':'Runtime Smoke','language':{'narration':'th-TH'},'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':30}}});tx.commit()
tx=e.begin();a=tx.create_artifact('NARRATIVE_SPINE',{'project_ref':p,'core_question':'Can GMK resume cold?','opening_promise':'Prove it.','central_mystery':'Persistence','major_turns':['Persist','Reload']},origin_refs=[p]);tx.commit()
tx=e.begin();tx.create_version(p['id'],base_version=1,patch={'working_title':'HEAD only'});tx.commit()
with TemporaryDirectory(prefix='gmk-runtime-smoke-') as d:
    RuntimeStore(ROOT,Path(d)).persist(e)
    result=ColdStartLoader(ROOT,Path(d)).load(clock=lambda:'2026-09-27T07:46:00Z')
    r=result.engine.resolver()
    assert r.resolve(p['id'],mode=ResolverMode.HEAD)['version']==2
    assert r.resolve(p['id'],mode=ResolverMode.ACTIVE)['version']==1
    assert result.engine.artifact_registry_snapshot()['entries'][a['artifact_id']]['head_version']==1
    assert result.engine.registry_snapshots()==e.registry_snapshots()
    print('Runtime persistence + Cold Start smoke: PASS')
    print('manifest_version:',result.manifest['manifest_version'])
    print('loaded_objects:',result.loaded_objects)
    print('loaded_artifacts:',result.loaded_artifacts)
    print('next_legal_action:',result.next_legal_action['action'])
