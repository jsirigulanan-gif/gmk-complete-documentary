import pytest
from gmk_state import StateEngine, ResolverMode, StateEngineError, ConcurrencyConflict, ValidationFailure


def create_project(engine,P,title='A',constraints=None):
    tx=engine.begin(); ref=tx.create_object('PROJECT',P(title,constraints=constraints)); tx.commit(); return ref


def test_create_object_issues_identity_and_activates_v1(engine,P):
    ref=create_project(engine,P)
    assert ref=={'id':'PROJECT_000001','version':1}
    snap=engine.registry_snapshots()['PROJECT_REGISTRY']
    e=snap['entries']['PROJECT_000001']
    assert e['head_version']==1 and e['active_version']==1
    assert len(e['versions']['1']['decision_sha256'])==64
    assert len(e['versions']['1']['record_sha256'])==64
    assert engine.manifest_version==2


def test_create_version_moves_head_not_active(engine,P):
    ref=create_project(engine,P,'A')
    tx=engine.begin(); v2=tx.create_version(ref['id'],base_version=1,patch={'title':'B'}); tx.commit()
    r=engine.resolver()
    assert r.resolve(ref['id'],mode=ResolverMode.HEAD)['version']==2
    assert r.resolve(ref['id'],mode=ResolverMode.ACTIVE)['version']==1
    assert r.resolve(ref['id'],mode=ResolverMode.EXACT,version=2)['title']=='B'
    assert v2['version']==2


def test_promote_active_is_explicit(engine,P):
    ref=create_project(engine,P)
    tx=engine.begin(); v2=tx.create_version(ref['id'],base_version=1,patch={'working_title':'Draft 2'}); tx.commit()
    tx=engine.begin(); tx.promote_active_version(ref['id'],v2['version']); tx.commit()
    assert engine.resolver().resolve(ref['id'],mode=ResolverMode.ACTIVE)['version']==2
    assert engine.registry_versions()['PROJECT_REGISTRY']==4


def test_exact_resolver_requires_version(engine,P):
    ref=create_project(engine,P)
    with pytest.raises(StateEngineError) as e:
        engine.resolver().resolve(ref['id'],mode=ResolverMode.EXACT)
    assert e.value.code=='EXACT_VERSION_REQUIRED'


def test_committed_records_are_copy_isolated(engine,P):
    ref=create_project(engine,P,'Immutable')
    a=engine.resolver().resolve(ref['id'],mode=ResolverMode.EXACT,version=1)
    a['title']='MUTATED OUTSIDE'
    b=engine.resolver().resolve(ref['id'],mode=ResolverMode.EXACT,version=1)
    assert b['title']=='Immutable'


def test_optimistic_manifest_concurrency(engine,P):
    tx1=engine.begin(); tx2=engine.begin()
    tx1.create_object('PROJECT',P('One')); tx1.commit()
    tx2.create_object('PROJECT',P('Two'))
    with pytest.raises(ConcurrencyConflict) as e: tx2.commit()
    assert e.value.code=='MANIFEST_VERSION_CONFLICT'


def test_failed_validation_publishes_nothing(engine,P):
    before=engine.manifest_version
    tx=engine.begin(); tx.create_object('PROJECT',{
      'title':'Bad','language':{'narration':'th-TH'},
      'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':50,'max':10}}
    })
    with pytest.raises(ValidationFailure): tx.commit()
    assert engine.manifest_version==before
    assert all(not snap['entries'] for snap in engine.registry_snapshots().values())


def test_system_managed_fields_cannot_be_injected(engine,P):
    tx=engine.begin()
    data=P('A'); data['id']='PROJECT_HACK'
    with pytest.raises(StateEngineError) as e: tx.create_object('PROJECT',data)
    assert e.value.code=='SYSTEM_MANAGED_FIELD_OVERRIDE'


def test_no_branching_from_non_head(engine,P):
    ref=create_project(engine,P)
    tx=engine.begin(); tx.create_version(ref['id'],base_version=1,patch={'working_title':'v2'}); tx.commit()
    tx=engine.begin()
    with pytest.raises(StateEngineError) as e: tx.create_version(ref['id'],base_version=1,patch={'working_title':'branch'})
    assert e.value.code=='REVISION_BASE_VERSION_MISMATCH'


def test_human_lock_blocks_locked_path(engine,P):
    c={'constraint_id':'HC_KEEP_TITLE','scope':{'path':'/title'},'rule':{'type':'PRESERVE','statement':'Keep title'},'lock_state':'HUMAN_LOCKED'}
    ref=create_project(engine,P,'Locked',constraints=[c])
    tx=engine.begin()
    with pytest.raises(StateEngineError) as e: tx.create_version(ref['id'],base_version=1,patch={'title':'Changed'})
    assert e.value.code=='HUMAN_LOCK_CONFLICT'


