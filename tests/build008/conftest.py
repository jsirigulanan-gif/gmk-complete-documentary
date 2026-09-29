from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine

class Clock:
    def __init__(self): self.n=0; self.base=datetime(2026,9,27,9,0,0,tzinfo=timezone.utc)
    def __call__(self):
        self.n+=1
        return (self.base+timedelta(seconds=self.n)).isoformat().replace('+00:00','Z')

def bootstrap(engine):
    tx=engine.begin()
    project=tx.create_object('PROJECT',{'title':'GMK Build 008','language':{'narration':'th-TH'},'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}}})
    act=tx.create_object('ACT',{'project_ref':project,'order':1,'narrative':{'job':'Explain','audience_question':'What happened?','knowledge_before':'Unknown','knowledge_after':'Understood'}})
    scene=tx.create_object('SCENE',{'act_ref':act,'order':1,'narrative':{'purpose':'Explain production path','viewer_question_entering':'How?','viewer_understanding_leaving':'Clearly'},'dynamics':{'role':'SETUP','energy':'CALM'}})
    beat=tx.create_object('NARRATION_BEAT',{'scene_ref':scene,'order':1,'beat_type':'TRANSITION','idea':{'summary':'Move into the explanation'},'viewer_takeaway':'The mechanism is clear.','claim_bindings':[],'workflow_state':'DRAFT'})
    vp=tx.create_object('VOICE_PROFILE',{'profile_name':'GMK Test','engine_class':'TTS','language':'th-TH','delivery':{'default_style':'NEUTRAL_DOCUMENTARY','speech_rate':'NATURAL'},'technical_constraints':{'sample_rate_hz':48000,'channels':1}})
    refart=tx.create_artifact('RESEARCH_ATTEMPT_LOG',{'query':'design reference','provider':'human','strategy':'reference','sources_inspected':[],'result':'selected','limitations':[]})
    dna=tx.create_object('DESIGN_DNA',{'project_ref':project,'base_design':{'config_id':'GMK_BASE_DESIGN','version':'1.0.0','sha256':'1'*64},'design_intent':{'visual_thesis':'Evidence first.','audience_feeling':'Focused','clarity_principle':'Show only what clarifies.'},'rules':[{'rule_id':'DNR_TEST','domain':'COMPOSITION','action':'REQUIRE','statement':'Keep evidence clear.','rationale':'Clarity','reference_refs':[refart]}],'references':[refart],'token_overrides':{},'graphic_policy':{'default_decision':'NO_GRAPHICS'}})
    tx.commit()

    tx=engine.begin()
    script=tx.create_artifact('VOICEOVER_SCRIPT_FINAL',{'project_ref':project,'language':'th-TH','blocks':[]})
    pd=tx.create_artifact('PRONUNCIATION_DICTIONARY',{'language':'th-TH','entries':[]})
    tts=tx.create_artifact('TTS_READY_SCRIPT',{'source_script':script,'pronunciation_dictionary':pd,'voice_profile_ref':vp,'blocks':[]})
    mv=tx.create_artifact('MASTER_VOICE',{'project_ref':project,'source_voice_blocks':[],'audio':{'uri':'gmk://audio/master.wav','sha256':'2'*64,'duration_seconds':10.0,'sample_rate_hz':48000,'channels':1}})
    tm=tx.create_artifact('VOICE_TIMING_MAP',{'master_voice':mv,'duration_seconds':10.0,'blocks':[]})
    vl=tx.create_artifact('VOICE_LOCK_MANIFEST',{'voice_profile_ref':vp,'voiceover_script':script,'tts_script':tts,'pronunciation_dictionary':pd,'voice_blocks':[],'master_voice':mv,'timing_map':tm})
    layer=tx.create_object('LAYER',{'stack_role':'BASE','z_index':0,'content':{'type':'GRAPHIC_PRIMITIVE'},'motion':{'decision':'NO_MOTION'}})
    shot=tx.create_object('SHOT',{'scene_ref':scene,'order':1,'beat_bindings':[{'beat_ref':beat,'role':'PRIMARY'}],'visual_job':'Show the explanation cleanly.','viewer_takeaway':'The relationship is clear.','visual_strategy':'GRAPHIC_EXPLAINER','timing':{'voice_lock_manifest':vl,'timing_map':tm,'start':{'type':'ABSOLUTE_MASTER_TIME','seconds':0},'end':{'type':'ABSOLUTE_MASTER_TIME','seconds':5}},'layer_refs':[layer],'cue_refs':[],'transition_out':{'type':'CUT'},'review_class':{'value':'STANDARD','derivation':'GRAPHIC_EXPLAINER'}})
    tokens=tx.create_artifact('EFFECTIVE_DESIGN_TOKENS',{'base_design':{'config_id':'GMK_BASE_DESIGN','version':'1.0.0','sha256':'1'*64},'design_dna_ref':dna,'tokens':{}})
    pool=tx.create_artifact('SCENE_ASSET_POOL',{'scene_ref':scene,'beat_pools':[]})
    plan=tx.create_artifact('SCENE_PLAN',{'scene_ref':scene,'voice_lock':vl,'design_dna_ref':dna,'design_tokens':tokens,'scene_asset_pool':pool,'shots':[{'shot_ref':shot,'start_seconds':0,'end_seconds':5}]})
    preview=tx.create_artifact('SCENE_PREVIEW',{'scene_ref':scene,'scene_plan':plan,'shots':[shot],'preview':{'uri':'gmk://preview/scene.mp4'}})
    review=tx.create_artifact('REVIEW_PACKAGE',{'scope':{'type':'SCENE'},'scene_preview':preview,'scene_plan':plan,'shots':[{'shot_ref':shot,'review_class':'STANDARD'}]})
    tx.commit()

    # exact approvals for the production-lock policy
    state=engine.snapshot(); dh_dna=engine.semantic.decision_hash(state.objects[(dna['id'],dna['version'])]); dh_shot=engine.semantic.decision_hash(state.objects[(shot['id'],shot['version'])])
    tx=engine.begin()
    tx.create_approval({'approval_class':'VOICE','target':vl,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'DESIGN_DNA','target':dna,'target_decision_sha256':dh_dna,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'SCENE_PREVIEW','target':preview,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.create_approval({'approval_class':'SHOT_VISUAL','target':shot,'target_decision_sha256':dh_shot,'review_context':review,'decision':'APPROVED','actor':{'type':'HUMAN','actor_id':'OWNER'},'decided_at':engine.now()})
    tx.commit()
    return {'project':project,'scene':scene,'shot':shot,'layer':layer,'dna':dna,'voice_lock':vl,'timing_map':tm,'plan':plan,'preview':preview,'review':review}

@pytest.fixture
def root(): return ROOT
@pytest.fixture
def engine(root): return StateEngine(root,clock=Clock())
@pytest.fixture
def ready(engine): return bootstrap(engine)
