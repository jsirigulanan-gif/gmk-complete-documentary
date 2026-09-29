import pytest
from gmk_gate import GateEngine
from gmk_state import StateEngine, StateEngineError

FIXED='2026-09-27T06:55:00Z'

def art(aid,typ,v=1,ch='a',**extra):
    return {'artifact_id':aid,'artifact_type':typ,'version':v,'sha256':ch*64,**extra}

def test_bootstrap_gate_pass_and_missing_fail(root,S):
    g=GateEngine(root)
    fail=g.evaluate_gate(S(), 'BOOTSTRAP', FIXED)
    assert fail.result=='FAIL'
    s=S(artifacts=[art('RESEARCH_PACK_001','RESEARCH_PACK')])
    ok=g.evaluate_gate(s,'BOOTSTRAP',FIXED)
    assert ok.result=='PASS'
    assert ok.evidence[0]['artifact_type']=='RESEARCH_PACK'

def test_historical_gate_result_invalidates_when_artifact_head_moves(root,S):
    g=GateEngine(root)
    a1=art('RESEARCH_PACK_001','RESEARCH_PACK',1,'a')
    s=S(artifacts=[a1])
    ev=g.evaluate_gate(s,'BOOTSTRAP',FIXED)
    assert g.effective(s,ev).validity=='VALID'
    a2=art('RESEARCH_PACK_001','RESEARCH_PACK',2,'b')
    s.artifacts[(a2['artifact_id'],2)]=a2
    eff=g.effective(s,ev)
    assert eff.validity=='INVALIDATED'
    assert any('ARTIFACT_NOT_CURRENT_HEAD' in x for x in eff.invalidation_reasons)

def test_direct_project_state_jump_is_forbidden(root,S):
    g=GateEngine(root)
    d=g.evaluate_transition(S(artifacts=[art('RESEARCH_PACK_001','RESEARCH_PACK')]),'BOOTSTRAPPED','RESEARCH_AUDITED',FIXED,actor_type='AI')
    assert not d.allowed
    assert d.permission_class=='FORBIDDEN'
    assert 'TRANSITION_NOT_DEFINED' in d.reason_codes

def test_next_legal_action_reports_missing_gate_then_transition(root,S):
    g=GateEngine(root)
    a=g.next_legal_action(S(),FIXED,actor_type='AI')
    assert a.action=='SATISFY_GATE_REQUIREMENTS'
    assert a.target_state=='RESEARCH_INTAKE'
    b=g.next_legal_action(S(artifacts=[art('RESEARCH_PACK_001','RESEARCH_PACK')]),FIXED,actor_type='AI')
    assert b.action=='TRANSITION_PROJECT_STATE'

def test_scoped_critical_qa_blocker_does_not_block_research_gate(root,S,E):
    issue=E('QA_ISSUE','QAI_001',qa_domain='SHOT',severity='CRITICAL',workflow_state='OPEN')
    g=GateEngine(root); s=S(objects=[issue])
    assert g.derive_blockers(s,gate_id='RESEARCH_AUDIT')==[]
    prod=g.derive_blockers(s,gate_id='PRODUCTION_LOCK')
    assert len(prod)==1 and prod[0].code=='CRITICAL_QA_ISSUE_OPEN'

def test_research_gap_blocks_only_declared_gate(root,S,E):
    gap=E('RESEARCH_GAP','GAP_001',question='Unknown critical fact',importance='CRITICAL',state='OPEN',blocked_targets=[],blocked_gates=['RESEARCH_AUDIT'],research_attempt_refs=[])
    g=GateEngine(root); s=S(objects=[gap])
    assert len(g.derive_blockers(s,gate_id='RESEARCH_AUDIT'))==1
    assert g.derive_blockers(s,gate_id='SCRIPT')==[]

