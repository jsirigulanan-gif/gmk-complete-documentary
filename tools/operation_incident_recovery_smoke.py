#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_state import StateEngine
from gmk_operations import OperationRuntime, OperationExecutionResult
from gmk_incident.runtime import IncidentRuntime
from gmk_recovery import CheckpointRuntime

class Clock:
    def __init__(self):self.n=0
    def __call__(self):
        self.n+=1
        return f"2026-09-27T09:{self.n:02d}:00Z"

e=StateEngine(ROOT,clock=Clock())
t=e.begin();project=t.create_object('PROJECT',{
    'title':'GMK Build 007 Smoke','language':{'narration':'th-TH'},
    'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}}
});t.commit()

recovery=CheckpointRuntime(e)
cp=recovery.create_checkpoint(checkpoint_class='PRE_HIGH_RISK_OPERATION',reason='Before external publish smoke')
ops=OperationRuntime(e)
op=ops.plan(operation_type='PUBLISH',subject=project,provider='SMOKE',action='PUBLISH_DRAFT',input_fingerprint='smoke-001',idempotency_key='SMOKE:PUBLISH:001',human_confirmed=True,checkpoint_ref=cp)
result=ops.execute(op['operation_ref'],lambda _:OperationExecutionResult('SUCCEEDED','remote-smoke-id'))
assert result['workflow_state']=='SUCCEEDED'

t=e.begin();v2=t.create_version(project['id'],base_version=1,patch={'working_title':'temporary-change'});t.promote_active_version(project['id'],v2['version']);t.commit()
plan=recovery.build_restore_plan(cp);recovery.restore(plan,human_confirmed=True)
assert e.resolver().resolve(project['id'],mode='HEAD')['version']==2
assert e.resolver().resolve(project['id'],mode='ACTIVE')['version']==1
assert e.resolver().resolve(op['operation_ref']['id'],mode='ACTIVE')['workflow_state']=='SUCCEEDED'

inc=IncidentRuntime(e).open(incident_type='PROVIDER_OUTAGE',severity='CRITICAL',summary='Smoke containment',affected_scope={'type':'SYSTEM'},containment_actions=['FREEZE_MUTATIONS','BLOCK_EXTERNAL_OPERATIONS'])
assert e.safety_mode=='EMERGENCY_STOP'
inc=IncidentRuntime(e).transition(inc,'CONTAINED')
inc=IncidentRuntime(e).transition(inc,'RECOVERY_READY')
IncidentRuntime(e).transition(inc,'RESOLVED',verification_refs=[project])
assert e.safety_mode=='NORMAL'

print('PASS: idempotent Operation Runtime, preserved external truth across restore, Incident Safety Controller, and Checkpoint/Restore smoke passed.')
