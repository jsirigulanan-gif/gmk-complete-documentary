import pytest

from gmk_projects.edit import EditError
from gmk_projects.preproduction import (inspect_preproduction, prepare_review, decide_review, prepare_lock,
                                        decide_lock, reopen_preproduction, review_file)
from gmk_projects.production import ProductionProject
from gmk_projects.design_planning import prepare_design, decide_design, prepare_plans
from tests.build056.test_design_planning import locked, action
from tests.build054.test_coverage import covered
from tests.build053.test_media_bridge import footage
from tests.build049.test_edit_render import setup


def run(p, fn, **kwargs):
    check = inspect_preproduction(p)
    return fn(p, expected_edit_sha256=check['edit_sha256'], expected_manifest_sha256=check['manifest_sha256'], **kwargs)


@pytest.fixture
def planned(locked):
    p = locked[0]
    from tests.build052.test_workflow import brief
    brief(p)
    action(p, prepare_design); action(p, decide_design, decision='APPROVED', actor_id='Synthetic designer'); action(p, prepare_plans)
    return locked


def approve_plan(p):
    run(p, prepare_review); run(p, decide_review, decision='APPROVED', actor_id='Synthetic plan reviewer')
    return run(p, prepare_lock)


def lock_plan(p):
    approve_plan(p)
    return run(p, decide_lock, decision='APPROVED', actor_id='Synthetic production owner')


def test_review_and_production_lock_require_separate_exact_human_decisions(planned):
    p, session, *_ = planned
    before = ProductionProject(p)._load().manifest_sha256
    assert inspect_preproduction(p)['ready'] and ProductionProject(p)._load().manifest_sha256 == before
    with pytest.raises(EditError): run(p, prepare_lock)
    prepared = run(p, prepare_review)
    assert prepared['production_state'] == 'HTML_REVIEW' and prepared['review_binding']['current']
    assert not prepared['review_binding']['approved'] and not prepared['lock_binding']['locked']
    html = review_file(p, prepared['review_binding']['index']).read_text()
    assert '<audio controls' in html and 'SHA256' in html and 'ยังไม่ใช่' not in html
    assert run(p, prepare_review)['idempotent_replay']
    accepted = run(p, decide_review, decision='APPROVED', actor_id='Synthetic plan reviewer')
    assert accepted['production_state'] == 'HTML_APPROVED' and accepted['review_binding']['approved']
    prepared = run(p, prepare_lock)
    assert prepared['lock_binding']['current'] and not prepared['lock_binding']['locked']
    accepted = run(p, decide_lock, decision='APPROVED', actor_id='Synthetic production owner')
    assert accepted['production_state'] == 'PRODUCTION_RENDER' and accepted['lock_binding']['locked']
    status = ProductionProject(p).status()
    assert status['final_binding']['voice_locked'] and status['design_binding']['approved'] and status['plan_binding']['shot_plan_ready']
    assert run(p, decide_lock, decision='APPROVED', actor_id='Synthetic production owner')['idempotent_replay']
    loaded = ProductionProject(p)._load()
    assert loaded.engine.gates.evaluate_gate(loaded.engine.snapshot(), 'PRODUCTION_LOCK', loaded.engine.now()).result == 'PASS'
    assert not status['documentary_completed']


def test_rejection_reopening_keeps_files_and_requires_new_plan_and_lock_review(planned):
    p = planned[0]
    prepared = run(p, prepare_review); page = review_file(p, prepared['review_binding']['index'])
    rejected = run(p, decide_review, decision='REJECTED', actor_id='Synthetic reviewer')
    assert rejected['production_state'] == 'HTML_REVIEW' and rejected['review_binding']['decision'] == 'REJECTED'
    with pytest.raises(EditError): run(p, prepare_lock)
    with pytest.raises(EditError, match='มีผลตรวจแล้ว'): run(p, decide_review, decision='APPROVED', actor_id='Synthetic reviewer')
    assert run(p, decide_review, decision='REJECTED', actor_id='Synthetic reviewer')['idempotent_replay']
    run(p, reopen_preproduction); approve_plan(p)
    result = run(p, decide_lock, decision='REJECTED', actor_id='Synthetic owner')
    assert result['production_state'] == 'HTML_APPROVED' and result['lock_binding']['decision'] == 'REJECTED'
    assert not result['lock_binding']['locked']
    with pytest.raises(EditError): run(p, decide_lock, decision='APPROVED', actor_id='Synthetic owner')
    run(p, reopen_preproduction)
    assert page.exists() and not inspect_preproduction(p)['review_binding']['approved']
    assert ProductionProject(p).status()['final_binding']['voice_locked']