def test_warn_gate_requires_exception_and_exact_exception_allows(root,S,E):
    q=E('QA_REPORT','QAR_001',report_type='SEARCH_COMPLETION_CERTIFICATE',scope={'id':'PROJECT_X','version':1},qa_profile={'config_id':'QA','version':'1.0.0','sha256':'a'*64},issue_refs=[],result='WARN',summary={'critical':0,'major':0,'minor':1},evaluated_at=FIXED)
    s=S(objects=[q],project_state='ASSET_RECON')
    g=GateEngine(root)
    d=g.evaluate_transition(s,'ASSET_RECON','ASSET_CATALOG_READY',FIXED,actor_type='AI')
    assert not d.allowed and d.warning_requires_acceptance
    ex=E('APPROVAL','APR_001',approval_class='EXCEPTION',target={'id':'QAR_001','version':1},decision='APPROVED',actor={'type':'HUMAN','actor_id':'OWNER'},decided_at=FIXED)
    s2=S(objects=[q,ex],project_state='ASSET_RECON')
    d2=g.evaluate_transition(s2,'ASSET_RECON','ASSET_CATALOG_READY',FIXED,actor_type='AI')
    assert d2.allowed

def test_human_permission_class_is_enforced_for_voice_lock(root,S,E):
    vl=art('VOICE_LOCK_001','VOICE_LOCK_MANIFEST')
    ap=E('APPROVAL','APR_VOICE',approval_class='VOICE',target={'artifact_id':'VOICE_LOCK_001','artifact_type':'VOICE_LOCK_MANIFEST','version':1,'sha256':'a'*64},decision='APPROVED',actor={'type':'HUMAN','actor_id':'OWNER'},decided_at=FIXED)
    s=S(objects=[ap],artifacts=[vl],project_state='TTS_READY')
    g=GateEngine(root)
    sys=g.evaluate_transition(s,'TTS_READY','VOICE_LOCKED',FIXED,actor_type='SYSTEM')
    assert not sys.allowed and 'HUMAN_CONFIRMATION_REQUIRED' in sys.reason_codes
    human=g.evaluate_transition(s,'TTS_READY','VOICE_LOCKED',FIXED,actor_type='HUMAN')
    assert human.allowed

def test_project_completion_predicate_requires_release_and_final_checkpoint(root,S,E):
    g=GateEngine(root)
    empty=g.evaluate_transition(S(project_state='DELIVERY_READY'),'DELIVERY_READY','PROJECT_COMPLETED',FIXED)
    assert not empty.allowed
    rel=E('RELEASE','REL_001',state='RELEASED')
    cp=E('CHECKPOINT','CP_001',checkpoint_class='FINAL_PROJECT',integrity_summary='PASS')
    done=g.evaluate_transition(S(objects=[rel,cp],project_state='DELIVERY_READY'),'DELIVERY_READY','PROJECT_COMPLETED',FIXED)
    assert done.allowed

def test_transaction_rechecks_gate_against_final_staged_state(root):
    pack=art('RESEARCH_PACK_001','RESEARCH_PACK')
    e=StateEngine(root,artifacts=[pack],clock=lambda:FIXED)
    tx=e.begin(); tx.transition_project_state('RESEARCH_INTAKE',actor_type='AI')
    tx.create_object('RESEARCH_GAP',{'question':'Critical unresolved blocker','importance':'CRITICAL','state':'OPEN','blocked_targets':[],'blocked_gates':['BOOTSTRAP'],'research_attempt_refs':[]})
    with pytest.raises(StateEngineError) as err:tx.commit()
    assert err.value.code=='PROJECT_STATE_TRANSITION_REVALIDATION_FAILED'
    assert e.project_state=='BOOTSTRAPPED'

def test_reenter_stage_is_explicit_human_only(root):
    e=StateEngine(root,project_state='SCRIPT_READY',clock=lambda:FIXED)
    tx=e.begin()
    with pytest.raises(StateEngineError) as err:tx.reenter_stage('VISUAL_COVERAGE_READY',actor_type='AI')
    assert err.value.code=='REENTER_STAGE_HUMAN_ONLY'
    tx=e.begin();tx.reenter_stage('VISUAL_COVERAGE_READY',actor_type='HUMAN');tx.commit()
    assert e.project_state=='VISUAL_COVERAGE_READY'

def test_gate_policy_is_pinned_in_policy_bundle(root):
    import hashlib,yaml
    gates=root/'config/gates_policies.yaml'; bundle=yaml.safe_load((root/'config/gmk_policy_bundle.yaml').read_text())
    assert bundle['policies']['gates']['sha256']==hashlib.sha256(gates.read_bytes()).hexdigest()
