import pytest
from gmk_operations import OperationRuntime, OperationExecutionResult, ExternalStateUnknown
from gmk_recovery import CheckpointRuntime
from gmk_state import StateEngineError


def test_idempotent_success_executes_external_side_effect_once(engine,project):
    ops=OperationRuntime(engine);calls=[]
    planned=ops.plan(operation_type='UPLOAD',subject=project,provider='TEST',action='UPLOAD_MASTER',input_fingerprint='abc',idempotency_key='UPLOAD:PROJECT:abc')
    def exec_once(op):
        calls.append(op['id']);return OperationExecutionResult('SUCCEEDED','remote-id-1')
    done=ops.execute(planned['operation_ref'],exec_once)
    replay=ops.plan(operation_type='UPLOAD',subject=project,provider='TEST',action='UPLOAD_MASTER',input_fingerprint='abc',idempotency_key='UPLOAD:PROJECT:abc')
    done2=ops.execute(replay['operation_ref'],exec_once)
    assert done['workflow_state']=='SUCCEEDED'
    assert replay['idempotent_replay'] is True and done2['idempotent_replay'] is True
    assert len(calls)==1


def test_idempotency_collision_fails(engine,project):
    ops=OperationRuntime(engine)
    ops.plan(operation_type='UPLOAD',subject=project,provider='A',action='UPLOAD',input_fingerprint='x',idempotency_key='K')
    with pytest.raises(StateEngineError) as exc:
        ops.plan(operation_type='UPLOAD',subject=project,provider='B',action='UPLOAD_OTHER',input_fingerprint='y',idempotency_key='K')
    assert exc.value.code=='OPERATION_IDEMPOTENCY_COLLISION'


def test_unknown_external_state_requires_reconciliation(engine,project):
    ops=OperationRuntime(engine)
    p=ops.plan(operation_type='UPLOAD',subject=project,provider='TEST',action='UPLOAD',input_fingerprint='x',idempotency_key='UNKNOWN')
    out=ops.execute(p['operation_ref'],lambda op: (_ for _ in ()).throw(ExternalStateUnknown('connection dropped after send')))
    assert out['workflow_state']=='UNKNOWN_EXTERNAL_STATE'
    with pytest.raises(StateEngineError) as exc:ops.execute(out['operation_ref'],lambda op: OperationExecutionResult('SUCCEEDED'))
    assert exc.value.code=='OPERATION_RECONCILIATION_REQUIRED'
    r=ops.reconcile(out['operation_ref'],outcome='SUCCEEDED',evidence='provider lookup confirmed remote object')
    assert r['workflow_state']=='SUCCEEDED'


def test_publish_requires_human_and_verified_checkpoint(engine,project):
    ops=OperationRuntime(engine)
    with pytest.raises(StateEngineError) as exc:
        ops.plan(operation_type='PUBLISH',subject=project,provider='TEST',action='PUBLISH',input_fingerprint='x',idempotency_key='PUB')
    assert exc.value.code=='DESTRUCTIVE_OPERATION_NOT_AUTHORIZED'
    cp=CheckpointRuntime(engine).create_checkpoint(checkpoint_class='PRE_HIGH_RISK_OPERATION',reason='Before publish')
    p=ops.plan(operation_type='PUBLISH',subject=project,provider='TEST',action='PUBLISH',input_fingerprint='x',idempotency_key='PUB',human_confirmed=True,checkpoint_ref=cp)
    assert p['workflow_state']=='PLANNED'


def test_restart_running_operation_becomes_unknown(root,engine,project,tmp_path):
    from gmk_runtime import RuntimeStore, ColdStartLoader
    ops=OperationRuntime(engine)
    p=ops.plan(operation_type='UPLOAD',subject=project,provider='TEST',action='UPLOAD',input_fingerprint='restart',idempotency_key='RESTART')
    cur=engine.resolver().resolve(p['operation_ref']['id'],mode='HEAD')
    tx=engine.begin();nv=tx.create_version(cur['id'],base_version=cur['version'],patch={'workflow_state':'RUNNING','attempts':[{'attempt':1,'started_at':engine.now()}]});tx.promote_active_version(cur['id'],nv['version']);tx.commit()
    ws=tmp_path/'ws';RuntimeStore(root,ws).persist(engine)
    loaded=ColdStartLoader(root,ws).load()
    ops2=OperationRuntime(loaded.engine);changed=ops2.reconcile_inflight_after_restart()
    assert len(changed)==1
    head=loaded.engine.resolver().resolve(p['operation_ref']['id'],mode='HEAD')
    assert head['workflow_state']=='UNKNOWN_EXTERNAL_STATE'
