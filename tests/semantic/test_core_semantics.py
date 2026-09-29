from gmk_semantics import StateView


def codes(v,state): return {x.code for x in v.validate_state(state)}

def test_lineage_requires_exact_previous_version(validator,B):
    v1=B("SOURCE","SRC_A")
    v3=B("SOURCE","SRC_A",3,supersedes={"id":"SRC_A","version":1},source_type="WEB_PAGE",title="x",authority_class="PRIMARY",independence={"group_id":"I"},availability="AVAILABLE",language="en",accessed_at="2026-09-27T04:00:00Z")
    assert "OBJECT_VERSION_GAP" in codes(validator,StateView.build([v1,v3]))

def test_human_constraint_must_carry_forward(validator,B):
    c={"constraint_id":"HC_KEEP","scope":{"path":"/title"},"rule":{"type":"PRESERVE","statement":"keep"},"lock_state":"HUMAN_LOCKED"}
    a=B("PROJECT","PROJECT_A",human_constraints=[c],title="A",language={"narration":"th"},target={"format":"LONGFORM_DOCUMENTARY","runtime_minutes":{"min":20,"max":30}})
    b=B("PROJECT","PROJECT_A",2,supersedes={"id":"PROJECT_A","version":1},title="B",language={"narration":"th"},target={"format":"LONGFORM_DOCUMENTARY","runtime_minutes":{"min":20,"max":30}})
    assert "HUMAN_CONSTRAINT_NOT_CARRIED_FORWARD" in codes(validator,StateView.build([a,b]))

def test_project_runtime(validator,B):
    p=B("PROJECT","PROJECT_A",title="A",language={"narration":"th"},target={"format":"LONGFORM_DOCUMENTARY","runtime_minutes":{"min":31,"max":30}})
    assert "PROJECT_RUNTIME_RANGE_INVALID" in codes(validator,StateView.build([p]))