def test_changed_review_bytes_and_stale_tokens_never_grant_approval(planned):
    p, session, *_ = planned
    prepared = run(p, prepare_review); page = review_file(p, prepared['review_binding']['index'])
    original = page.read_bytes(); page.write_bytes(b'Changed review')
    before = ProductionProject(p)._load().manifest_sha256
    assert not inspect_preproduction(p)['review_binding']['current']
    with pytest.raises(EditError): run(p, decide_review, decision='APPROVED', actor_id='Synthetic reviewer')
    assert ProductionProject(p)._load().manifest_sha256 == before
    page.write_bytes(original)
    edit = session.load(); edit['music_gain'] = .11; session.save(edit, expected_revision=edit['revision'])
    with pytest.raises(EditError, match='เปลี่ยนหลังเปิดตรวจ'):
        decide_review(p, expected_edit_sha256=prepared['edit_sha256'], expected_manifest_sha256=prepared['manifest_sha256'],
                      decision='APPROVED', actor_id='Synthetic reviewer')
    assert not ProductionProject(p).status()['review_binding']['current']


def test_failed_lock_staging_and_foreign_records_leave_core_unchanged(planned, monkeypatch):
    from gmk_production import ProductionLockRuntime
    from gmk_runtime.persistence import RuntimeStore
    p = planned[0]; approve_plan(p); before = ProductionProject(p)._load().manifest_sha256
    original = ProductionLockRuntime.create_project_lock
    def fail(*args, **kwargs): raise EditError('Simulated final lock failure')
    monkeypatch.setattr(ProductionLockRuntime, 'create_project_lock', fail)
    with pytest.raises(EditError, match='Simulated'): run(p, decide_lock, decision='APPROVED', actor_id='Synthetic owner')
    assert ProductionProject(p)._load().manifest_sha256 == before
    assert not inspect_preproduction(p)['lock_binding']['locked']
    monkeypatch.setattr(ProductionLockRuntime, 'create_project_lock', original)
    result = run(p, decide_lock, decision='APPROVED', actor_id='Synthetic owner')
    loaded = ProductionProject(p)._load(); lock = result['lock_binding']['production_lock_ref']
    obj = loaded.engine.snapshot().artifacts[(lock['artifact_id'], lock['version'])]
    payload = {key: obj[key] for key in ('scope', 'system', 'scene_locks', 'shots', 'layers', 'cues', 'approvals', 'dependency_snapshot_sha256')}
    tx = loaded.engine.begin(); tx.create_artifact('PRODUCTION_LOCK_MANIFEST', payload); tx.commit()
    RuntimeStore(loaded.engine.root, ProductionProject(p).workspace).persist(loaded.engine)
    before = ProductionProject(p)._load().manifest_sha256
    assert not inspect_preproduction(p)['ready']
    with pytest.raises(EditError): run(p, reopen_preproduction)
    assert ProductionProject(p)._load().manifest_sha256 == before


