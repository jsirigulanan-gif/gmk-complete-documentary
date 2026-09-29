from pathlib import Path
import copy

import pytest

from gmk_narrative import RoughNarrativeRuntime, VisualRequirementsRuntime, VisualRequirementsError
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state import StateEngine

ROOT=Path(__file__).resolve().parents[2]


def seed_workspace(tmp_path:Path):
    ws=tmp_path/'ws'
    engine=StateEngine(ROOT,project_state='RESEARCH_AUDITED')
    tx=engine.begin()
    tx.create_object('PROJECT',{
        'title':'Visual Requirements Test','working_title':'Visual Requirements Test','language':{'narration':'th-TH'},
        'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':10,'max':20}},
    })
    good=tx.create_object('CLAIM',{
        'claim_text':'Audited fact','claim_type':'FACTUAL_ASSERTION','verification_state':'CORROBORATED','evidence_links':[],
        'certainty':{'level':'HIGH','basis':['TEST_SUPPORT']},
        'production_use':{'narration_allowed':True,'language_mode':'DIRECT','reason':'test'},'contradiction_refs':[],
    })
    tx.commit(); RuntimeStore(ROOT,ws).persist(engine)
    rough={
        'batch_id':'TEST_ROUGH_VISUAL',
        'spine':{
            'core_question':'What happened?','opening_promise':'Follow the evidence.','central_mystery':'What remains?',
            'major_turns':['One audited event'],'final_answer':'Evidence remains.','closing_thought':'Access and history differ.',
        },
        'excluded_claim_ids':[],
        'acts':[{
            'key':'A1','order':1,'title':'Act One',
            'narrative':{'job':'Establish event.','audience_question':'What happened?','knowledge_before':'Unknown','knowledge_after':'Known'},
            'scenes':[{
                'key':'S1','order':1,'title':'Scene One',
                'narrative':{'purpose':'Explain fact.','viewer_question_entering':'What happened?','viewer_understanding_leaving':'Audited fact happened.'},
                'dynamics':{'role':'HOOK','energy':'BUILD'},
                'beats':[
                    {'key':'B1','order':1,'beat_type':'FACT','idea':'Show the audited fact.','viewer_takeaway':'The fact is supported.','claims':[{'claim_id':good['id'],'role':'PRIMARY_FACT'}]},
                    {'key':'B2','order':2,'beat_type':'PAYOFF','idea':'Connect the fact to the conclusion.','viewer_takeaway':'Evidence remains.','claims':[{'claim_id':good['id'],'role':'SUPPORTING_FACT'}]},
                ]
            }]
        }]
    }
    rr=RoughNarrativeRuntime(ROOT,ws).run(rough)
    assert rr.project_state=='ROUGH_NARRATIVE_READY'
    return ws,rr


def visual_plan(rr,batch='TEST_VISUAL_REQ'):
    return {
        'batch_id':batch,
        'source_narrative_batch_id':'TEST_ROUGH_VISUAL',
        'narrative_spine_ref':rr.narrative_spine_ref,
        'requirements':[
            {
                'beat_key':'B1',
                'viewer_must_see':'The dated primary document or footage proving the audited event.',
                'viewer_must_understand':'The event is grounded in direct evidence rather than generic b-roll.',
                'preferred_match':['DIRECT'],
                'asset_needs':['DOCUMENT','VIDEO'],
                'priority':'CRITICAL',
            },
            {
                'beat_key':'B2',
                'viewer_must_see':'A traceable sequence that returns to the same evidence and shows its consequence.',
                'viewer_must_understand':'The conclusion is a synthesis of the audited evidence already shown.',
                'preferred_match':['DIRECT','SUPPORTING'],
                'asset_needs':['DOCUMENT','STILL'],
                'priority':'MAJOR',
            },
        ]
    }


