from pathlib import Path
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine

FIXED='2026-09-27T06:10:00Z'

@pytest.fixture
def root(): return ROOT

@pytest.fixture
def engine(): return StateEngine(ROOT,clock=lambda:FIXED)

@pytest.fixture
def payloads():
    def source(title='Source', constraints=None):
        d={
            'source_type':'WEB_PAGE','title':title,'authority_class':'OFFICIAL',
            'independence':{'group_id':'SRCGRP_MAIN','relationship':'ORIGINAL'},
            'availability':{'state':'AVAILABLE'},'language':'en','accessed_at':FIXED,
        }
        if constraints is not None:d['human_constraints']=constraints
        return d
    def evidence(source_ref, summary='Observed fact', constraints=None):
        d={
            'source_ref':source_ref,'locator':{'type':'FULL_SOURCE'},
            'evidence_kind':'DOCUMENT_EXCERPT','content_summary':summary,
        }
        if constraints is not None:d['human_constraints']=constraints
        return d
    def claim(evidence_ref):
        return {
            'claim_text':'The documented event occurred.','claim_type':'FACTUAL_ASSERTION',
            'verification_state':'SOURCE_VERIFIED',
            'evidence_links':[{'evidence_ref':evidence_ref,'relation':'SUPPORTS','scope':['EVENT'],'strength':'DIRECT'}],
            'certainty':{'level':'HIGH','basis':['PRIMARY_EVIDENCE']},
            'production_use':{'narration_allowed':True,'language_mode':'DIRECT'},
        }
    def project():
        return {'title':'GMK','language':{'narration':'th-TH'},'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}}}
    def act(project_ref,title='Act'):
        return {'project_ref':project_ref,'order':1,'title':title,'narrative':{'job':'Set up','audience_question':'What happened?','knowledge_before':'Unknown','knowledge_after':'Context established'}}
    def scene(act_ref,constraints=None):
        d={'act_ref':act_ref,'order':1,'narrative':{'purpose':'Explain','viewer_question_entering':'Why?','viewer_understanding_leaving':'Understood'},'dynamics':{'role':'SETUP','energy':'CALM'}}
        if constraints is not None:d['human_constraints']=constraints
        return d
    return {'source':source,'evidence':evidence,'claim':claim,'project':project,'act':act,'scene':scene}
