from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from gmk_state import StateEngine
from gmk_qa import QARuntime
from gmk_production import ProductionLockRuntime

class Clock:
    def __init__(self): self.n=0; self.base=datetime(2026,9,27,12,0,0,tzinfo=timezone.utc)
    def __call__(self):
        self.n+=1
        return (self.base+timedelta(seconds=self.n)).isoformat().replace('+00:00','Z')

def build_preproduction(engine):
    tx=engine.begin()
    project=tx.create_object('PROJECT',{'title':'GMK Build 009 E2E','language':{'narration':'th-TH'},'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':1,'max':10}}})
    src=tx.create_object('SOURCE',{'source_type':'DOCUMENT','title':'Synthetic primary source','authority_class':'PRIMARY','independence':{'group_id':'SRCGRP_SYNTH','relationship':'ORIGINAL'},'language':'en','availability':{'state':'AVAILABLE'},'accessed_at':engine.now()})
    evd=tx.create_object('EVIDENCE',{'source_ref':src,'locator':{'type':'FULL_SOURCE'},'evidence_kind':'DOCUMENT_EXCERPT','content_summary':'Synthetic evidence exists for pipeline integration testing.'})
    claim=tx.create_object('CLAIM',{'claim_text':'The synthetic integration fixture exists.','claim_type':'FACTUAL_ASSERTION','verification_state':'UNREVIEWED','evidence_links':[],'certainty':{'level':'UNKNOWN','basis':[]},'production_use':{'narration_allowed':False,'language_mode':'PROHIBITED','reason':'UNREVIEWED'}})
    act=tx.create_object('ACT',{'project_ref':project,'order':1,'narrative':{'job':'Explain','audience_question':'Does the pipeline work?','knowledge_before':'Unknown','knowledge_after':'Verified'}})
    scene=tx.create_object('SCENE',{'act_ref':act,'order':1,'narrative':{'purpose':'Exercise the full GMK pipeline','viewer_question_entering':'Will it complete?','viewer_understanding_leaving':'The pipeline completed.'},'dynamics':{'role':'SETUP','energy':'CALM'}})
    beat=tx.create_object('NARRATION_BEAT',{'scene_ref':scene,'order':1,'beat_type':'TRANSITION','idea':{'summary':'Move through the integration path.'},'viewer_takeaway':'The pipeline is traceable end to end.','claim_bindings':[],'visual_requirement':{'viewer_must_see':'A clean explanatory frame.','viewer_must_understand':'The runtime is executing frozen decisions.','preferred_match':['EXPLAINER'],'asset_needs':['STILL'],'priority':'STANDARD'},'workflow_state':'VISUAL_REQUIREMENT_READY'})
    vp=tx.create_object('VOICE_PROFILE',{'profile_name':'GMK Test','engine_class':'TTS','language':'th-TH','delivery':{'default_style':'NEUTRAL_DOCUMENTARY','speech_rate':'NATURAL'},'technical_constraints':{'sample_rate_hz':48000,'channels':1}})
    refart=tx.create_artifact('RESEARCH_ATTEMPT_LOG',{'query':'design reference','provider':'human','strategy':'reference','sources_inspected':[],'result':'selected','limitations':[]})
    dna=tx.create_object('DESIGN_DNA',{'project_ref':project,'base_design':{'config_id':'GMK_BASE_DESIGN','version':'1.0.0','sha256':'1'*64},'design_intent':{'visual_thesis':'Evidence first.','audience_feeling':'Focused','clarity_principle':'Show only what clarifies.'},'rules':[{'rule_id':'DNR_TEST','domain':'COMPOSITION','action':'REQUIRE','statement':'Keep explanatory content clear.','rationale':'Clarity','reference_refs':[refart]}],'references':[refart],'token_overrides':{},'graphic_policy':{'default_decision':'NO_GRAPHICS'}})
    tx.commit()

    tx=engine.begin()
    research_pack=tx.create_artifact('RESEARCH_PACK',{'title':'Synthetic research pack','research_summary':'Fixture used only for GMK runtime integration testing.','source_refs':[src]})
    spine=tx.create_artifact('NARRATIVE_SPINE',{'project_ref':project,'core_question':'Does the pipeline work?','opening_promise':'We will prove the runtime path.','major_turns':['Research','Production','Release']})
    script=tx.create_artifact('VOICEOVER_SCRIPT_FINAL',{'project_ref':project,'language':'th-TH','blocks':[]})
    pd=tx.create_artifact('PRONUNCIATION_DICTIONARY',{'language':'th-TH','entries':[]})
    tts=tx.create_artifact('TTS_READY_SCRIPT',{'source_script':script,'pronunciation_dictionary':pd,'voice_profile_ref':vp,'blocks':[]})
    mv=tx.create_artifact('MASTER_VOICE',{'project_ref':project,'source_voice_blocks':[],'audio':{'uri':'gmk://audio/master.wav','sha256':'2'*64,'duration_seconds':5.0,'sample_rate_hz':48000,'channels':1}})
    tm=tx.create_artifact('VOICE_TIMING_MAP',{'master_voice':mv,'duration_seconds':5.0,'blocks':[]})
    vl=tx.create_artifact('VOICE_LOCK_MANIFEST',{'voice_profile_ref':vp,'voiceover_script':script,'tts_script':tts,'pronunciation_dictionary':pd,'voice_blocks':[],'master_voice':mv,'timing_map':tm})
    layer=tx.create_object('LAYER',{'stack_role':'BASE','z_index':0,'content':{'type':'GRAPHIC_PRIMITIVE'},'motion':{'decision':'NO_MOTION'}})
    shot=tx.create_object('SHOT',{'scene_ref':scene,'order':1,'beat_bindings':[{'beat_ref':beat,'role':'PRIMARY'}],'visual_job':'Show a clean integration explanation.','viewer_takeaway':'The frozen graph drives production.','visual_strategy':'GRAPHIC_EXPLAINER','timing':{'voice_lock_manifest':vl,'timing_map':tm,'start':{'type':'ABSOLUTE_MASTER_TIME','seconds':0},'end':{'type':'ABSOLUTE_MASTER_TIME','seconds':5}},'layer_refs':[layer],'cue_refs':[],'transition_out':{'type':'CUT'},'review_class':{'value':'STANDARD','derivation':'GRAPHIC_EXPLAINER'}})
    tokens=tx.create_artifact('EFFECTIVE_DESIGN_TOKENS',{'base_design':{'config_id':'GMK_BASE_DESIGN','version':'1.0.0','sha256':'1'*64},'design_dna_ref':dna,'tokens':{}})
    pool=tx.create_artifact('SCENE_ASSET_POOL',{'scene_ref':scene,'beat_pools':[]})
    plan=tx.create_artifact('SCENE_PLAN',{'scene_ref':scene,'voice_lock':vl,'design_dna_ref':dna,'design_tokens':tokens,'scene_asset_pool':pool,'shots':[{'shot_ref':shot,'start_seconds':0,'end_seconds':5}]})
    preview=tx.create_artifact('SCENE_PREVIEW',{'scene_ref':scene,'scene_plan':plan,'shots':[shot],'preview':{'uri':'gmk://preview/scene.mp4'}})
    review=tx.create_artifact('REVIEW_PACKAGE',{'scope':{'type':'SCENE'},'scene_preview':preview,'scene_plan':plan,'shots':[{'shot_ref':shot,'review_class':'STANDARD'}]})
    tx.commit()

    # Research/asset gates use QA reports; this fixture intentionally has no production media Asset.
    q=QARuntime(engine)
    search_q=q.evaluate(report_type='SEARCH_COMPLETION_CERTIFICATE',scope=project,findings=[])
    coverage_q=q.evaluate(report_type='ASSET_COVERAGE_REPORT',scope=project,findings=[])

    state=engine.snapshot(); dh_dna=engine.semantic.decision_hash(state.objects[(dna['id'],dna['version'])]); dh_shot=engine.semantic.decision_hash(state.objects[(shot['id'],shot['version'])])
    tx=engine.begin()
    tx.create_approval({'approval_class':'VOICE','target':vl,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'DESIGN_DNA','target':dna,'target_decision_sha256':dh_dna,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'SCENE_PREVIEW','target':preview,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'SHOT_VISUAL','target':shot,'target_decision_sha256':dh_shot,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.commit()

    locks=ProductionLockRuntime(engine); scene_lock=locks.create_scene_lock(voice_lock_ref=vl,design_dna_ref=dna,scene_plan_ref=plan,scene_preview_ref=preview)
    project_lock=locks.create_project_lock(scene_lock_refs=[scene_lock])
    tx=engine.begin()
    tx.create_approval({'approval_class':'PRODUCTION_LOCK','target':scene_lock,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'PRODUCTION_LOCK','target':project_lock,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.commit()
    return {'project':project,'source':src,'evidence':evd,'claim':claim,'act':act,'scene':scene,'beat':beat,'voice_profile':vp,'dna':dna,'research_pack':research_pack,'spine':spine,'script':script,'tts':tts,'voice_lock':vl,'layer':layer,'shot':shot,'plan':plan,'preview':preview,'review':review,'scene_lock':scene_lock,'project_lock':project_lock,'search_qa':search_q['report_ref'],'coverage_qa':coverage_q['report_ref']}

@pytest.fixture
def root(): return ROOT
@pytest.fixture
def engine(root): return StateEngine(root,clock=Clock())
@pytest.fixture
def full_ready(engine): return build_preproduction(engine)
