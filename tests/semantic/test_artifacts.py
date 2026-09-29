from gmk_semantics import StateView


def codes(v,s): return {x.code for x in v.validate_state(s)}

def test_voice_timing_map_must_match_master_duration(validator,B,A,sha):
    p=B("PROJECT","PROJECT_A",title="A",language={"narration":"th"},target={"format":"LONGFORM_DOCUMENTARY","runtime_minutes":{"min":20,"max":30}})
    mv=A("MASTER_VOICE","MV_A",project_ref={"id":"PROJECT_A","version":1},source_voice_blocks=[],audio={"uri":"gmk://audio/master.wav","sha256":sha,"duration_seconds":10.0,"sample_rate_hz":48000,"channels":1})
    tm=A("VOICE_TIMING_MAP","TM_A",master_voice={"artifact_id":"MV_A","artifact_type":"MASTER_VOICE","version":1,"sha256":sha},duration_seconds=11.0,blocks=[])
    assert "VOICE_TIMING_DURATION_MISMATCH" in codes(validator,StateView.build([p],[mv,tm]))

def test_voiceover_compiled_text_cannot_drift(validator,B,A,sha):
    beat=B("NARRATION_BEAT","NB_A",scene_ref={"id":"SCN_A","version":1},order=1,beat_type="FACT",idea={"summary":"x"},viewer_takeaway="x",claim_bindings=[],narration={"text":"authority","language_mode":"DIRECT"},workflow_state="DRAFT")
    vo=A("VOICEOVER_SCRIPT_FINAL","VO_A",project_ref={"id":"PROJECT_A","version":1},language="th",blocks=[{"beat_ref":{"id":"NB_A","version":1},"decision_sha256":"f"*64,"narration_text":"drift"}])
    cs=codes(validator,StateView.build([beat],[vo]))
    assert "VOICEOVER_TEXT_DRIFT" in cs
    assert "VOICEOVER_BEAT_DECISION_HASH_DRIFT" in cs

def test_motion_previs_requires_start_key_end(validator,B,A):
    shot=B("SHOT","SHT_A",scene_ref={"id":"SCN_A","version":1},order=1,beat_bindings=[{"beat_ref":{"id":"NB_A","version":1},"role":"PRIMARY"}],visual_job="x",viewer_takeaway="x",visual_strategy="THREE_D_EXPLAINER",timing={"voice_lock_manifest":{"artifact_id":"VL_A","artifact_type":"VOICE_LOCK_MANIFEST","version":1,"sha256":"0"*64},"timing_map":{"artifact_id":"TM_A","artifact_type":"VOICE_TIMING_MAP","version":1,"sha256":"0"*64},"start":{"type":"ABSOLUTE_MASTER_TIME","seconds":0},"end":{"type":"ABSOLUTE_MASTER_TIME","seconds":1}},layer_refs=[],cue_refs=[],transition_out={"type":"CUT"},review_class={"value":"CRITICAL","derivation":"3D"})
    mp=A("MOTION_PREVIS","MP_A",shot_ref={"id":"SHT_A","version":1},preview={},key_states={"start":{},"end":{}})
    assert "MOTION_PREVIS_TEMPORAL_STATES_REQUIRED" in codes(validator,StateView.build([shot],[mp]))

