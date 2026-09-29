from gmk_semantics import StateView

def codes(v,s): return {x.code for x in v.validate_state(s)}

def test_approval_hash_is_exact(validator,B,A,sha):
    p=B("PROJECT","PROJECT_A",title="A",language={"narration":"th"},target={"format":"LONGFORM_DOCUMENTARY","runtime_minutes":{"min":20,"max":30}})
    rp=A("REVIEW_PACKAGE","RP_A",scope={},scene_preview={"artifact_id":"SP_A","artifact_type":"SCENE_PREVIEW","version":1,"sha256":sha},scene_plan={"artifact_id":"PLAN_A","artifact_type":"SCENE_PLAN","version":1,"sha256":sha},shots=[])
    ap=B("APPROVAL","APR_A",approval_class="SHOT_VISUAL",target={"id":"PROJECT_A","version":1},target_decision_sha256="f"*64,review_context={"artifact_id":"RP_A","artifact_type":"REVIEW_PACKAGE","version":1,"sha256":sha},decision="APPROVED",actor={"type":"HUMAN","actor_id":"U"},decided_at="2026-09-27T04:00:00Z")
    assert "APPROVAL_TARGET_HASH_MISMATCH" in codes(validator,StateView.build([p,ap],[rp]))

def test_final_render_requires_lock(validator,B,A,sha):
    prompt=A("RENDERER_PROMPT","PROMPT_A",production_lock={"artifact_id":"PL_A","artifact_type":"PRODUCTION_LOCK_MANIFEST","version":1,"sha256":sha},renderer_adapter={"config_id":"ADAPTER","version":"1.0.0","sha256":sha},compiled_payload={})
    r=B("RENDER_JOB","RJ_A",render_level="FINAL",scope={"type":"PROJECT","target":{"id":"PROJECT_A","version":1}},input_snapshot={"snapshot_sha256":sha,"inputs":[]},renderer={"adapter_id":"A","adapter_version":"1.0.0"},renderer_prompt={"artifact_id":"PROMPT_A","artifact_type":"RENDERER_PROMPT","version":1,"sha256":sha},output_profile={"config_id":"OUT","version":"1.0.0","sha256":sha},cost_class="HIGH",workflow_state="QUEUED")
    assert "FINAL_RENDER_PRODUCTION_LOCK_REQUIRED" in codes(validator,StateView.build([r],[prompt]))

def test_resolved_qa_issue_requires_retest(validator,B):
    q=B("QA_ISSUE","QAI_A",qa_domain="SHOT",severity="MAJOR",code="X",target={"id":"SHT_A","version":1},description="x",root_cause={"state":"IDENTIFIED","category":"CUE_TIMING"},workflow_state="RESOLVED")
    assert "QA_ISSUE_RESOLVED_WITHOUT_RETEST" in codes(validator,StateView.build([q]))

def test_released_release_requires_timestamp(validator,B,A,sha):
    refs=lambda typ,id:{"artifact_id":id,"artifact_type":typ,"version":1,"sha256":sha}
    rel=B("RELEASE","REL_A",project_ref={"id":"PROJECT_A","version":1},release_label="v1",production_lock=refs("PRODUCTION_LOCK_MANIFEST","PL_A"),master_output=refs("FINAL_FILM_MASTER","MASTER_A"),delivery_profile={"config_id":"DELIVERY","version":"1.0.0","sha256":sha},final_asset_manifest=refs("FINAL_ASSET_MANIFEST","FAM_A"),provenance_manifest=refs("PROVENANCE_MANIFEST","PROV_A"),qa_reports=[],state="RELEASED")
    assert "RELEASED_AT_REQUIRED" in codes(validator,StateView.build([rel]))
