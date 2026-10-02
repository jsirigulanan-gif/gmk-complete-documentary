"""Publish an actual locked-master render to the canonical render graph.

Streaming byte verification and full-file decode precede publication. Technical
success grants no Shot/Scene/Full-film QA and leaves PRODUCTION_RENDER in place.
"""
from pathlib import Path

from gmk_render import RenderRuntime
from gmk_production import ProductionLockRuntime

from .design_planning import _persist
from .edit import EditError, asset_file, fingerprint
from .final_production import _aref, _ref, _heads, master_file
from .preproduction import _tokens, _inspect
from .production import ProductionProject
from .production_bridge import _active
from .render import render_project
from .storage import atomic_json, digest


def _checked(project, expected_edit_sha256, expected_manifest_sha256):
    edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256)
    check = _inspect(project, edit, loaded); engine = loaded.engine
    if not check['ready'] or not check['lock_binding']['locked'] or engine.project_state != 'PRODUCTION_RENDER':
        raise EditError('ยืนยันแผนและล็อกการผลิตรุ่นปัจจุบันก่อนเรนเดอร์ขั้นผลิต')
    if engine.snapshot().safety_mode != 'NORMAL' or engine.derive_blockers(gate_id='RENDER'):
        raise EditError('ข้อมูลผลิตมีเหตุหรือผลตรวจที่ห้ามเรนเดอร์ ต้องแก้สาเหตุก่อน')
    ProductionLockRuntime(engine).assert_valid(check['lock_binding']['production_lock_ref'])
    master = next(a for a in _heads(engine.snapshot(), 'MASTER_VOICE')
                  if a.get('extensions', {}).get('project_final') and not a['extensions']['project_final'].get('retired'))
    path = master_file(ProductionProject(project), master)
    return edit, loaded, check, master, path