def test_production_lock_requires_shot_child_closure(validator,B,A,sha):
    layer=B("LAYER","LYR_A",stack_role="BASE",z_index=0,content={"type":"TEXT","text":"x"},motion={"decision":"NO_MOTION"})
    shot=B("SHOT","SHT_A",scene_ref={"id":"SCN_A","version":1},order=1,beat_bindings=[{"beat_ref":{"id":"NB_A","version":1},"role":"PRIMARY"}],visual_job="x",viewer_takeaway="x",visual_strategy="DIRECT_FOOTAGE",timing={"voice_lock_manifest":{"artifact_id":"VL_A","artifact_type":"VOICE_LOCK_MANIFEST","version":1,"sha256":sha},"timing_map":{"artifact_id":"TM_A","artifact_type":"VOICE_TIMING_MAP","version":1,"sha256":sha},"start":{"type":"ABSOLUTE_MASTER_TIME","seconds":0},"end":{"type":"ABSOLUTE_MASTER_TIME","seconds":1}},layer_refs=[{"id":"LYR_A","version":1}],cue_refs=[],transition_out={"type":"CUT"},review_class={"value":"SIMPLE","derivation":"x"})
    dna=B("DESIGN_DNA","DNA_A",project_ref={"id":"PROJECT_A","version":1},base_design={"config_id":"BASE","version":"1.0.0","sha256":sha},design_intent={"visual_thesis":"x","audience_feeling":"x","clarity_principle":"x"},rules=[{"rule_id":"DNR_A","domain":"COMPOSITION","action":"PREFER","statement":"x","rationale":"x","human_decision_ref":{"id":"EDR_A","version":1}}],references=[{"artifact_id":"REF_A","artifact_type":"DESIGN_REFERENCE_BOARD","version":1,"sha256":sha}],token_overrides={},graphic_policy={"default_decision":"NO_GRAPHICS"})
    vl=A("VOICE_LOCK_MANIFEST","VL_A",voice_profile_ref={"id":"VP_A","version":1},voiceover_script={"artifact_id":"VO_A","artifact_type":"VOICEOVER_SCRIPT_FINAL","version":1,"sha256":sha},tts_script={"artifact_id":"TTS_A","artifact_type":"TTS_READY_SCRIPT","version":1,"sha256":sha},pronunciation_dictionary={"artifact_id":"PD_A","artifact_type":"PRONUNCIATION_DICTIONARY","version":1,"sha256":sha},voice_blocks=[],master_voice={"artifact_id":"MV_A","artifact_type":"MASTER_VOICE","version":1,"sha256":sha},timing_map={"artifact_id":"TM_A","artifact_type":"VOICE_TIMING_MAP","version":1,"sha256":sha})
    plan=A("SCENE_PLAN","PLAN_A",scene_ref={"id":"SCN_A","version":1},voice_lock={"artifact_id":"VL_A","artifact_type":"VOICE_LOCK_MANIFEST","version":1,"sha256":sha},design_dna_ref={"id":"DNA_A","version":1},design_tokens={"artifact_id":"TOK_A","artifact_type":"EFFECTIVE_DESIGN_TOKENS","version":1,"sha256":sha},scene_asset_pool={"artifact_id":"POOL_A","artifact_type":"SCENE_ASSET_POOL","version":1,"sha256":sha},shots=[{"shot_ref":{"id":"SHT_A","version":1}}])
    lock=A("PRODUCTION_LOCK_MANIFEST","PL_A",scope={"type":"SCENE"},system={"schema_version":"1.0.0","policy_bundle":{"config_id":"GMK_POLICY_BUNDLE","version":"1.0.0","sha256":sha}},voice_lock={"artifact_id":"VL_A","artifact_type":"VOICE_LOCK_MANIFEST","version":1,"sha256":sha},design_dna_ref={"id":"DNA_A","version":1},scene_plan={"artifact_id":"PLAN_A","artifact_type":"SCENE_PLAN","version":1,"sha256":sha},shots=[{"id":"SHT_A","version":1}],layers=[],cues=[],approvals=[],dependency_snapshot_sha256=sha)
    assert "PRODUCTION_LOCK_SHOT_LAYER_CLOSURE_FAILED" in codes(validator,StateView.build([layer,shot,dna],[vl,plan,lock]))

def test_artifact_lineage_contiguous(validator,A):
    a1=A("PROVENANCE_MANIFEST","PROV_A",entries=[],disclosures=[])
    a3=A("PROVENANCE_MANIFEST","PROV_A",3,supersedes_version=1,entries=[],disclosures=[])
    assert "ARTIFACT_VERSION_GAP" in codes(validator,StateView.build([], [a1,a3]))