def test_explicit_release_constraint_allows_revision(engine,P):
    c={'constraint_id':'HC_KEEP_TITLE','scope':{'path':'/title'},'rule':{'type':'PRESERVE','statement':'Keep title'},'lock_state':'HUMAN_LOCKED'}
    ref=create_project(engine,P,'Locked',constraints=[c])
    tx=engine.begin()
    er=tx.create_edit_request({
      'target':ref,
      'directive':{'type':'RELEASE_CONSTRAINT','instruction':'Release title lock','constraint_id':'HC_KEEP_TITLE'},
      'priority':'MAJOR','workflow_state':'OPEN','requested_by':{'type':'HUMAN','actor_id':'OWNER'}
    }); tx.commit()
    tx=engine.begin()
    result=tx.apply_revision(reason_type='HUMAN_EDIT_REQUEST',edit_request_refs=[er],edits=[{
      'object_id':ref['id'],'base_version':1,
      'patch':{'title':'Changed','human_constraints':[]},
      'changed_paths':['/title'],'summary':'Human released title lock.'
    }]); tx.commit()
    v2=result['new_versions'][0]
    obj=engine.resolver().resolve(v2['id'],mode=ResolverMode.EXACT,version=2)
    assert obj['title']=='Changed'
    assert obj['extensions']['released_human_constraints']==['HC_KEEP_TITLE']


def test_derived_refresh_changes_record_hash_not_decision_hash(engine,P):
    ref=create_project(engine,P,'A')
    before=engine.registry_snapshots()['PROJECT_REGISTRY']['entries'][ref['id']]['versions']['1']
    tx=engine.begin(); tx.refresh_derived_state(ref['id'],1,{'status':'STALE','stale':{'is_stale':True,'reasons':[{'code':'INPUT_CHANGED','message':'dependency changed','detected_at':'2026-09-27T05:05:00Z'}]}}); tx.commit()
    after=engine.registry_snapshots()['PROJECT_REGISTRY']['entries'][ref['id']]['versions']['1']
    assert before['decision_sha256']==after['decision_sha256']
    assert before['record_sha256']!=after['record_sha256']


def test_archive_clears_active(engine,P):
    ref=create_project(engine,P)
    tx=engine.begin(); tx.archive_object(ref['id']); tx.commit()
    assert engine.resolver().resolve(ref['id'],mode=ResolverMode.ACTIVE) is None
    assert engine.resolver().resolve(ref['id'],mode=ResolverMode.HEAD)['status']=='ARCHIVED'


def test_state_transition_fails_closed_when_gate_evidence_missing(root,P):
    e=StateEngine(root,clock=lambda:'2026-09-27T05:05:00Z')
    tx=e.begin()
    with pytest.raises(StateEngineError) as err: tx.transition_project_state('RESEARCH_INTAKE')
    assert err.value.code=='PROJECT_STATE_TRANSITION_DENIED'
    assert 'GATE_FAIL:BOOTSTRAP' in err.value.details['reason_codes']


def test_gate_authorized_state_transition_is_transactional(root):
    pack={'artifact_id':'RESEARCH_PACK_001','artifact_type':'RESEARCH_PACK','version':1,'sha256':'a'*64}
    e=StateEngine(root,artifacts=[pack],clock=lambda:'2026-09-27T05:05:00Z')
    tx=e.begin(); tx.transition_project_state('RESEARCH_INTAKE'); tx.commit()
    assert e.project_state=='RESEARCH_INTAKE'
    assert e.manifest_version==2
    assert e.gate_history()[-1]['gate_id']=='BOOTSTRAP'
    assert e.gate_history()[-1]['result']=='PASS'


def test_audit_log_is_append_only_transaction_history(engine,P):
    ref=create_project(engine,P)
    tx=engine.begin(); tx.create_version(ref['id'],base_version=1,patch={'working_title':'V2'}); tx.commit()
    log=engine.audit_log()
    assert [x['transaction_id'] for x in log]==['TX_000001','TX_000002']
    assert log[0]['actions'][0]['action_type']=='CREATE_OBJECT'
    assert log[1]['actions'][0]['action_type']=='CREATE_VERSION'

def test_expected_registry_version_checked_on_begin(engine,P):
    create_project(engine,P)
    with pytest.raises(ConcurrencyConflict) as e:
        engine.begin(expected_registry_versions={'PROJECT_REGISTRY':0})
    assert e.value.code=='REGISTRY_VERSION_CONFLICT'


def test_stale_version_cannot_be_promoted(engine,P):
    ref=create_project(engine,P)
    tx=engine.begin(); v2=tx.create_version(ref['id'],base_version=1,patch={'working_title':'v2'}); tx.commit()
    tx=engine.begin(); tx.refresh_derived_state(ref['id'],2,{'status':'STALE','stale':{'is_stale':True,'reasons':[{'code':'TEST_STALE','message':'stale','detected_at':'2026-09-27T05:05:00Z'}]}}); tx.commit()
    tx=engine.begin()
    with pytest.raises(StateEngineError) as e: tx.promote_active_version(ref['id'],v2['version'])
    assert e.value.code=='PROMOTION_TARGET_INELIGIBLE'
