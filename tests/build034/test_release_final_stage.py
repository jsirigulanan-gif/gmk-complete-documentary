from pathlib import Path
import json
import pytest

from gmk_release import DeliveryStageRuntime, ReleaseFinalStageRuntime, ReleaseFinalStageError
from gmk_release.runtime import ReleaseRuntime
from gmk_qa import FullFilmQAStageRuntime
from gmk_runtime.cold_start import ColdStartLoader
from tests.build032.test_full_film_qa_stage import _scene_qa_passed, _plan as _ff_plan
from tests.build033.test_delivery_stage import _patch_profile, _prepare_plan, _approve

ROOT=Path(__file__).resolve().parents[2]


def _delivery_ready(tmp_path,monkeypatch):
    _patch_profile(monkeypatch)
    ws=_scene_qa_passed(tmp_path)
    ff=FullFilmQAStageRuntime(ROOT,ws).run(_ff_plan(batch='B034_FF'))
    assert ff.project_state=='FULL_FILM_QA_PASSED'
    ds=DeliveryStageRuntime(ROOT,ws)
    ds.prepare(_prepare_plan(batch='B034_DELIVERY'))
    dec=ds.decide(_approve())
    assert dec.project_state=='DELIVERY_READY'
    return ws


def _plan(tmp_path,batch='B034_RELEASE',label='v1'):
    return {'batch_id':batch,'mode':'LOCAL_EXPORT','destination_dir':str(tmp_path/'published'),'release_label':label}


def test_release_finalize_local_export_completes_project(tmp_path,monkeypatch):
    ws=_delivery_ready(tmp_path,monkeypatch)
    out=ReleaseFinalStageRuntime(ROOT,ws).run(_plan(tmp_path))
    assert out.project_state=='PROJECT_COMPLETED'
    assert Path(out.receipt_path).is_file()
    receipt=json.loads(Path(out.receipt_path).read_text(encoding='utf-8'))
    assert receipt['mode']=='LOCAL_EXPORT' and receipt['release_label']=='v1'
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    rel=state.objects[(out.release_ref['id'],out.release_ref['version'])]
    cp=state.objects[(out.final_checkpoint_ref['id'],out.final_checkpoint_ref['version'])]
    op=state.objects[(out.operation_ref['id'],out.operation_ref['version'])]
    assert rel['state']=='RELEASED'
    assert cp['checkpoint_class']=='FINAL_PROJECT' and cp['integrity_summary']=='PASS'
    assert op['workflow_state']=='SUCCEEDED' and op['operation_type']=='PUBLISH'


def test_release_finalize_replay_does_not_duplicate_release_or_checkpoint(tmp_path,monkeypatch):
    ws=_delivery_ready(tmp_path,monkeypatch);rt=ReleaseFinalStageRuntime(ROOT,ws);plan=_plan(tmp_path)
    first=rt.run(plan);second=rt.run(plan)
    assert second.idempotent_replay is True
    assert second.release_ref==first.release_ref and second.final_checkpoint_ref==first.final_checkpoint_ref
    state=ColdStartLoader(ROOT,ws).load().engine.snapshot()
    releases=[o for o in state.objects.values() if o.get('object_type')=='RELEASE' and o.get('state')=='RELEASED']
    finals=[o for o in state.objects.values() if o.get('object_type')=='CHECKPOINT' and o.get('checkpoint_class')=='FINAL_PROJECT']
    assert len(releases)==1 and len(finals)==1


def test_release_finalize_requires_exact_human_delivery_approval(tmp_path,monkeypatch):
    _patch_profile(monkeypatch);ws=_scene_qa_passed(tmp_path)
    FullFilmQAStageRuntime(ROOT,ws).run(_ff_plan(batch='B034_NOAPP_FF'))
    DeliveryStageRuntime(ROOT,ws).prepare(_prepare_plan(batch='B034_NOAPP_DELIVERY'))
    with pytest.raises(ReleaseFinalStageError,match='RELEASE_STATE_INVALID'):
        ReleaseFinalStageRuntime(ROOT,ws).run(_plan(tmp_path,batch='B034_NOAPP'))


def test_release_finalize_batch_collision_rejected(tmp_path,monkeypatch):
    ws=_delivery_ready(tmp_path,monkeypatch);rt=ReleaseFinalStageRuntime(ROOT,ws)
    rt.run(_plan(tmp_path,batch='B034_COLLIDE',label='v1'))
    with pytest.raises(ReleaseFinalStageError,match='RELEASE_BATCH_ID_COLLISION'):
        rt.run(_plan(tmp_path,batch='B034_COLLIDE',label='v2'))


def test_release_runtime_publish_and_finalize_are_idempotent_after_completion(tmp_path,monkeypatch):
    ws=_delivery_ready(tmp_path,monkeypatch);rt=ReleaseFinalStageRuntime(ROOT,ws)
    out=rt.run(_plan(tmp_path,batch='B034_IDEM'))
    eng=ColdStartLoader(ROOT,ws).load().engine;state=eng.snapshot()
    pkg=[a for a in state.artifacts.values() if a.get('artifact_type')=='DELIVERY_REVIEW_PACKAGE'][-1]
    cand=rt._candidate(pkg);rel=ReleaseRuntime(eng,workspace=ws)
    from gmk_operations import OperationExecutionResult
    pub=rel.publish(cand,executor=lambda _:OperationExecutionResult('SUCCEEDED','should-not-run'),provider='GMK_LOCAL_EXPORT',destination=str((tmp_path/'published').resolve()),release_label='v1',human_confirmed=True)
    assert pub.release_ref==out.release_ref
    final=rel.finalize_project(pub.release_ref,important_artifact_refs=[cand['delivery_package'],{'artifact_id':pkg['artifact_id'],'artifact_type':pkg['artifact_type'],'version':pkg['version'],'sha256':pkg['sha256']}])
    assert final['project_state']=='PROJECT_COMPLETED' and final['final_checkpoint_ref']==out.final_checkpoint_ref