def render_production(project, *, expected_edit_sha256, expected_manifest_sha256, progress=None):
    with project._lock():
        edit, loaded, check, master, voice = _checked(project, expected_edit_sha256, expected_manifest_sha256)
        lockref = check['lock_binding']['production_lock_ref']; masterref = _aref(master)
        started_at = loaded.engine.now()
    result = render_project(project, progress=progress, _locked_master_path=voice,
                            _locked_master_sha256=master['audio']['sha256'], _publish_last=False)
    with project._lock():
        edit, loaded, check, current_master, _ = _checked(project, expected_edit_sha256, expected_manifest_sha256)
        if (check['lock_binding']['production_lock_ref'] != lockref or _aref(current_master) != masterref
                or result['edit_sha256'] != expected_edit_sha256
                or result['research_manifest_sha256'] != expected_manifest_sha256
                or not result['matches_current_edit']): raise EditError('ข้อมูลผลิตเปลี่ยนระหว่างเรนเดอร์ — เก็บไฟล์ไว้แต่ไม่ลงผลสำเร็จ')
        qa = result['technical_qa']
        if not qa['passed'] or not qa['full_decode_checked'] or qa['issues']:
            raise EditError('วิดีโอไม่ผ่านการตรวจไฟล์จริง — เก็บผลตรวจและไฟล์ไว้เพื่อแก้ไข')
        output_path = asset_file(project, result['registered']['preview.mp4'], 'exports')
        if digest(output_path)['sha256'] != qa['sha256']: raise EditError('วิดีโอเปลี่ยนหลังตรวจเทคนิค')
        engine = loaded.engine; runtime = RenderRuntime(engine)
        tag = {'project_render': {'input_sha256': check['review_binding']['input_sha256'], 'retired': False,
                                 'input_manifest_sha256': expected_manifest_sha256,
                                 'master_voice_ref': masterref, 'master_audio_sha256': master['audio']['sha256']}}
        profile = {'width': edit['width'], 'height': edit['height'], 'fps': edit['fps'], 'codec': 'h264', 'audio': 'aac'}
        adapter = {'config_id': 'GMK_EDITOR_FFMPEG', 'version': '1.0.0',
                   'sha256': digest(Path(__file__).with_name('render.py'))['sha256']}
        compiler = {'config_id': 'GMK_PROJECT_RENDER_COMPILER', 'version': '1.0.0', 'sha256': digest(Path(__file__))['sha256']}
        project_obj = next(o for o in _active(engine.snapshot()).values() if o['object_type'] == 'PROJECT')
        job = runtime.queue_final(production_lock_ref=lockref, scope_type='PROJECT', scope_target=_ref(project_obj),
            renderer_adapter=adapter, output_profile={'config_id': 'GMK_EDITOR_MASTER', 'version': '1.0.0', 'sha256': fingerprint(profile)},
            compiled_payload={'edit_sha256': expected_edit_sha256, 'production_lock': lockref,
                              'master_voice': masterref, 'settings': profile,
                              'timeline': check['timeline']['timeline'], 'execution': 'ACTUAL_LOCAL_FFMPEG'},
            transient_retry_limit=0, compiler=compiler, extensions=tag)
        tx = engine.begin(); running = tx.create_version(job['id'], base_version=job['version'], patch={'workflow_state': 'RUNNING'})
        tx.promote_active_version(running['id'], running['version'], confirm_locked_impact=True); tx.commit()
        current = engine.snapshot().objects[(running['id'], running['version'])]
        tx = engine.begin(); done = tx.create_version(running['id'], base_version=running['version'], patch={'workflow_state': 'SUCCEEDED'})
        tx.promote_active_version(done['id'], done['version'], confirm_locked_impact=True)
        output = tx.create_artifact('RENDER_OUTPUT', {'render_job_ref': done,
            'media_uri': 'gmk://project/'+result['registered']['preview.mp4']['path'], 'media_sha256': qa['sha256'], 'media_type': 'VIDEO',
            'technical': {'width': edit['width'], 'height': edit['height'], 'duration_seconds': qa['duration_seconds'],
                          'frame_rate': {'numerator': edit['fps'], 'denominator': 1}, 'codec': 'h264', 'container': 'mp4', 'audio_present': True},
            'render_key_sha256': current['extensions']['render_key_sha256'],
            'extensions': {**tag, 'local_technical_qa': qa, 'registered_output': result['registered']['preview.mp4']}},
            origin_refs=[done, lockref, masterref])
        manifest = tx.create_object('RENDER_MANIFEST', {'render_job_ref': done,
            'execution': {'attempt': 1, 'mode': 'EXECUTED', 'started_at': started_at, 'finished_at': engine.now()},
            'outcome': 'SUCCESS', 'inputs_snapshot_sha256': current['input_snapshot']['snapshot_sha256'], 'outputs': [output],
            'technical_validation': {'state': 'PASS'}, 'extensions': tag}, activate=True)
        tx.commit()
        # Recheck byte-bound inputs and outputs after staging, before a single durable publication.
        _checked(project, expected_edit_sha256, expected_manifest_sha256)
        asset_file(project, result['registered']['preview.mp4'], 'exports')
        _persist(project, engine); published = ProductionProject(project)._load()
        result.update(input_manifest_sha256=expected_manifest_sha256, research_manifest_sha256=published.manifest_sha256,
                      canonical_render={'production_lock_ref': lockref, 'master_voice_ref': masterref,
                                        'master_audio_sha256': master['audio']['sha256'], 'render_job_ref': done,
                                        'render_manifest_ref': manifest, 'render_output_ref': output},
                      production_state=engine.project_state, shot_qa='PENDING', scene_qa='PENDING', full_film_qa='PENDING')
        atomic_json(project.root/'last_render.json', result)
        return result


def canonical_render_current(project, render, state):
    """Read-only exact proof, used by workflow/export verification."""
    refs = render.get('canonical_render') or {}
    outputref = refs.get('render_output_ref') or {}; manifestref = refs.get('render_manifest_ref') or {}
    jobref = refs.get('render_job_ref') or {}
    output = state.artifacts.get((outputref.get('artifact_id'), outputref.get('version')))
    manifest = _active(state).get(manifestref.get('id')); job = _active(state).get(jobref.get('id'))
    entry = state.artifact_registry.entries.get(outputref.get('artifact_id'))
    if not (output and entry and entry.head_version == outputref['version'] and _aref(output) == outputref
            and manifest and _ref(manifest) == manifestref and manifest['outcome'] == 'SUCCESS'
            and job and _ref(job) == jobref and job['workflow_state'] == 'SUCCEEDED'
            and outputref in manifest['outputs'] and output['render_job_ref'] == jobref
            and job['production_lock'] == refs.get('production_lock_ref')
            and output.get('extensions', {}).get('registered_output') == render['registered']['preview.mp4']
            and output['media_sha256'] == render['technical_qa']['sha256']
            and output['extensions']['project_render']['master_voice_ref'] == refs.get('master_voice_ref')
            and output['extensions']['project_render']['master_audio_sha256'] == refs.get('master_audio_sha256')):
        return False
    if output['extensions']['project_render']['input_manifest_sha256'] != render.get('input_manifest_sha256'): return False
    from .preproduction import lock_binding_status
    lock = lock_binding_status(project, state)
    return lock['locked'] and lock['production_lock_ref'] == refs['production_lock_ref']
