import pytest
from gmk_production import ProductionLockRuntime
from gmk_render import RenderRuntime, RenderProduct, TransientRenderError
from gmk_qa import QARuntime
from gmk_state.errors import StateEngineError

class Adapter:
    def __init__(self, transient=0): self.calls=0; self.transient=transient
    def render(self,payload,snapshot,*,attempt):
        self.calls+=1
        if self.calls<=self.transient: raise TransientRenderError('temporary')
        return RenderProduct('gmk://renders/test.mp4',b'rendered-bytes',technical={'width':1920,'height':1080,'duration_seconds':5.0,'codec':'h264'})

def make_lock(engine,ready):
    return ProductionLockRuntime(engine).create_scene_lock(voice_lock_ref=ready['voice_lock'],design_dna_ref=ready['dna'],scene_plan_ref=ready['plan'],scene_preview_ref=ready['preview'])

def test_lock_render_and_qa_happy_path(engine,ready):
    lock=make_lock(engine,ready)
    rr=RenderRuntime(engine); job=rr.queue_final(production_lock_ref=lock,scope_target=ready['scene'])
    out=rr.execute(job,Adapter())
    assert out['failed'] is False and out['cache_hit'] is False
    qa=QARuntime(engine).evaluate(report_type='SHOT_QA',scope=ready['shot'],observed_artifact=out['output_ref'],findings=[])
    assert qa['result']=='PASS'
    baseline=QARuntime(engine).create_baseline(scope=ready['shot'],production_lock=lock,render_manifest_ref=out['manifest_ref'],qa_report_refs=[qa['report_ref']],output_refs=[out['output_ref']])
    reg=QARuntime(engine).regression_compare(baseline_ref=baseline,candidate_output_ref=out['output_ref'],expected_changed_scope=['SHOT'],observed_changed_scope=['SHOT'])
    assert reg['artifact_type']=='REGRESSION_COMPARE'

def test_transient_retry_is_bounded_and_cache_reuses(engine,ready):
    lock=make_lock(engine,ready); rr=RenderRuntime(engine)
    job=rr.queue_final(production_lock_ref=lock,scope_target=ready['scene'])
    a=Adapter(transient=2); first=rr.execute(job,a)
    assert a.calls==3 and first['failed'] is False
    job2=rr.queue_final(production_lock_ref=lock,scope_target=ready['scene'])
    b=Adapter(); second=rr.execute(job2,b)
    assert second['cache_hit'] is True and b.calls==0

def test_qa_failure_root_cause_and_auto_repair_cap(engine,ready):
    lock=make_lock(engine,ready); rr=RenderRuntime(engine); job=rr.queue_final(production_lock_ref=lock,scope_target=ready['scene']); out=rr.execute(job,Adapter())
    qa=QARuntime(engine).evaluate(report_type='SHOT_QA',scope=ready['shot'],observed_artifact=out['output_ref'],findings=[{'severity':'MAJOR','code':'CUE_EARLY_REVEAL','description':'too early','root_cause':{'state':'IDENTIFIED','category':'CUE_TIMING'}}])
    assert qa['result']=='FAIL'
    runtime=QARuntime(engine); issue=qa['issue_refs'][0]
    runtime.plan_repair(issue,proposed_changes=[{'path':'/timing'}],required_retests=['SHOT_QA'],auto=True)
    runtime.plan_repair(issue,proposed_changes=[{'path':'/timing'}],required_retests=['SHOT_QA'],auto=True)
    with pytest.raises(StateEngineError) as e: runtime.plan_repair(issue,proposed_changes=[{'path':'/timing'}],auto=True)
    assert e.value.code=='AUTO_REPAIR_LIMIT_EXCEEDED'

def test_final_render_rejects_invalidated_production_lock(engine,ready):
    lock=make_lock(engine,ready)
    tx=engine.begin();v2=tx.create_version(ready['shot']['id'],base_version=ready['shot']['version'],patch={'viewer_takeaway':'Changed after lock.'});tx.promote_active_version(ready['shot']['id'],v2['version'],confirm_locked_impact=True);tx.commit()
    rr=RenderRuntime(engine)
    with pytest.raises(StateEngineError) as e:
        rr.queue_final(production_lock_ref=lock,scope_target=ready['scene'])
    assert e.value.code=='PRODUCTION_LOCK_STALE'