def test_visual_requirements_cover_all_beats_and_transition(tmp_path):
    ws,rr=seed_workspace(tmp_path)
    res=VisualRequirementsRuntime(ROOT,ws).run(visual_plan(rr))
    assert res.project_state=='VISUAL_REQUIREMENTS_READY'
    assert res.gate_result=='PASS'
    assert res.requirement_count==2
    assert res.priority_counts=={'CRITICAL':1,'MAJOR':1}
    loaded=ColdStartLoader(ROOT,ws).load(); st=loaded.engine.snapshot()
    assert loaded.engine.project_state=='VISUAL_REQUIREMENTS_READY'
    assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
    active=[]
    for reg in st.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type=='NARRATION_BEAT' and e.active_version is not None:
                active.append(st.objects[(oid,int(e.active_version))])
    assert len(active)==2
    assert all(b['workflow_state']=='VISUAL_REQUIREMENT_READY' for b in active)
    assert all('visual_requirement' in b for b in active)
    assert all('narration' not in b for b in active)
    assert all(((b.get('extensions') or {}).get('visual_requirements') or {}).get('source_narrative_spine_ref')==rr.narrative_spine_ref for b in active)


def test_visual_requirements_require_exact_beat_coverage(tmp_path):
    ws,rr=seed_workspace(tmp_path)
    p=visual_plan(rr);p['requirements']=p['requirements'][:1]
    with pytest.raises(VisualRequirementsError,match='VISUAL_REQUIREMENTS_COVERAGE_MISSING'):
        VisualRequirementsRuntime(ROOT,ws).run(p)
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.engine.project_state=='ROUGH_NARRATIVE_READY'


def test_visual_requirements_unknown_beat_and_placeholder_fail_closed(tmp_path):
    ws,rr=seed_workspace(tmp_path)
    p=visual_plan(rr);p['requirements'][1]['beat_key']='UNKNOWN'
    with pytest.raises(VisualRequirementsError,match='VISUAL_REQUIREMENTS_COVERAGE_MISSING|VISUAL_REQUIREMENTS_UNKNOWN_BEAT_KEY'):
        VisualRequirementsRuntime(ROOT,ws).run(p)
    p=visual_plan(rr,'TEST_VISUAL_PLACEHOLDER');p['requirements'][0]['viewer_must_see']='TBD'
    with pytest.raises(VisualRequirementsError,match='VISUAL_REQUIREMENTS_PLACEHOLDER_FORBIDDEN'):
        VisualRequirementsRuntime(ROOT,ws).run(p)


def test_visual_requirements_replay_and_collision(tmp_path):
    ws,rr=seed_workspace(tmp_path)
    runtime=VisualRequirementsRuntime(ROOT,ws);p=visual_plan(rr,'REPLAY_VISUAL')
    first=runtime.run(p);second=runtime.run(p)
    assert first.idempotent_replay is False and second.idempotent_replay is True
    assert first.beat_refs==second.beat_refs
    changed=copy.deepcopy(p);changed['requirements'][0]['viewer_must_understand']='Changed meaning.'
    with pytest.raises(VisualRequirementsError,match='VISUAL_REQUIREMENTS_BATCH_ID_COLLISION'):
        runtime.run(changed)


def test_real_pt_build014_workspace_visual_requirements_ready():
    ws=ROOT/'pilot'/'PT_WORKSPACE'
    if not ws.exists(): return
    loaded=ColdStartLoader(ROOT,ws).load();st=loaded.engine.snapshot()
    assert loaded.engine.project_state in {'ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY','ASSET_RECON'}
    if loaded.engine.project_state in {'VISUAL_REQUIREMENTS_READY','ASSET_RECON'}:
        beats=[]
        for reg in st.registries.values():
            for oid,e in reg.entries.items():
                if e.object_type=='NARRATION_BEAT' and e.active_version is not None:
                    beats.append(st.objects[(oid,int(e.active_version))])
        assert len(beats)==10
        assert all(b['workflow_state']=='VISUAL_REQUIREMENT_READY' for b in beats)
        assert all(b.get('visual_requirement') for b in beats)
        assert all('narration' not in b for b in beats)
