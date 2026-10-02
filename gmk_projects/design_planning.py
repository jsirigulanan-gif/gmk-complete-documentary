"""Bind the renderer's actual design and selected cuts to frozen production plans.

Design review is an explicit human decision. Plans describe the current edit;
they do not invent shots, graphical assets, source rights or final-film approval.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile

from gmk_design.runtime import _base_design
from gmk_runtime.persistence import RuntimeStore

from .edit import EditError, EditSession, asset_file, fingerprint
from .final_production import _aref, _ref, _heads, final_binding_status, master_file
from .media_bridge import _pools
from .production import ProductionProject, RUNTIME_ROOT
from .production_bridge import _active, _spine
from .render import _ffmpeg, _run, _title_ass, _title_text
from .research import _research_review
from .storage import StorageError, atomic_json, digest, relative_path


STATES = {'VOICE_LOCKED', 'DESIGN_DNA_APPROVED', 'SCENE_PLAN_READY', 'SHOT_PLAN_READY'}
READABLE_STATES = STATES | {'HTML_REVIEW', 'HTML_APPROVED', 'PRODUCTION_RENDER'}
EDITABLE_STATES = STATES | {'HTML_REVIEW', 'HTML_APPROVED'}
ARTIFACTS = {'EFFECTIVE_DESIGN_TOKENS', 'DESIGN_DNA_REVIEW_PACKAGE', 'SCENE_ASSET_POOL', 'SCENE_PLAN'}
OBJECTS = {'DESIGN_DNA', 'SHOT', 'LAYER', 'CUE'}
RULES = {'version': 1, 'fit': 'CONTAIN_WITH_BLACK_PADDING', 'transition': 'CUT',
         'title': 'RENDERER_ASS_FIRST_CUT_MAX_3_SECONDS_120_CHARACTERS',
         'captions': 'SOFT_MOV_TEXT_WITH_SRT_SIDECAR_ALIGNMENT_REVIEW_PENDING',
         'music': 'EXISTING_RENDERER_DUCKING_NO_NEW_AUDIO_GENERATION'}


def _tag(obj):
    return obj.get('extensions', {}).get('project_design') or obj.get('extensions', {}).get('project_plan') or {}


def _records(state):
    return [o for o in _active(state).values() if o['object_type'] in OBJECTS
            or (o['object_type'] == 'APPROVAL' and o.get('approval_class') == 'DESIGN_DNA')] + [
                a for a in _heads(state) if a['artifact_type'] in ARTIFACTS]


def design_present(state):
    return any(not _tag(o).get('retired') for o in _records(state))


def owns_design(state):
    records = _records(state)
    return bool(records) and all(_tag(o) for o in records)


def retire_design(tx):
    from .preproduction import retire_review
    retire_review(tx)
    for obj in _active(tx.staged).values():
        if _tag(obj) and (obj['object_type'] in OBJECTS or obj['object_type'] == 'APPROVAL'):
            tx.archive_object(obj['id'])
    for art in _heads(tx.staged):
        if art['artifact_type'] in ARTIFACTS and _tag(art) and not _tag(art).get('retired'):
            namespace = 'project_design' if art.get('extensions', {}).get('project_design') else 'project_plan'
            tx.create_artifact_version(art['artifact_id'], base_version=art['version'],
                                      payload_patch={'extensions': {namespace: {'retired': True}}})


def design_input(edit, state):
    lock = next((a for a in _heads(state, 'VOICE_LOCK_MANIFEST') if not a.get('extensions', {}).get('project_final', {}).get('retired')), None)
    return {'rules': RULES, 'renderer_code_sha256': digest(Path(__file__).with_name('render.py'))['sha256'],
            'design_policy': _base_design(RUNTIME_ROOT), 'voice_lock': _aref(lock) if lock else None,
            'spine': _aref(_spine(state)) if _spine(state) else None,
            'width': edit['width'], 'height': edit['height'], 'fps': edit['fps'],
            'music': edit.get('music'), 'music_omitted': edit.get('music_omitted', False), 'music_gain': edit['music_gain'],
            'scenes': [{'id': s['id'], 'title': s['title'], 'show_title': s['show_title'],
                        'subtitles': (s.get('voice') or {}).get('subtitles')} for s in edit['scenes'] if s['included']]}


def _file(production, record):
    path = production.workspace/relative_path(record['path'])
    if (path.is_symlink() or not path.resolve().is_relative_to(production.workspace)
            or not path.is_file() or digest(path)['sha256'] != record['sha256']):
        raise EditError('ไฟล์ตัวอย่างรูปแบบภาพหายหรือเปลี่ยนหลังเตรียม')
    return path


def _asset_refs_current(state, obj):
    return all((state.artifact_registry.entries.get(r['artifact_id'])
                and state.artifact_registry.entries[r['artifact_id']].head_version == r['version'])
               for r in obj.get('origin_refs', []) if 'artifact_id' in r)


def design_binding_status(project, state, *, edit=None, final_status=None):
    if edit is None:
        try: edit = json.loads((project.root/'edit.json').read_text())
        except (OSError, ValueError): edit = None
    dnas = [o for o in _active(state).values() if o['object_type'] == 'DESIGN_DNA' and _tag(o)]
    dna = dnas[0] if len(dnas) == 1 else None
    current = bool(dna and edit and state.project_state in READABLE_STATES and owns_design(state)
                   and _tag(dna)['input_sha256'] == fingerprint(design_input(edit, state))
                   and not dna.get('stale', {}).get('is_stale')
                   and dna['status'] not in {'STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED'}
                   and (final_status if final_status is not None else final_binding_status(project, state, edit=edit))['voice_locked'])
    tokens = [a for a in _heads(state, 'EFFECTIVE_DESIGN_TOKENS') if _tag(a) and not _tag(a).get('retired')]
    reviews = [a for a in _heads(state, 'DESIGN_DNA_REVIEW_PACKAGE') if _tag(a) and not _tag(a).get('retired')]
    token = tokens[0] if len(tokens) == 1 else None
    review = reviews[0] if len(reviews) == 1 else None
    current = bool(current and token and review and token['design_dna_ref'] == _ref(dna)
                   and review['design_dna_ref'] == _ref(dna) and review['effective_tokens'] == _aref(token)
                   and _asset_refs_current(state, review))
    if current:
        try:
            _file(ProductionProject(project), _tag(dna)['preview'])
            _verify_design_files(project, edit)
        except (OSError, StorageError): current = False
    decisions = [o for o in _active(state).values() if o['object_type'] == 'APPROVAL' and _tag(o)
                 and o.get('target') == (_ref(dna) if dna else None)
                 and o.get('review_context') == (_aref(review) if review else None)]
    rejected = current and any(o['decision'] == 'REJECTED' for o in decisions)
    approved = bool(current and state.project_state != 'VOICE_LOCKED'
                    and any(o['decision'] == 'APPROVED' for o in decisions) and not rejected)
    return {'connected': bool(dna), 'current': current, 'approved': approved,
            'decision': 'REJECTED' if rejected else 'APPROVED' if approved else None,
            'design_ref': _ref(dna) if dna else None, 'review_ref': _aref(review) if review else None,
            'tokens_ref': _aref(token) if token else None, 'preview': _tag(dna).get('preview') if dna else None,
            'reason': 'รูปแบบภาพผ่านการยืนยันและตรงงานปัจจุบัน' if approved else
                      'รูปแบบภาพยังต้องแก้ — กลับไปแก้รูปแบบแล้วเตรียมใหม่' if rejected else
                      'รอเปิดตัวอย่างและยืนยันรูปแบบภาพ' if current else 'ต้องเตรียมรูปแบบภาพจากเสียงที่ยืนยันแล้วรุ่นปัจจุบัน'}


def plan_binding_status(project, state, *, edit=None, design_status=None):
    if edit is None:
        try: edit = json.loads((project.root/'edit.json').read_text())
        except (OSError, ValueError): edit = None
    design = design_status if design_status is not None else design_binding_status(project, state, edit=edit)
    plans = [a for a in _heads(state, 'SCENE_PLAN') if _tag(a) and not _tag(a).get('retired')]
    signature = fingerprint(edit) if edit else None
    current = bool(edit and design['approved'] and state.project_state in READABLE_STATES - {'VOICE_LOCKED', 'DESIGN_DNA_APPROVED'}
                   and len(plans) == sum(s['included'] for s in edit['scenes'])
                   and { _tag(p)['key'] for p in plans } == {s['id'] for s in edit['scenes'] if s['included']}
                   and all(_tag(p)['edit_sha256'] == signature and _asset_refs_current(state, p) for p in plans))
    active = _active(state)
    for plan in plans:
        for field in ('voice_lock', 'design_tokens', 'scene_asset_pool'):
            ref = plan[field]; entry = state.artifact_registry.entries.get(ref['artifact_id'])
            if not entry or entry.head_version != ref['version']: current = False
        for field in ('scene_ref', 'design_dna_ref'):
            ref = plan[field]; obj = active.get(ref['id'])
            if not obj or obj['version'] != ref['version']: current = False
        for row in plan['shots']:
            ref = row['shot_ref']; shot = active.get(ref['id'])
            if (not shot or shot['version'] != ref['version'] or shot.get('stale', {}).get('is_stale')
                    or shot['status'] in {'STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED'}): current = False
    return {'connected': bool(plans), 'current': current,
            'scene_plan_ready': current, 'shot_plan_ready': current and state.project_state != 'SCENE_PLAN_READY',
            'scene_count': len(plans), 'shot_count': sum(len(p['shots']) for p in plans),
            'reason': 'แผนฉากและช็อตตรงช่วงตัดและเสียงที่ยืนยันแล้ว' if current else 'ต้องเชื่อมแผนฉากและช็อตจากงานรุ่นปัจจุบัน'}


def _verify_design_files(project, edit):
    if edit.get('music'): asset_file(project, edit['music'], 'music')
    for s in edit['scenes']:
        sub = (s.get('voice') or {}).get('subtitles')
        if s['included'] and sub: asset_file(project, sub, 'voice')


def _inspect(project, edit, loaded):
    state = loaded.engine.snapshot(); final = final_binding_status(project, state, edit=edit)
    design = design_binding_status(project, state, edit=edit, final_status=final)
    plan = EditSession(project).preflight(edit, research=_research_review(project))
    issues = [i['detail'] for i in plan['issues']]
    if not final['voice_locked']: issues.append('ยืนยันเสียงรวมขั้นผลิตรุ่นปัจจุบันก่อนเตรียมรูปแบบภาพ')
    if state.project_state not in STATES: issues.append('ต้องกลับมาแก้ในขั้นออกแบบก่อนล็อกการผลิต')
    if any(not _tag(o) for o in _records(state)): issues.append('มีงานออกแบบหรือแผนจากระบบอื่น ต้องย้ายข้อมูลก่อน')
    if not edit.get('music') and not edit.get('music_omitted'): issues.append('เลือกดนตรีหรือระบุว่าตั้งใจไม่ใช้ดนตรี')
    try: _verify_design_files(project, edit)
    except (OSError, StorageError) as exc: issues.append(str(exc))
    return {'ready': not issues, 'issues': issues, 'settings': design_input(edit, state), 'timeline': plan,
            'edit_sha256': fingerprint(edit), 'manifest_sha256': loaded.manifest_sha256,
            'input_sha256': fingerprint(design_input(edit, state)), 'production_state': state.project_state,
            'design_binding': design, 'plan_binding': plan_binding_status(project, state, edit=edit, design_status=design),
            'documentary_completed': False}


def inspect_design(project):
    EditSession(project).load()
    with project._lock(): return _inspect(project, EditSession(project).load(), ProductionProject(project)._load())


def _tokens(project, expected_edit_sha256, expected_manifest_sha256):
    edit = EditSession(project).load(); loaded = ProductionProject(project)._load()
    if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
        raise EditError('งานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจรูปแบบภาพและแผนใหม่')
    return edit, loaded


def _artifact(tx, kind, key, payload, origins):
    old = [a for a in _heads(tx.staged, kind) if _tag(a).get('key') == key]
    if len(old) > 1: raise EditError('ข้อมูลออกแบบหรือแผนซ้ำ: '+key)
    if old: return tx.create_artifact_version(old[0]['artifact_id'], base_version=old[0]['version'], payload_patch=payload, origin_refs=origins)
    return tx.create_artifact(kind, payload, origin_refs=origins)


def _object(tx, kind, key, payload):
    old = [o for o in tx.staged.objects.values() if o['object_type'] == kind and _tag(o).get('key') == key]
    if not old: return tx.create_object(kind, payload)
    if len({o['id'] for o in old}) != 1: raise EditError('ข้อมูลออกแบบหรือช็อตซ้ำ: '+key)
    prior = max(old, key=lambda o: o['version'])
    ref = tx.create_version(prior['id'], base_version=prior['version'], patch=payload)
    tx.promote_active_version(ref['id'], ref['version']); return ref


def _persist(project, engine):
    RuntimeStore(RUNTIME_ROOT, ProductionProject(project).workspace).persist(engine)
    data = project.read(); data['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, data)


def prepare_design(project, *, expected_edit_sha256, expected_manifest_sha256):
    production = ProductionProject(project)
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256)
        check = _inspect(project, edit, loaded)
        if check['design_binding']['current']: return {**check, 'idempotent_replay': True}
        if not check['ready']: raise EditError('; '.join(check['issues']))
        if loaded.engine.project_state != 'VOICE_LOCKED' or design_present(loaded.engine.snapshot()):
            raise EditError('กลับไปแก้รูปแบบก่อนเตรียมข้อมูลรุ่นใหม่')
    with tempfile.TemporaryDirectory(dir=project.root, prefix='.design-preview-') as folder:
        temp = Path(folder); timeline = check['timeline']
        scene = next((s for s in timeline['timeline'] if s['show_title']), timeline['timeline'][0])
        cut = scene['cuts'][0]; source = asset_file(project, cut, 'footage')
        vf = (f'scale={edit["width"]}:{edit["height"]}:force_original_aspect_ratio=decrease,'
              f'pad={edit["width"]}:{edit["height"]}:(ow-iw)/2:(oh-ih)/2,setsar=1')
        if scene['show_title']:
            (temp/'title.ass').write_text(_title_ass(scene['title'], edit['width'], edit['height']))
            vf += ',ass=title.ass'
        preview = temp/'preview.png'
        _run(_ffmpeg('-ss', cut['in_seconds'], '-i', source, '-vf', vf, '-frames:v', 1, '-threads', 1, preview), cwd=temp)
        asset_file(project, cut, 'footage')
        with project._lock():
            edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256)
            check = _inspect(project, edit, loaded)
            if not check['ready']: raise EditError('; '.join(check['issues']))
            dest = production.workspace/'media'/'design'; dest.mkdir(parents=True, exist_ok=True)
            path = dest/(digest(preview)['sha256']+'.png')
            if path.is_symlink() or (path.exists() and digest(path) != digest(preview)):
                raise EditError('ไฟล์ตัวอย่างรูปแบบในคลังถูกแก้')
            if not path.exists():
                fd, name = tempfile.mkstemp(dir=dest, prefix='.preview-', suffix='.tmp'); os.close(fd)
                try:
                    shutil.copyfile(preview, name); os.link(name, path)
                finally: Path(name).unlink(missing_ok=True)
            record = {'path': path.relative_to(production.workspace).as_posix(), **digest(path)}
            engine = loaded.engine; state = engine.snapshot(); settings = check['settings']
            tag = {'project_design': {'key': 'design', 'input_sha256': check['input_sha256'], 'retired': False, 'preview': record}}
            refs = [settings['voice_lock'], settings['spine']]
            project_ref = _ref(next(o for o in _active(state).values() if o['object_type'] == 'PROJECT'))
            intent = {'visual_thesis': edit.get('central_question') or edit['title'],
                      'audience_feeling': 'Follow the reviewed narrative with readable source pictures.',
                      'clarity_principle': 'Retain source framing, use current titles and keep subtitle timing uncertainty visible.'}
            rules = [{'rule_id': 'DNR_'+domain, 'domain': domain, 'action': 'REQUIRE', 'statement': statement,
                      'rationale': 'Matches the current editor renderer.', 'reference_refs': refs} for domain, statement in (
                          ('COMPOSITION', 'Contain footage with black padding; no implicit crop.'),
                          ('TYPOGRAPHY', 'Current ASS title style and soft subtitle track; inspect real glyph legibility.'),
                          ('TRANSITION', 'Cuts between selected source intervals; explicit final-frame holds are disclosed.'))]
            tx = engine.begin()
            dna = _object(tx, 'DESIGN_DNA', 'design', {'project_ref': project_ref, 'base_design': _base_design(RUNTIME_ROOT),
                'design_intent': intent, 'rules': rules, 'references': refs, 'token_overrides': settings,
                'graphic_policy': {'default_decision': 'OPTIONAL'}, 'extensions': tag})
            tokens = _artifact(tx, 'EFFECTIVE_DESIGN_TOKENS', 'design', {'base_design': _base_design(RUNTIME_ROOT),
                'design_dna_ref': dna, 'tokens': settings, 'extensions': tag}, refs+[dna])
            _artifact(tx, 'DESIGN_DNA_REVIEW_PACKAGE', 'design', {'scope': {'type': 'DESIGN_DNA'},
                'design_dna_ref': dna, 'voice_lock': refs[0], 'narrative_spine': refs[1], 'effective_tokens': tokens,
                'review_summary': {'rule_count': len(rules), 'reference_count': 2, 'visual_thesis': intent['visual_thesis']},
                'extensions': tag}, refs+[tokens, dna])
            tx.commit(); _verify_design_files(project, edit); _file(production, record); _persist(project, engine)
            return {**_inspect(project, edit, production._load()), 'idempotent_replay': False}


def decide_design(project, *, expected_edit_sha256, expected_manifest_sha256, decision, actor_id):
    if decision not in {'APPROVED', 'REJECTED'} or not actor_id.strip(): raise EditError('ระบุผลตรวจและชื่อผู้ตรวจรูปแบบภาพ')
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256)
        check = _inspect(project, edit, loaded); binding = check['design_binding']; engine = loaded.engine
        if not check['ready'] or not binding['current']: raise EditError('รูปแบบภาพไม่ตรงงานปัจจุบัน ต้องเตรียมใหม่')
        prior = [o for o in _active(engine.snapshot()).values() if o['object_type'] == 'APPROVAL' and _tag(o)
                 and o.get('target') == binding['design_ref'] and o.get('review_context') == binding['review_ref']]
        if prior:
            if any(o['decision'] == decision and o['actor']['actor_id'] == actor_id.strip() for o in prior):
                return {**check, 'idempotent_replay': True}
            raise EditError('รูปแบบนี้มีผลตรวจแล้ว ต้องกลับไปแก้และเตรียมรุ่นใหม่')
        dna = engine.snapshot().objects[(binding['design_ref']['id'], binding['design_ref']['version'])]
        tx = engine.begin(); tx.create_approval({'approval_class': 'DESIGN_DNA', 'target': binding['design_ref'],
            'target_decision_sha256': engine.semantic.decision_hash(dna), 'review_context': binding['review_ref'],
            'decision': decision, 'actor': {'type': 'HUMAN', 'actor_id': actor_id.strip()}, 'decided_at': engine.now(),
            'extensions': {'project_design': {'input_sha256': check['input_sha256'], 'retired': False}}})
        if decision == 'APPROVED': tx.transition_project_state('DESIGN_DNA_APPROVED', actor_type='HUMAN', human_confirmed=True)
        tx.commit(); _persist(project, engine)
        return {**_inspect(project, edit, ProductionProject(project)._load()), 'idempotent_replay': False}


def reopen_design(project, *, expected_edit_sha256, expected_manifest_sha256):
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        if engine.project_state not in EDITABLE_STATES or not owns_design(engine.snapshot()): raise EditError('กลับไปแก้ได้เฉพาะรูปแบบและแผนที่สร้างจากโปรเจกต์นี้ก่อนล็อกการผลิต — ถ้าล็อกแล้วให้กลับไปแก้แผนการผลิตก่อน')
        tx = engine.begin(); retire_design(tx)
        if engine.project_state != 'VOICE_LOCKED': tx.reenter_stage('VOICE_LOCKED', actor_type='HUMAN')
        tx.commit(); _persist(project, engine)
        return _inspect(project, edit, ProductionProject(project)._load())


def prepare_plans(project, *, expected_edit_sha256, expected_manifest_sha256):
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        check = _inspect(project, edit, loaded); binding = check['design_binding']
        if check['plan_binding']['shot_plan_ready']: return {**check, 'idempotent_replay': True}
        if not check['ready'] or not binding['approved'] or engine.project_state != 'DESIGN_DNA_APPROVED':
            raise EditError('ยืนยันรูปแบบภาพรุ่นปัจจุบันก่อนเชื่อมแผนฉากและช็อต')
        state = engine.snapshot(); pools = _pools(state); mapping = _spine(state)['extensions']['project_story']['scene_map']
        lock = next(a for a in _heads(state, 'VOICE_LOCK_MANIFEST') if not a['extensions']['project_final'].get('retired'))
        timing = state.artifacts[(lock['timing_map']['artifact_id'], lock['timing_map']['version'])]
        voice = state.artifacts[(lock['master_voice']['artifact_id'], lock['master_voice']['version'])]; master_file(ProductionProject(project), voice)
        blocks = {o['source_beat_refs'][0]['id']: o for o in _active(state).values() if o['object_type'] == 'VOICE_BLOCK'}
        tx = engine.begin(); plan_refs = {}; fps = edit['fps']; signature = check['edit_sha256']
        for scene in check['timeline']['timeline']:
            key = scene['scene_id']; m = mapping[key]; beat = state.objects[(m['beat_ref']['id'], m['beat_ref']['version'])]
            rows = {r['shot_id']: r for r in pools[key]['extensions']['project_media']['rows']}
            selected = [rows[c['id']]['segment_ref'] for c in scene['cuts']]
            tag = {'project_plan': {'key': key, 'edit_sha256': signature, 'retired': False}}
            pool = _artifact(tx, 'SCENE_ASSET_POOL', key, {'scene_ref': m['scene_ref'], 'beat_pools': [{
                'beat_ref': m['beat_ref'], 'beat_key': key, 'visual_requirement': deepcopy(beat['visual_requirement']),
                'segment_refs': selected, 'voice_range': {'start_seconds': scene['start_frame']/fps,
                'end_seconds': (scene['start_frame']+scene['frames'])/fps}}], 'extensions': tag},
                [m['scene_ref'], m['beat_ref'], *selected])
            plan_refs[key] = _artifact(tx, 'SCENE_PLAN', key, {'scene_ref': m['scene_ref'], 'voice_lock': _aref(lock),
                'design_dna_ref': binding['design_ref'], 'design_tokens': binding['tokens_ref'], 'scene_asset_pool': pool,
                'shots': [], 'extensions': tag}, [m['scene_ref'], _aref(lock), binding['design_ref'], binding['tokens_ref'], pool])
        tx.commit(); tx = engine.begin(); tx.transition_project_state('SCENE_PLAN_READY', actor_type='AI'); tx.commit()
        tx = engine.begin()
        for scene in check['timeline']['timeline']:
            key = scene['scene_id']; m = mapping[key]; beat = state.objects[(m['beat_ref']['id'], m['beat_ref']['version'])]
            vb = blocks[m['beat_ref']['id']]; cursor = scene['start_frame']; shots = []; rows = {r['shot_id']: r for r in pools[key]['extensions']['project_media']['rows']}
            for order, cut in enumerate(scene['cuts'], 1):
                row = rows[cut['id']]; start = cursor; cursor += cut['frames']; shot_key = key+'/'+cut['id']
                tag = {'project_plan': {'key': shot_key, 'edit_sha256': signature, 'retired': False,
                    'source_file': deepcopy(row['file']), 'source_in_seconds': cut['in_seconds'], 'selected_out_seconds': cut['out_seconds'],
                    'used_source_frames': cut['frames']-cut['freeze_frames'], 'hold_frames': cut['freeze_frames'],
                    'start_frame': start, 'end_frame': cursor, 'fps': fps, 'original_match': cut['visual_review']['match_type'], 'rights': 'UNKNOWN'}}
                layer = _object(tx, 'LAYER', shot_key+'/picture', {'stack_role': 'BASE', 'z_index': 0,
                    'content': {'type': 'MEDIA_SEGMENT', 'segment_ref': row['segment_ref']},
                    'comprehension_purpose': {'type': 'FOCUS_ATTENTION', 'description': cut['visual_review']['match_reason']},
                    'presentation': {'fit': 'CONTAIN', 'padding': 'BLACK', 'source_in_seconds': cut['in_seconds'],
                                     'used_source_frames': cut['frames']-cut['freeze_frames'], 'hold_frames': cut['freeze_frames']},
                    'treatment': {'design_tokens_ref': binding['tokens_ref']},
                    'motion': {'decision': 'NO_MOTION', 'purpose': 'Preserve selected source framing.'},
                    'extensions': {'project_plan': {**tag['project_plan'], 'key': shot_key+'/picture'}}})
                layers = [layer]
                if order == 1 and scene['show_title']:
                    title = _object(tx, 'LAYER', shot_key+'/title', {'stack_role': 'LABEL', 'z_index': 1,
                        'content': {'type': 'TEXT', 'text': _title_text(scene['title'])},
                        'comprehension_purpose': {'type': 'FOCUS_ATTENTION', 'description': 'Current scene heading.'},
                        'presentation': {'style': 'CURRENT_RENDERER_ASS', 'start_seconds': start/fps,
                                         'end_seconds': min(cursor/fps, start/fps+3)},
                        'treatment': {'design_tokens_ref': binding['tokens_ref']},
                        'motion': {'decision': 'NO_MOTION', 'purpose': 'Retain title readability.'},
                        'extensions': {'project_plan': {**tag['project_plan'], 'key': shot_key+'/title'}}})
                    layers.append(title)
                cue = _object(tx, 'CUE', shot_key+'/show', {'timing_source': {'master_voice': _aref(voice), 'timing_map': _aref(timing)},
                    'semantic_trigger': {'type': 'PHRASE_ANCHOR', 'anchor_id': vb['id'], 'offset_seconds': (start-scene['start_frame'])/fps},
                    'action': {'type': 'SHOW'}, 'target_layer_refs': layers,
                    'animation': {'start_offset_seconds': 0., 'key_offset_seconds': 0., 'end_offset_seconds': 0.},
                    'extensions': {'project_plan': {**tag['project_plan'], 'key': shot_key+'/show'}}})
                shot = _object(tx, 'SHOT', shot_key, {'scene_ref': m['scene_ref'], 'order': order,
                    'beat_bindings': [{'beat_ref': m['beat_ref'], 'role': 'PRIMARY'}],
                    'visual_job': beat['visual_requirement'].get('visual_job') or next(s['visual'] for s in edit['scenes'] if s['id'] == key),
                    'viewer_takeaway': beat.get('viewer_takeaway') or beat['idea']['summary'],
                    'visual_strategy': 'DIRECT_EVIDENCE' if cut['visual_review']['match_type'] == 'DIRECT' else 'CONTEXTUAL_BROLL',
                    'timing': {'voice_lock_manifest': _aref(lock), 'timing_map': _aref(timing),
                        'start': {'type': 'ABSOLUTE_MASTER_TIME', 'seconds': start/fps},
                        'end': {'type': 'ABSOLUTE_MASTER_TIME', 'seconds': cursor/fps}},
                    'layer_refs': layers, 'cue_refs': [cue], 'transition_out': {'type': 'CUT'},
                    'review_class': {'value': 'CRITICAL' if beat['visual_requirement'].get('priority') == 'CRITICAL' else 'STANDARD',
                                     'derivation': 'Current visual requirement priority; full-film review remains required.'},
                    'extensions': tag})
                shots.append({'shot_ref': shot})
            prior = plan_refs[key]
            tx.create_artifact_version(prior['artifact_id'], base_version=prior['version'], payload_patch={'shots': shots},
                origin_refs=[m['scene_ref'], _aref(lock), binding['design_ref'], binding['tokens_ref'], *[s['shot_ref'] for s in shots]])
        tx.commit(); tx = engine.begin(); tx.transition_project_state('SHOT_PLAN_READY', actor_type='AI'); tx.commit()
        _verify_design_files(project, edit)
        for scene in check['timeline']['timeline']:
            asset_file(project, scene['voice'], 'voice')
            for cut in scene['cuts']: asset_file(project, cut, 'footage')
        _persist(project, engine)
        return {**_inspect(project, edit, ProductionProject(project)._load()), 'idempotent_replay': False}