def test_locked_render_consumes_actual_master_and_records_real_output_without_qa(planned, monkeypatch):
    from gmk_projects.production_render import render_production, canonical_render_current
    from gmk_projects import production_render
    from gmk_projects.workflow import workflow_status, FILM_CHECKS
    from gmk_projects.render import approve_editorial_review, export_delivery
    from gmk_projects.delivery import verify_delivery
    from gmk_projects.final_production import _heads
    from gmk_projects.storage import digest
    p = planned[0]; lock_plan(p); original = production_render.render_project; observed = []
    def capture(*args, **kwargs):
        observed.append(digest(kwargs['_locked_master_path'])['sha256'])
        return original(*args, **kwargs)
    monkeypatch.setattr(production_render, 'render_project', capture)
    result = run(p, render_production)
    loaded = ProductionProject(p)._load(); state = loaded.engine.snapshot()
    assert result['production_state'] == 'PRODUCTION_RENDER' and result['shot_qa'] == 'PENDING'
    assert result['canonical_render']['master_audio_sha256'] == observed[0]
    assert canonical_render_current(p, result, state)
    assert loaded.engine.gates.evaluate_gate(state, 'RENDER', loaded.engine.now()).result == 'PASS'
    assert loaded.engine.gates.evaluate_gate(state, 'SHOT_QA', loaded.engine.now()).result == 'FAIL'
    assert len(_heads(state, 'RENDER_OUTPUT')) == 1 and not result['documentary_completed']
    assert workflow_status(p)['next_action'] == 'FILM_QA'
    approve_editorial_review(p, expected_master_sha256=result['technical_qa']['sha256'], checklist={k: True for k in FILM_CHECKS})
    export_delivery(p); assert verify_delivery(p)['local_package_verified']
    assert workflow_status(p)['next_action'] == 'DRIVE'
    run(p, reopen_preproduction)
    assert not canonical_render_current(p, result, ProductionProject(p)._load().engine.snapshot())
    renewed = lock_plan(p)
    assert renewed['lock_binding']['production_lock_ref']['artifact_id'] == result['canonical_render']['production_lock_ref']['artifact_id']
    assert renewed['lock_binding']['production_lock_ref']['version'] > result['canonical_render']['production_lock_ref']['version']


def test_edit_during_production_render_never_publishes_canonical_success(planned, monkeypatch):
    from gmk_projects.production_render import render_production
    from gmk_projects import production_render
    from gmk_projects.final_production import _heads
    p, session, *_ = planned; lock_plan(p); before = ProductionProject(p)._load().manifest_sha256
    original = production_render.render_project
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        edit = session.load(); edit['music_gain'] = .314; session.save(edit, expected_revision=edit['revision'])
        return result
    monkeypatch.setattr(production_render, 'render_project', change)
    with pytest.raises(EditError, match='เปลี่ยนหลังเปิดตรวจ'): run(p, render_production)
    assert ProductionProject(p)._load().manifest_sha256 == before
    assert not _heads(ProductionProject(p)._load().engine.snapshot(), 'RENDER_OUTPUT')
    assert not (p.root/'last_render.json').exists()
    assert list((p.root/'renders').glob('*/preview.mp4'))


def test_changed_consumed_master_copy_is_rejected_before_publication(planned, monkeypatch):
    from pathlib import Path
    from gmk_projects.production_render import render_production
    from gmk_projects import render
    from gmk_projects.final_production import _heads
    p = planned[0]; lock_plan(p); before = ProductionProject(p)._load().manifest_sha256
    original = render.shutil.copyfile
    def corrupt(source, destination, *args, **kwargs):
        result = original(source, destination, *args, **kwargs)
        if Path(destination).name == 'voice.wav':
            target = Path(destination); data = target.read_bytes(); target.write_bytes(data[:-1]+bytes([data[-1] ^ 1]))
        return result
    monkeypatch.setattr(render.shutil, 'copyfile', corrupt)
    with pytest.raises(EditError, match='เสียงรวมที่ใช้เรนเดอร์'): run(p, render_production)
    assert ProductionProject(p)._load().manifest_sha256 == before
    assert not _heads(ProductionProject(p)._load().engine.snapshot(), 'RENDER_OUTPUT')
    assert not (p.root/'last_render.json').exists()


def test_draft_pointer_cannot_waive_current_research_with_an_input_manifest_field(setup, tmp_path):
    from gmk_projects.intake import import_research
    from gmk_projects.render import render_project, approve_editorial_review, export_delivery
    from gmk_projects.storage import atomic_json
    p = setup[0]; result = render_project(p); original_manifest = result['research_manifest_sha256']
    source = tmp_path/'new-research.txt'; source.write_text('New research\nCLAIM: An additional assertion needs review.')
    import_research(p, source)
    result.update(research_manifest_sha256=ProductionProject(p)._load().manifest_sha256, input_manifest_sha256=original_manifest)
    atomic_json(p.root/'last_render.json', result)
    approve_editorial_review(p, expected_master_sha256=result['technical_qa']['sha256'])
    with pytest.raises(EditError, match='รีเสิร์ช'): export_delivery(p)
