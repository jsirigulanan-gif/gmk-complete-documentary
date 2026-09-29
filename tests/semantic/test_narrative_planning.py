from gmk_semantics import StateView

def codes(v,s): return {x.code for x in v.validate_state(s)}

def test_narration_cannot_exceed_claim(validator,B):
    c=B("CLAIM","CLM_A",claim_text="x",claim_type="FACTUAL_ASSERTION",verification_state="CONTESTED",evidence_links=[],certainty={"level":"LOW","basis":[]},production_use={"narration_allowed":True,"language_mode":"QUALIFIED"})
    b=B("NARRATION_BEAT","NB_A",scene_ref={"id":"SCN_A","version":1},order=1,beat_type="FACT",idea={"summary":"x"},viewer_takeaway="x",claim_bindings=[{"claim_ref":{"id":"CLM_A","version":1},"role":"PRIMARY_FACT"}],narration={"text":"x","language_mode":"DIRECT"},workflow_state="DRAFT")
    assert "NARRATION_CERTAINTY_EXCEEDS_RESEARCH" in codes(validator,StateView.build([c,b]))

def test_non_base_layer_needs_purpose(validator,B):
    l=B("LAYER","LYR_A",stack_role="ANNOTATION",z_index=1,content={"type":"TEXT","text":"x"},motion={"decision":"NO_MOTION"})
    assert "LAYER_WITHOUT_COMPREHENSION_PURPOSE" in codes(validator,StateView.build([l]))

def test_three_d_known_unknown_cannot_overlap(validator,B):
    l=B("LAYER","LYR_A",stack_role="BASE",z_index=0,content={"type":"THREE_D","evidence_basis":[],"known":["DISTANCE"],"unknown":["DISTANCE"]},motion={"decision":"NO_MOTION"})
    cs=codes(validator,StateView.build([l]))
    assert "THREE_D_WITHOUT_EVIDENCE" in cs
    assert "THREE_D_KNOWN_UNKNOWN_CONFLICT" in cs

def test_shot_exactly_one_base_and_cue_target_in_shot(validator,B,A,sha):
    mv=A("MASTER_VOICE","MASTER_VOICE_A")
    tm=A("VOICE_TIMING_MAP","TIMING_A",master_voice={"artifact_id":"MASTER_VOICE_A","artifact_type":"MASTER_VOICE","version":1,"sha256":sha},duration_seconds=10,blocks=[])
    l1=B("LAYER","LYR_A",stack_role="BASE",z_index=0,content={"type":"TEXT","text":"a"},motion={"decision":"NO_MOTION"})
    l2=B("LAYER","LYR_B",stack_role="BASE",z_index=0,content={"type":"TEXT","text":"b"},motion={"decision":"NO_MOTION"})
    l3=B("LAYER","LYR_C",stack_role="ANNOTATION",z_index=1,content={"type":"TEXT","text":"c"},comprehension_purpose={"type":"LABEL_ENTITY","description":"x"},motion={"decision":"NO_MOTION"})
    cue=B("CUE","CUE_A",timing_source={"master_voice":{"artifact_id":"MASTER_VOICE_A","artifact_type":"MASTER_VOICE","version":1,"sha256":sha},"timing_map":{"artifact_id":"TIMING_A","artifact_type":"VOICE_TIMING_MAP","version":1,"sha256":sha}},semantic_trigger={"type":"PHRASE_ANCHOR","anchor_id":"A","offset_seconds":0},action={"type":"SHOW"},target_layer_refs=[{"id":"LYR_C","version":1}])
    shot=B("SHOT","SHT_A",scene_ref={"id":"SCN_A","version":1},order=1,beat_bindings=[{"beat_ref":{"id":"NB_A","version":1},"role":"PRIMARY"}],visual_job="x",viewer_takeaway="x",visual_strategy="DIRECT_FOOTAGE",timing={"voice_lock_manifest":{"artifact_id":"VL_A","artifact_type":"VOICE_LOCK_MANIFEST","version":1,"sha256":sha},"timing_map":{"artifact_id":"TIMING_A","artifact_type":"VOICE_TIMING_MAP","version":1,"sha256":sha},"start":{"type":"ABSOLUTE_MASTER_TIME","seconds":0},"end":{"type":"ABSOLUTE_MASTER_TIME","seconds":4}},layer_refs=[{"id":"LYR_A","version":1},{"id":"LYR_B","version":1}],cue_refs=[{"id":"CUE_A","version":1}],transition_out={"type":"CUT"},review_class={"value":"SIMPLE","derivation":"x"})
    cs=codes(validator,StateView.build([l1,l2,l3,cue,shot],[mv,tm]))
    assert "SHOT_MULTIPLE_BASE_LAYERS" in cs
    assert "CUE_TARGET_NOT_IN_SHOT" in cs
