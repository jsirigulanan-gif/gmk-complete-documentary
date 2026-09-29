from pathlib import Path
import json
import shutil

import pytest

from gmk_narrative import RoughNarrativeRuntime, RoughNarrativeError
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state import StateEngine

ROOT=Path(__file__).resolve().parents[2]


def seed_workspace(tmp_path:Path):
    ws=tmp_path/'ws'
    engine=StateEngine(ROOT,project_state='RESEARCH_AUDITED')
    tx=engine.begin()
    project=tx.create_object('PROJECT',{
        'title':'Narrative Test','working_title':'Narrative Test','language':{'narration':'th-TH'},
        'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':10,'max':20}},
    })
    good=tx.create_object('CLAIM',{
        'claim_text':'Audited claim','claim_type':'FACTUAL_ASSERTION','verification_state':'CORROBORATED','evidence_links':[],
        'certainty':{'level':'HIGH','basis':['TEST_SUPPORT']},
        'production_use':{'narration_allowed':True,'language_mode':'DIRECT','reason':'test'},'contradiction_refs':[],
    })
    bad=tx.create_object('CLAIM',{
        'claim_text':'Unsupported claim','claim_type':'RUMOR','verification_state':'INSUFFICIENT_EVIDENCE','evidence_links':[],
        'certainty':{'level':'LOW','basis':['INSUFFICIENT_SUPPORT']},
        'production_use':{'narration_allowed':False,'language_mode':'PROHIBITED','reason':'test'},'contradiction_refs':[],
    })
    tx.commit(); RuntimeStore(ROOT,ws).persist(engine)
    return ws,project,good,bad


def plan(claim_id='CLM_000001',batch_id='TEST_ROUGH'):
    return {
        'batch_id':batch_id,
        'spine':{
            'core_question':'What happened?',
            'opening_promise':'We will follow the audited evidence.',
            'central_mystery':'What remains?',
            'major_turns':['Audited event'],
            'final_answer':'The audited event is the current boundary.',
            'closing_thought':'No unsupported claim is needed.',
        },
        'excluded_claim_ids':[],
        'acts':[{
            'key':'A1','order':1,'title':'Act One',
            'narrative':{'job':'Establish the audited event.','audience_question':'What happened?','knowledge_before':'Unknown.','knowledge_after':'Known from audit.'},
            'scenes':[{
                'key':'S1','order':1,'title':'Scene One',
                'narrative':{'purpose':'Explain one audited fact.','viewer_question_entering':'What happened?','viewer_understanding_leaving':'The audited fact happened.'},
                'dynamics':{'role':'HOOK','energy':'BUILD'},
                'beats':[{
                    'key':'B1','order':1,'beat_type':'FACT','idea':'State the audited fact.','viewer_takeaway':'The fact is supported.',
                    'claims':[{'claim_id':claim_id,'role':'PRIMARY_FACT'}]
                }]
            }]
        }]
    }


def test_rough_narrative_creates_exact_graph_and_transitions(tmp_path):
    ws,_,good,_=seed_workspace(tmp_path)
    res=RoughNarrativeRuntime(ROOT,ws).run(plan(good['id']))
    assert res.project_state=='ROUGH_NARRATIVE_READY'
    assert res.gate_result=='PASS'
    assert len(res.act_refs)==1 and len(res.scene_refs)==1 and len(res.beat_refs)==1
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.engine.project_state=='ROUGH_NARRATIVE_READY'
    assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
    st=loaded.engine.snapshot()
    beat=st.objects[(res.beat_refs[0]['id'],res.beat_refs[0]['version'])]
    assert beat['workflow_state']=='RESEARCH_BOUND'
    assert beat['claim_bindings'][0]['claim_ref']==good
    art=st.artifacts[(res.narrative_spine_ref['artifact_id'],res.narrative_spine_ref['version'])]
    assert art['artifact_type']=='NARRATIVE_SPINE'
    assert art['extensions']['rough_narrative']['included_claim_refs']==[good]


def test_prohibited_claim_cannot_enter_rough_narrative(tmp_path):
    ws,_,_,bad=seed_workspace(tmp_path)
    with pytest.raises(RoughNarrativeError,match='ROUGH_NARRATIVE_CLAIM_PROHIBITED'):
        RoughNarrativeRuntime(ROOT,ws).run(plan(bad['id']))
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.engine.project_state=='RESEARCH_AUDITED'
    assert not [a for a in loaded.engine.snapshot().artifacts.values() if a.get('artifact_type')=='NARRATIVE_SPINE']


def test_rough_narrative_replay_is_idempotent_and_collision_fails(tmp_path):
    ws,_,good,_=seed_workspace(tmp_path)
    runtime=RoughNarrativeRuntime(ROOT,ws)
    first=runtime.run(plan(good['id'],'REPLAY'))
    second=runtime.run(plan(good['id'],'REPLAY'))
    assert first.idempotent_replay is False and second.idempotent_replay is True
    assert first.narrative_spine_ref==second.narrative_spine_ref
    changed=plan(good['id'],'REPLAY');changed['spine']['closing_thought']='Changed content.'
    with pytest.raises(RoughNarrativeError,match='ROUGH_NARRATIVE_BATCH_ID_COLLISION'):
        runtime.run(changed)


def test_real_pt_build013_workspace_is_rough_narrative_ready():
    ws=ROOT/'pilot'/'PT_WORKSPACE'
    if not ws.exists(): return
    loaded=ColdStartLoader(ROOT,ws).load(); st=loaded.engine.snapshot()
    assert loaded.engine.project_state in {'RESEARCH_AUDITED','ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY','ASSET_RECON'}
    if loaded.engine.project_state in {'ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY','ASSET_RECON'}:
        spines=[a for a in st.artifacts.values() if a.get('artifact_type')=='NARRATIVE_SPINE']
        assert spines
        active_beats=[]
        for reg in st.registries.values():
            for oid,e in reg.entries.items():
                if e.object_type=='NARRATION_BEAT' and e.active_version is not None:
                    active_beats.append(st.objects[(oid,int(e.active_version))])
        assert active_beats
        if loaded.engine.project_state=='ROUGH_NARRATIVE_READY':
            assert all(b['workflow_state']=='RESEARCH_BOUND' for b in active_beats)
        else:
            assert all(b['workflow_state']=='VISUAL_REQUIREMENT_READY' for b in active_beats)
