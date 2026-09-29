from gmk_semantics import StateView


def codes(v,s): return {x.code for x in v.validate_state(s)}

def test_disproven_requires_counter_evidence(validator,B):
    c=B("CLAIM","CLM_A",claim_text="x",claim_type="FACTUAL_ASSERTION",verification_state="DISPROVEN",evidence_links=[],certainty={"level":"LOW","basis":[]},production_use={"narration_allowed":False,"language_mode":"PROHIBITED"})
    assert "DISPROVEN_WITHOUT_COUNTER_EVIDENCE" in codes(validator,StateView.build([c]))

def test_claim_exact_evidence_unique(validator,B):
    e=B("EVIDENCE","EVD_A",source_ref={"id":"SRC_A","version":1},locator={"type":"FULL_SOURCE"},evidence_kind="DOCUMENT",content_summary="x")
    c=B("CLAIM","CLM_A",claim_text="x",claim_type="FACTUAL_ASSERTION",verification_state="SOURCE_VERIFIED",evidence_links=[
      {"evidence_ref":{"id":"EVD_A","version":1},"relation":"SUPPORTS","scope":["EVENT"],"strength":"DIRECT"},
      {"evidence_ref":{"id":"EVD_A","version":1},"relation":"QUALIFIES","scope":["TIMELINE"],"strength":"STRONG"}],certainty={"level":"MEDIUM","basis":[]},production_use={"narration_allowed":True,"language_mode":"QUALIFIED"})
    assert "CLAIM_EVIDENCE_LINK_DUPLICATE" in codes(validator,StateView.build([e,c]))

def test_viable_candidate_requires_inspection_and_source(validator,B):
    r=B("SEARCH_RESULT","SR_A",search_ref={"id":"SEARCH_A","version":1},discovery_method="HUMAN_INJECTION",discovery_locator={"type":"LOGICAL_URI","value":"gmk://incoming/a"},title="a",source_family="OTHER",candidate_state="VIABLE")
    cs=codes(validator,StateView.build([r]))
    assert "VIABLE_CANDIDATE_SOURCE_REQUIRED" in cs
    assert "VIABLE_CANDIDATE_INSPECTION_INCOMPLETE" in cs

def test_acquired_asset_needs_immutable_file(validator,B):
    a=B("ASSET","AST_A",origin_search_result_ref={"id":"SR_A","version":1},source_ref={"id":"SRC_A","version":1},media_type="VIDEO",asset_class="DIRECT_FOOTAGE",workflow_state="ACQUIRED",rights={"status":"CLEAR"})
    assert "ACQUIRED_ASSET_FILE_REQUIRED" in codes(validator,StateView.build([a]))
