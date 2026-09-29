import json
import pytest
from gmk_state import ResolverMode
from gmk_runtime import RuntimeStore, ColdStartLoader, ColdStartError
from gmk_semantics.model import sha256_json
from gmk_state.constants import STANDARD_REGISTRY_IDS


def create_project(engine,P):
    tx=engine.begin();ref=tx.create_object('PROJECT',P());tx.commit();return ref


def create_spine(engine,project_ref):
    tx=engine.begin();ref=tx.create_artifact('NARRATIVE_SPINE',{
        'project_ref':project_ref,'core_question':'What happened?','opening_promise':'We will reconstruct it.',
        'central_mystery':'Why did it disappear?','major_turns':['Reveal'],'final_answer':'Documented answer','closing_thought':'Close.'
    },origin_refs=[project_ref]);tx.commit();return ref


def test_artifact_registry_versions_are_system_owned(engine,P):
    p=create_project(engine,P);a1=create_spine(engine,p)
    snap=engine.artifact_registry_snapshot();entry=snap['entries'][a1['artifact_id']]
    assert snap['version']==2 and entry['head_version']==1
    tx=engine.begin();a2=tx.create_artifact_version(a1['artifact_id'],base_version=1,payload_patch={'central_mystery':'A sharper question'});tx.commit()
    snap=engine.artifact_registry_snapshot();entry=snap['entries'][a1['artifact_id']]
    assert snap['version']==3 and entry['head_version']==2
    assert a2['version']==2 and a1['sha256']!=a2['sha256']


def test_manifest_pins_all_standard_registries_and_artifact_registry(engine,P,tmp_path):
    p=create_project(engine,P);create_spine(engine,p)
    m=RuntimeStore(engine.root,tmp_path/'ws').persist(engine)
    assert set(STANDARD_REGISTRY_IDS).issubset(m['registries'])
    assert 'ARTIFACT_REGISTRY' in m['registries']
    assert m['current']['narrative_spine']['artifact_type']=='NARRATIVE_SPINE'
    assert m['project_ref']==p
    assert m['system']['master_spec_id']=='GMK_MASTER_SPEC_V2'
    assert m['system']['master_checkpoint_id']=='GMK_PIPELINE_V2_CHECKPOINT_002'


def test_cold_start_roundtrip_preserves_exact_head_active_and_artifact_head(engine,P,tmp_path):
    p=create_project(engine,P)
    tx=engine.begin();v2=tx.create_version(p['id'],base_version=1,patch={'working_title':'Unpromoted v2'});tx.commit()
    a1=create_spine(engine,p)
    tx=engine.begin();a2=tx.create_artifact_version(a1['artifact_id'],base_version=1,payload_patch={'central_mystery':'v2'});tx.commit()
    ws=tmp_path/'ws';manifest=RuntimeStore(engine.root,ws).persist(engine)
    loaded=ColdStartLoader(engine.root,ws).load(clock=lambda:'2026-09-27T07:31:00Z')
    r=loaded.engine.resolver()
    assert r.resolve(p['id'],mode=ResolverMode.HEAD)['version']==2
    assert r.resolve(p['id'],mode=ResolverMode.ACTIVE)['version']==1
    assert loaded.engine.artifact_registry_snapshot()['entries'][a1['artifact_id']]['head_version']==2
    assert loaded.manifest['manifest_version']==manifest['manifest_version']==engine.manifest_version
    assert loaded.loaded_artifacts==2
    assert loaded.engine.registry_snapshots()==engine.registry_snapshots()


def test_persist_is_idempotent_for_unchanged_state(engine,P,tmp_path):
    create_project(engine,P);ws=tmp_path/'ws';store=RuntimeStore(engine.root,ws)
    m1=store.persist(engine);m2=store.persist(engine)
    assert m1==m2
    pointer=json.loads((ws/'CURRENT_MANIFEST.json').read_text())
    assert pointer['manifest_version']==engine.manifest_version
    assert pointer['sha256']==sha256_json(m1)


def test_cold_start_fails_closed_on_tampered_object(engine,P,tmp_path):
    p=create_project(engine,P);ws=tmp_path/'ws';RuntimeStore(engine.root,ws).persist(engine)
    path=ws/'objects'/p['id']/'v1.json';obj=json.loads(path.read_text());obj['title']='TAMPERED';path.write_text(json.dumps(obj),encoding='utf-8')
    with pytest.raises(ColdStartError) as exc:ColdStartLoader(engine.root,ws).load()
    assert exc.value.code=='OBJECT_RECORD_HASH_MISMATCH'


def test_cold_start_fails_closed_on_registry_hash_mismatch(engine,P,tmp_path):
    create_project(engine,P);ws=tmp_path/'ws';m=RuntimeStore(engine.root,ws).persist(engine)
    ptr=m['registries']['PROJECT_REGISTRY'];path=ws/'registries'/'PROJECT_REGISTRY'/f"v{ptr['version']}.json"
    reg=json.loads(path.read_text());reg['entries']['FAKE']={'object_id':'FAKE','object_type':'PROJECT','head_version':1,'active_version':1,'versions':{}};path.write_text(json.dumps(reg),encoding='utf-8')
    with pytest.raises(ColdStartError) as exc:ColdStartLoader(engine.root,ws).load()
    assert exc.value.code=='REGISTRY_HASH_MISMATCH'


def test_cold_start_requires_every_standard_registry_pointer(engine,P,tmp_path):
    create_project(engine,P);ws=tmp_path/'ws';m=RuntimeStore(engine.root,ws).persist(engine)
    mpath=ws/'manifests'/m['manifest_id']/f"v{m['manifest_version']}.json"
    doc=json.loads(mpath.read_text());doc['registries'].pop('RESEARCH_REGISTRY');mpath.write_text(json.dumps(doc),encoding='utf-8')
    pointer=json.loads((ws/'CURRENT_MANIFEST.json').read_text());pointer['sha256']=sha256_json(doc);(ws/'CURRENT_MANIFEST.json').write_text(json.dumps(pointer),encoding='utf-8')
    with pytest.raises(ColdStartError) as exc:ColdStartLoader(engine.root,ws).load()
    assert exc.value.code=='REGISTRY_MISSING'
