import pytest
from gmk_incident.runtime import IncidentRuntime
from gmk_incident import IncidentSafetyController
from gmk_operations import OperationRuntime
from gmk_runtime import RuntimeStore, ColdStartLoader
from gmk_state import StateEngineError


def test_critical_containment_derives_emergency_stop_and_blocks_normal_mutation(engine,project):
    incidents=IncidentRuntime(engine)
    ref=incidents.open(incident_type='REGISTRY_INTEGRITY',severity='CRITICAL',summary='Registry corruption suspected',affected_scope={'type':'PROJECT'},containment_actions=['FREEZE_MUTATIONS','BLOCK_EXTERNAL_OPERATIONS'])
    assert IncidentSafetyController(engine).mode=='EMERGENCY_STOP'
    assert engine.safety_mode=='EMERGENCY_STOP'
    with pytest.raises(StateEngineError) as exc:engine.begin()
    assert exc.value.code=='INCIDENT_SAFETY_MODE_ACTIVE'
    with pytest.raises(StateEngineError) as exc:
        OperationRuntime(engine).plan(operation_type='UPLOAD',subject=project,provider='TEST',action='UPLOAD',input_fingerprint='x',idempotency_key='blocked')
    assert exc.value.code=='INCIDENT_EXTERNAL_OPERATION_BLOCKED'


def test_incident_resolution_requires_verification_and_releases_safety(engine,project):
    rt=IncidentRuntime(engine)
    ref=rt.open(incident_type='PROVIDER_OUTAGE',severity='CRITICAL',summary='Provider unstable',affected_scope={'type':'SYSTEM'},containment_actions=['BLOCK_EXTERNAL_OPERATIONS'])
    ref=rt.transition(ref,'CONTAINED')
    ref=rt.transition(ref,'RECOVERY_READY')
    with pytest.raises(StateEngineError) as exc:rt.transition(ref,'RESOLVED')
    assert exc.value.code=='INCIDENT_RESOLVED_WITHOUT_VERIFICATION'
    ref=rt.transition(ref,'RESOLVED',verification_refs=[project])
    assert engine.safety_mode=='NORMAL'
    tx=engine.begin();tx.create_version(project['id'],base_version=1,patch={'working_title':'Safety released'});tx.commit()


def test_cold_start_preserves_incident_derived_safety(root,engine,project,tmp_path):
    IncidentRuntime(engine).open(incident_type='REGISTRY_INTEGRITY',severity='CRITICAL',summary='Freeze',affected_scope={'type':'PROJECT'},containment_actions=['FREEZE_MUTATIONS'])
    assert engine.safety_mode=='READ_ONLY'
    ws=tmp_path/'ws';RuntimeStore(root,ws).persist(engine)
    loaded=ColdStartLoader(root,ws).load()
    assert loaded.engine.safety_mode=='READ_ONLY'
