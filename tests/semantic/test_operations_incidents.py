from gmk_semantics import StateView

def codes(v,s): return {x.code for x in v.validate_state(s)}

def test_operation_attempts_contiguous(validator,B):
    op=B("OPERATION","OP_A",operation_type="UPLOAD",subject={"id":"PROJECT_A","version":1},external_target={"provider":"X"},request={"action":"UPLOAD","input_fingerprint":"x"},idempotency_key="K",workflow_state="RUNNING",attempts=[{"attempt":2,"started_at":"2026-09-27T04:00:00Z"}])
    assert "OPERATION_ATTEMPT_SEQUENCE_INVALID" in codes(validator,StateView.build([op]))

def test_critical_incident_needs_containment(validator,B):
    inc=B("INCIDENT","INC_A",incident_type="REGISTRY_INTEGRITY",severity="CRITICAL",detected_at="2026-09-27T04:00:00Z",summary="x",affected_scope={"type":"PROJECT"},containment={"actions":[]},workflow_state="OPEN")
    assert "CRITICAL_INCIDENT_UNCONTAINED" in codes(validator,StateView.build([inc]))
