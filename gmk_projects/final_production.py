"""Connect the reviewed edit to final script, actual master voice and human review.

Uses the existing frozen objects and StateEngine gates. It neither calls a
provider nor turns per-scene listening checks into a master-voice approval.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import wave

from gmk_narrative.script import ScriptRuntime
from gmk_narrative.tts import TTSRuntime
from gmk_runtime.persistence import RuntimeStore

from .coverage import (_inspect as coverage_inspect, _reports, _write_assessment,
                       coverage_binding_status, coverage_input, retire_coverage)
from .edit import EditError, EditSession, asset_file, fingerprint, probe
from .media_bridge import _pools, media_binding_status
from .production import ProductionProject, RUNTIME_ROOT
from .production_bridge import _active, _spine, binding_status as story_binding
from .render import _ffmpeg, _run
from .research import _research_review
from .storage import StorageError, atomic_json, digest, relative_path


ARTIFACTS = {'VOICEOVER_SCRIPT_FINAL', 'PRONUNCIATION_DICTIONARY', 'TTS_READY_SCRIPT',
             'MASTER_VOICE', 'VOICE_TIMING_MAP', 'VOICE_LOCK_MANIFEST', 'VOICE_REVIEW_PACKAGE'}
STATES = {'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED'}
READABLE_STATES = STATES | {'DESIGN_DNA_APPROVED', 'SCENE_PLAN_READY', 'SHOT_PLAN_READY'}


def _ref(obj):
    return {'id': obj['id'], 'version': obj['version']}


def _aref(obj):
    return {k: obj[k] for k in ('artifact_id', 'artifact_type', 'version', 'sha256')}


def _heads(state, kind=None):
    return [state.artifacts[(aid, e.head_version)] for aid, e in state.artifact_registry.entries.items()
            if kind is None or e.artifact_type == kind]


def _tag(obj):
    return obj.get('extensions', {}).get('project_final', {})


def owns_final(state):
    artifacts = [a for a in _heads(state) if a['artifact_type'] in ARTIFACTS]
    return (bool(artifacts) and all(_tag(a) for a in artifacts)
            and any(a['artifact_type'] == 'VOICE_LOCK_MANIFEST' and not _tag(a).get('retired') for a in artifacts)
            and all(_tag(o) for o in _active(state).values()
                    if o['object_type'] in {'VOICE_PROFILE', 'VOICE_BLOCK'}
                    or (o['object_type'] == 'APPROVAL' and o.get('approval_class') == 'VOICE')))


def retire_final(tx):
    """Retire only our prior plans/decisions during an explicit upstream revision."""
    from .design_planning import retire_design
    retire_design(tx)
    for obj in _active(tx.staged).values():
        if _tag(obj) and obj['object_type'] in {'VOICE_PROFILE', 'VOICE_BLOCK', 'APPROVAL'}:
            tx.archive_object(obj['id'])
    for art in _heads(tx.staged):
        if art['artifact_type'] in ARTIFACTS and _tag(art) and not _tag(art).get('retired'):
            tx.create_artifact_version(art['artifact_id'], base_version=art['version'],
                payload_patch={'extensions': {'project_final': {'retired': True}}})


def final_input(edit, state):
    value = coverage_input(edit, state)
    value.pop('receipts')  # Canonical ref refresh alone does not change reviewed editorial content.
    return {**value, 'language': (edit.get('brief') or {}).get('language') or 'th-TH'}


def master_file(production, master):
    uri = master['audio']['uri']; prefix = 'gmk://workspace/'
    if not uri.startswith(prefix): raise EditError('ตำแหน่งเสียงรวมไม่ใช่คลังผลิตของโปรเจกต์')
    path = production.workspace / relative_path(uri[len(prefix):])
    if path.is_symlink() or not path.resolve().is_relative_to(production.workspace) or not path.is_file():
        raise EditError('ไฟล์เสียงรวมหายหรืออยู่นอกโปรเจกต์')
    if digest(path)['sha256'] != master['audio']['sha256']: raise EditError('ไฟล์เสียงรวมถูกแก้หลังเตรียม')
    return path


def final_binding_status(project, state, *, edit=None, story_status=None, media_status=None, coverage_status=None):
    locks = [a for a in _heads(state, 'VOICE_LOCK_MANIFEST') if _tag(a)]
    lock = locks[0] if len(locks) == 1 else None
    if edit is None:
        try: edit = json.loads((project.root/'edit.json').read_text(encoding='utf-8'))
        except (OSError, ValueError): edit = None
    current = bool(lock and edit and not _tag(lock).get('retired')
                   and owns_final(state)
                   and _tag(lock).get('input_sha256') == fingerprint(final_input(edit, state))
                   and state.project_state in READABLE_STATES
                   and (story_status if story_status is not None else story_binding(project, state))['current']
                   and (media_status if media_status is not None else media_binding_status(project, state, edit=edit))['current']
                   and (coverage_status if coverage_status is not None else coverage_binding_status(project, state, edit=edit, media_status=media_status))['ready'])
    master = None
    if lock:
        ref = lock['master_voice']; master = state.artifacts.get((ref['artifact_id'], ref['version']))
        for key in ('master_voice', 'timing_map', 'voiceover_script', 'tts_script', 'pronunciation_dictionary'):
            ref = lock[key]; head = state.artifact_registry.entries.get(ref['artifact_id'])
            if not head or head.head_version != ref['version']: current = False
        live = _active(state)
        for ref in [lock['voice_profile_ref'], *lock['voice_blocks']]:
            obj = live.get(ref['id'])
            if (not obj or obj['version'] != ref['version'] or obj.get('stale', {}).get('is_stale')
                    or obj['status'] in {'STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED'}): current = False
    if current:
        try: master_file(ProductionProject(project), master)
        except (OSError, StorageError, KeyError): current = False
    reviews = [a for a in _heads(state, 'VOICE_REVIEW_PACKAGE') if _tag(a) and not _tag(a).get('retired')
               and a.get('voice_lock') == (_aref(lock) if lock else None)]
    review = reviews[0] if len(reviews) == 1 else None
    approvals = [o for o in _active(state).values() if o['object_type'] == 'APPROVAL' and _tag(o)
                 and o.get('target') == (_aref(lock) if lock else None)]
    if not review or any(o.get('review_context') != _aref(review) or o.get('stale', {}).get('is_stale')
                         or o['status'] in {'STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED'} for o in approvals):
        current = False
    approved = bool(current and state.project_state in READABLE_STATES - {'SCRIPT_READY', 'TTS_READY'}
                    and any(a['decision'] == 'APPROVED' for a in approvals)
                    and not any(a['decision'] == 'REJECTED' for a in approvals))
    rejected = bool(current and any(a['decision'] == 'REJECTED' for a in approvals))
    return {'connected': bool(lock), 'current': current, 'prepared': current, 'voice_locked': approved,
            'voice_decision': 'REJECTED' if rejected else 'APPROVED' if approved else None,
            'voice_lock_ref': _aref(lock) if lock else None, 'master_voice_ref': _aref(master) if master else None,
            'master_audio_sha256': master['audio']['sha256'] if master else None,
            'documentary_completed': False,
            'reason': 'บทและเสียงรวมตรงงานปัจจุบัน — ยืนยันเสียงขั้นผลิตแล้ว' if approved else
                      'เสียงรวมยังต้องแก้ — กดกลับไปแก้บทหรือเสียง แล้วตรวจและเตรียมใหม่' if rejected else
                      'บทและเสียงรวมตรงงานปัจจุบัน — รอฟังเสียงรวมและยืนยัน' if current else
                      'ต้องเตรียมบทและเสียงรวมจากภาพและเสียงที่ตรวจแล้วรุ่นปัจจุบัน'}


def _inspect(project, edit, loaded):
    state = loaded.engine.snapshot(); binding = final_binding_status(project, state, edit=edit)
    coverage = coverage_binding_status(project, state, edit=edit)
    issues = []
    if not coverage['ready'] or not coverage['selection_closed']:
        issues.append('ตรวจภาพให้ผ่านและบันทึกเหตุผลเลือกใช้คลังภาพก่อนเตรียมบทสุดท้าย')
    if state.project_state != 'VISUAL_COVERAGE_READY' and not binding['current']:
        issues.append('แก้หรือเชื่อมงานภาพรุ่นปัจจุบันก่อนเตรียมบทและเสียงขั้นผลิตใหม่')
    foreign = [a for a in _heads(state) if a['artifact_type'] in ARTIFACTS and not _tag(a)]
    foreign += [o for o in _active(state).values() if not _tag(o)
                and (o['object_type'] in {'VOICE_BLOCK', 'VOICE_PROFILE'}
                     or (o['object_type'] == 'APPROVAL' and o.get('approval_class') == 'VOICE'))]
    if foreign: issues.append('มีบทหรือเสียงขั้นผลิตจากระบบอื่น ต้องย้ายข้อมูลอย่างชัดเจนก่อน')
    plan = EditSession(project).preflight(edit, research=_research_review(project))
    issues += [i['detail'] for i in plan['issues']]
    issues += [i for s in plan['script_review']['scenes'] for i in s['issues']]
    scenes = []
    mapping = story_binding(project, state).get('scene_map', {})
    for scene in edit['scenes']:
        if not scene['included']: continue
        try:
            text = ScriptRuntime._validate_text(scene['id'], scene['narration'])
            if text != scene['narration']: raise EditError('ลบช่องว่างต้น/ท้ายบทแล้วตรวจเสียงใหม่ก่อนยืนยันบท')
            beat_ref = mapping[scene['id']]['beat_ref']; beat = state.objects[(beat_ref['id'], beat_ref['version'])]
            mode = ScriptRuntime._required_mode(beat, state)
            timing = next(s for s in plan['timeline'] if s['scene_id'] == scene['id'])
            scenes.append({'scene_id': scene['id'], 'title': scene['title'], 'narration': text, 'language_mode': mode,
                           'beat_ref': beat_ref, 'voice': deepcopy(scene['voice']),
                           'start_frame': timing['start_frame'], 'frames': timing['frames']})
        except (KeyError, StopIteration, RuntimeError) as exc: issues.append(scene['id']+': '+str(exc))
    return {'ready': not issues and bool(scenes), 'issues': issues, 'scenes': scenes,
            'edit_sha256': fingerprint(edit), 'manifest_sha256': loaded.manifest_sha256,
            'input_sha256': fingerprint(final_input(edit, state)), 'fps': edit['fps'],
            'production_state': state.project_state, 'binding': binding, 'documentary_completed': False}


def inspect_final(project):
    EditSession(project).load()
    with project._lock(): return _inspect(project, EditSession(project).load(), ProductionProject(project)._load())


def _artifact(tx, kind, payload, origins):
    old = [a for a in _heads(tx.staged, kind) if _tag(a)]
    if len(old) > 1: raise EditError('ข้อมูลผลิตซ้ำ: '+kind)
    if old: return tx.create_artifact_version(old[0]['artifact_id'], base_version=old[0]['version'], payload_patch=payload, origin_refs=origins)
    return tx.create_artifact(kind, payload, origin_refs=origins)


def _object(tx, kind, key, payload):
    old = [o for o in tx.staged.objects.values() if o['object_type'] == kind and _tag(o).get('key') == key]
    ids = {o['id'] for o in old}
    if len(ids) > 1: raise EditError('ข้อมูลเสียงซ้ำ: '+key)
    if not old: return tx.create_object(kind, payload)
    prior = max(old, key=lambda o: o['version'])
    ref = tx.create_version(prior['id'], base_version=prior['version'], patch=payload)
    tx.promote_active_version(ref['id'], ref['version']); return ref


def _refresh_media(tx, edit, mapping):
    """New exact refs for unchanged reviewed pictures; never upgrade rights/matches."""
    for scene in edit['scenes']:
        if not scene['included']: continue
        pool = _pools(tx.staged)[scene['id']]; ext = deepcopy(pool['extensions']['project_media'])
        beat = mapping[scene['id']]['beat_ref']; live = _active(tx.staged)
        prior = live[ext['search_ref']['id']]
        search = tx.create_version(prior['id'], base_version=prior['version'], patch={'target_beat_ref': beat})
        tx.promote_active_version(search['id'], search['version'])
        for row in ext['rows']:
            refs = {}
            for kind, key, patch in [('SEARCH_RESULT', 'result_ref', {'search_ref': search}),
                                     ('ASSET', 'asset_ref', None), ('SEGMENT', 'segment_ref', None)]:
                prior = _active(tx.staged)[row[key]['id']]
                if kind == 'ASSET': patch = {'origin_search_result_ref': refs['result_ref']}
                if kind == 'SEGMENT': patch = {'asset_ref': refs['asset_ref']}
                ref = tx.create_version(prior['id'], base_version=prior['version'], patch=patch)
                tx.promote_active_version(ref['id'], ref['version']); refs[key] = ref
            row.update(**refs, beat_ref=beat, search_ref=search)
        ext['search_ref'] = search
        tx.create_artifact_version(pool['artifact_id'], base_version=pool['version'],
            payload_patch={'entries': ext['rows'], 'extensions': {'project_media': ext}},
            origin_refs=[mapping[scene['id']]['scene_ref'], beat, search,
                         *[r[k] for r in ext['rows'] for k in ('asset_ref', 'segment_ref')]])


def _assemble(project, check, folder):
    """Sequential PCM chunks keep memory bounded and match the video frame clock."""
    output = folder/'master.wav'; rate = 48000; timing = []
    with wave.open(str(output), 'wb') as master:
        master.setnchannels(1); master.setsampwidth(2); master.setframerate(rate)
        for order, scene in enumerate(check['scenes'], 1):
            samples = scene['frames']*(rate//check['fps']); part = folder/'part.wav'
            source = asset_file(project, scene['voice'], 'voice')
            frozen = folder/('source'+source.suffix)
            shutil.copyfile(source, frozen)
            if digest(frozen)['sha256'] != scene['voice']['sha256']:
                raise EditError('ไฟล์เสียงเปลี่ยนระหว่างเตรียมสำเนารวมเสียง')
            _run(_ffmpeg('-i', frozen, '-map', '0:a:0', '-af',
                f'aresample={rate},apad,atrim=end_sample={samples},asetpts=N/SR/TB',
                '-ac', '1', '-ar', rate, '-c:a', 'pcm_s16le', part))
            with wave.open(str(part), 'rb') as audio:
                if audio.getnframes() != samples: raise EditError('จำนวนตัวอย่างเสียงไม่ตรงไทม์ไลน์')
                while chunk := audio.readframes(65536): master.writeframesraw(chunk)
            start = scene['start_frame']*(rate//check['fps'])
            timing.append({'order': order, 'scene_id': scene['scene_id'], 'start_sample': start,
                           'end_sample': start+samples, 'start_seconds': start/rate, 'end_seconds': (start+samples)/rate})
    info = probe(output)
    if abs(info['duration_seconds']-sum(s['frames'] for s in check['scenes'])/check['fps']) > 1/rate:
        raise EditError('ความยาวเสียงรวมไม่ตรงไทม์ไลน์')
    return output, timing


def _compile(engine, project, edit, check, master_path, timing):
    initial = engine.snapshot(); old_report = next(q for q in _reports(initial) if q['report_type'] == 'ASSET_COVERAGE_REPORT')
    reason = old_report['extensions']['project_coverage']['stop_reason']
    spine = _spine(initial); mapping = deepcopy(spine['extensions']['project_story']['scene_map'])
    signature = check['input_sha256']; tag = {'project_final': {'input_sha256': signature, 'retired': False}}
    project_ref = _ref(next(o for o in _active(initial).values() if o['object_type'] == 'PROJECT'))
    tx = engine.begin(); retire_coverage(tx, include_final=False); blocks = []
    for scene in check['scenes']:
        prior = _active(tx.staged)[scene['beat_ref']['id']]
        ref = tx.create_version(prior['id'], base_version=prior['version'], patch={
            'narration': {'text': scene['narration'], 'language_mode': scene['language_mode']}, 'workflow_state': 'NARRATION_FINAL'})
        tx.promote_active_version(ref['id'], ref['version']); mapping[scene['scene_id']]['beat_ref'] = ref
        obj = tx.staged.objects[(ref['id'], ref['version'])]
        blocks.append({'beat_ref': ref, 'decision_sha256': engine.semantic.decision_hash(obj), 'narration_text': scene['narration']})
    tx.create_artifact_version(spine['artifact_id'], base_version=spine['version'], payload_patch={
        'extensions': {'project_story': {'scene_map': mapping}, 'rough_narrative': {'beat_refs': [b['beat_ref'] for b in blocks]}}},
        origin_refs=spine['origin_refs'])
    _refresh_media(tx, edit, mapping)
    script = _artifact(tx, 'VOICEOVER_SCRIPT_FINAL', {'project_ref': project_ref,
        'language': final_input(edit, initial)['language'], 'blocks': blocks,
        'extensions': {**tag, 'script_runtime': {'batch_id': 'PROJECT_FINAL_'+signature[:20], 'plan_sha256': signature, 'block_count': len(blocks)}}},
        [project_ref, *[b['beat_ref'] for b in blocks]])
    tx.commit()
    coverage = coverage_inspect(project, edit, SimpleNamespace(engine=engine, manifest_sha256=check['manifest_sha256']))
    if not coverage['ready']: raise EditError('การเชื่อมบทสุดท้ายทำให้ภาพไม่พร้อม: '+'; '.join(i['detail'] for i in coverage['issues']))
    _write_assessment(engine, coverage, True, reason)
    tx = engine.begin(); tx.transition_project_state('SCRIPT_READY', actor_type='AI'); tx.commit()
    source = engine.snapshot().artifacts[(script['artifact_id'], script['version'])]
    TTSRuntime._validate_script(source, engine.snapshot())
    delivery = {'default_style': 'NEUTRAL_DOCUMENTARY', 'speech_rate': 'NATURAL'}
    profile = {'profile_name': 'GMK reviewed per-scene audio', 'engine_class': 'HYBRID',
               'delivery': delivery, 'technical_constraints': {'sample_rate_hz': 48000, 'channels': 1}}
    TTSRuntime._validate_plan({'language': source['language'], 'voice_profile': profile, 'pronunciations': []})
    tx = engine.begin()
    dictionary = _artifact(tx, 'PRONUNCIATION_DICTIONARY', {'language': source['language'], 'entries': [], 'extensions': tag}, [script])
    vp = _object(tx, 'VOICE_PROFILE', 'profile', {**profile, 'language': source['language'],
        'extensions': {'project_final': {**tag['project_final'], 'key': 'profile', 'mode': 'EXISTING_PER_SCENE_AUDIO'}}})
    tts_blocks = [{'order': i, 'beat_ref': b['beat_ref'], 'text': b['narration_text'],
                   'source_decision_sha256': b['decision_sha256'],
                   'delivery': {'style': delivery['default_style'], 'speech_rate': delivery['speech_rate']}}
                  for i, b in enumerate(blocks, 1)]
    tts = _artifact(tx, 'TTS_READY_SCRIPT', {'source_script': script, 'pronunciation_dictionary': dictionary,
        'voice_profile_ref': vp, 'blocks': tts_blocks,
        'extensions': {**tag, 'tts_runtime': {'rendered_audio': False},
                       'project_audio_sources': [{'scene_id': s['scene_id'], 'file': s['voice'], 'provider': s['voice'].get('provider')} for s in check['scenes']]}},
        [script, dictionary, vp])
    voice_blocks = [_object(tx, 'VOICE_BLOCK', s['scene_id'], {'voice_profile_ref': vp, 'tts_script_ref': tts,
        'source_beat_refs': [b['beat_ref']], 'order': i, 'delivery': {}, 'workflow_state': 'TTS_READY',
        'extensions': {'project_final': {**tag['project_final'], 'key': s['scene_id']}}})
        for i, (s, b) in enumerate(zip(check['scenes'], blocks), 1)]
    tx.commit(); tx = engine.begin(); tx.transition_project_state('TTS_READY', actor_type='AI'); tx.commit()
    tx = engine.begin(); info = probe(master_path); sha = digest(master_path)['sha256']
    master = _artifact(tx, 'MASTER_VOICE', {'project_ref': project_ref, 'source_voice_blocks': voice_blocks,
        'audio': {'uri': 'gmk://workspace/'+master_path.relative_to(ProductionProject(project).workspace).as_posix(),
                  'sha256': sha, 'duration_seconds': info['duration_seconds'], 'sample_rate_hz': 48000, 'channels': 1},
        'extensions': {**tag, 'voice_runtime': {'verified_bytes': True, 'mode': 'ASSEMBLED_EXISTING_AUDIO'}}}, [tts])
    map_rows = [{'order': t['order'], 'voice_block_ref': voice_blocks[t['order']-1],
                 'start_seconds': t['start_seconds'], 'end_seconds': t['end_seconds']} for t in timing]
    timing_ref = _artifact(tx, 'VOICE_TIMING_MAP', {'master_voice': master, 'duration_seconds': info['duration_seconds'],
        'blocks': map_rows, 'extensions': {**tag, 'project_sample_clock': {'sample_rate_hz': 48000, 'fps': check['fps'], 'blocks': timing}}}, [master])
    lock = _artifact(tx, 'VOICE_LOCK_MANIFEST', {'voice_profile_ref': vp, 'voiceover_script': script, 'tts_script': tts,
        'pronunciation_dictionary': dictionary, 'voice_blocks': voice_blocks, 'master_voice': master, 'timing_map': timing_ref,
        'extensions': {**tag, 'voice_runtime': {'human_approval_required': True, 'approval_created': False, 'mode': 'IMPORTED_MASTER'}}},
        [master, timing_ref, tts])
    _artifact(tx, 'VOICE_REVIEW_PACKAGE', {'scope': {'type': 'VOICE_LOCK'}, 'voice_lock': lock,
        'master_voice': master, 'timing_map': timing_ref, 'tts_script': tts,
        'review_summary': {'block_count': len(blocks), 'duration_seconds': info['duration_seconds'], 'audio_sha256': sha},
        'extensions': {**tag, 'project_selection_history': {'prior_report': old_report['id']+'@'+str(old_report['version']), 'stop_reason': reason}}},
        [lock, master, timing_ref, tts])
    tx.commit()


def prepare_final(project, *, expected_edit_sha256, expected_manifest_sha256):
    production = ProductionProject(project); EditSession(project).load()
    with project._lock():
        edit = EditSession(project).load(); loaded = production._load()
        if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
            raise EditError('งานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจบทและเสียงใหม่')
        check = _inspect(project, edit, loaded)
        if check['binding']['current']: return {**check, 'idempotent_replay': True}
        if not check['ready']: raise EditError('ยังเตรียมบทและเสียงไม่ได้: '+'; '.join(check['issues']))
    with tempfile.TemporaryDirectory(dir=project.root, prefix='.final-voice-') as folder:
        output, timing = _assemble(project, check, Path(folder))
        with project._lock():
            loaded = production._load()
            if fingerprint(EditSession(project).load()) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
                raise EditError('งานเปลี่ยนระหว่างรวมเสียง กรุณาตรวจใหม่')
            dest = production.workspace/'media'/'voice'; dest.mkdir(parents=True, exist_ok=True)
            master = dest/('project_master_'+digest(output)['sha256']+'.wav')
            if master.is_symlink() or (master.exists() and digest(master) != digest(output)):
                raise EditError('เสียงรวมในคลังถูกแก้ เก็บไว้ตรวจและกู้ไฟล์เดิมก่อน')
            if not master.exists():
                fd, name = tempfile.mkstemp(dir=dest, prefix='.master-', suffix='.tmp'); os.close(fd)
                try:
                    shutil.copyfile(output, name)
                    os.link(name, master)  # Exclusive publication; interruptions leave only a temporary file.
                finally: Path(name).unlink(missing_ok=True)
            _compile(loaded.engine, project, edit, check, master, timing)
            for s in check['scenes']: asset_file(project, s['voice'], 'voice')
            for pool in _pools(loaded.engine.snapshot()).values():
                if not pool['extensions']['project_media'].get('retired'):
                    for row in pool['extensions']['project_media']['rows']: asset_file(project, row['file'], 'footage')
            RuntimeStore(RUNTIME_ROOT, production.workspace).persist(loaded.engine)
            data = project.read(); data['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, data)
            final = production._load()
            return {**check, 'production_state': final.engine.project_state, 'manifest_sha256': final.manifest_sha256,
                    'binding': final_binding_status(project, final.engine.snapshot(), edit=edit), 'idempotent_replay': False}


def reopen_final(project, *, expected_edit_sha256, expected_manifest_sha256):
    production = ProductionProject(project)
    with project._lock():
        edit = EditSession(project).load(); loaded = production._load(); engine = loaded.engine
        if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
            raise EditError('งานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจใหม่ก่อนกลับไปแก้')
        from .design_planning import design_present, owns_design
        state = engine.snapshot()
        if (engine.project_state not in READABLE_STATES or not owns_final(state)
                or (design_present(state) and not owns_design(state))):
            raise EditError('กลับไปแก้ได้เฉพาะบทและเสียงขั้นต้นที่เตรียมจากโปรเจกต์นี้')
        tx = engine.begin(); retire_coverage(tx)
        tx.reenter_stage('ASSET_RECON', actor_type='HUMAN'); tx.commit()
        RuntimeStore(RUNTIME_ROOT, production.workspace).persist(engine)
        data = project.read(); data['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, data)
        return {'production_state': engine.project_state, 'documentary_completed': False}


def decide_final_voice(project, *, expected_edit_sha256, expected_manifest_sha256, expected_master_sha256,
                       decision, actor_id):
    if decision not in {'APPROVED', 'REJECTED'} or not actor_id.strip(): raise EditError('ระบุผลตรวจเสียงและชื่อผู้ตรวจ')
    production = ProductionProject(project)
    with project._lock():
        edit = EditSession(project).load(); loaded = production._load(); engine = loaded.engine; state = engine.snapshot()
        if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
            raise EditError('งานเปลี่ยนหลังเปิดฟัง กรุณาเปิดเสียงรวมรุ่นใหม่')
        binding = final_binding_status(project, state, edit=edit)
        if not binding['current']: raise EditError('บทหรือเสียงรวมไม่ตรงงานปัจจุบัน ต้องเตรียมใหม่ก่อนยืนยัน')
        lock = next(a for a in _heads(state, 'VOICE_LOCK_MANIFEST') if _tag(a))
        master = state.artifacts[(lock['master_voice']['artifact_id'], lock['master_voice']['version'])]
        if master['audio']['sha256'] != expected_master_sha256: raise EditError('ผลการฟังไม่ใช่เสียงรวมรุ่นนี้')
        master_file(production, master)
        review = next(a for a in _heads(state, 'VOICE_REVIEW_PACKAGE') if _tag(a) and a['voice_lock'] == _aref(lock))
        prior = next((o for o in _active(state).values() if o['object_type'] == 'APPROVAL' and _tag(o)
                      and o.get('target') == _aref(lock) and o.get('review_context') == _aref(review)
                      and o['decision'] == decision and o['actor']['actor_id'] == actor_id.strip()), None)
        if prior: return {'binding': binding, 'manifest_sha256': loaded.manifest_sha256, 'idempotent_replay': True}
        if any(o['object_type'] == 'APPROVAL' and o.get('target') == _aref(lock) for o in _active(state).values()):
            raise EditError('เสียงรุ่นนี้มีผลตรวจแล้ว หากต้องแก้ผลตรวจให้กลับไปตรวจความครอบคลุมและเตรียมเสียงรุ่นใหม่')
        tx = engine.begin()
        ref = tx.create_approval({'approval_class': 'VOICE', 'target': _aref(lock), 'review_context': _aref(review),
            'decision': decision, 'actor': {'type': 'HUMAN', 'actor_id': actor_id.strip()}, 'decided_at': engine.now(),
            'extensions': {'project_final': {'input_sha256': fingerprint(final_input(edit, state)), 'retired': False}}})
        if decision == 'APPROVED': tx.transition_project_state('VOICE_LOCKED', actor_type='HUMAN', human_confirmed=True)
        tx.commit(); RuntimeStore(RUNTIME_ROOT, production.workspace).persist(engine)
        data = project.read(); data['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, data)
        final = production._load()
        return {'approval_ref': ref, 'production_state': final.engine.project_state, 'manifest_sha256': final.manifest_sha256,
                'binding': final_binding_status(project, final.engine.snapshot(), edit=edit), 'idempotent_replay': False}
