"""Assess actual used pictures against current beats and measured scratch voice.

Library selection can be explicitly closed by a human with a reason. This is
not a declaration of exhaustive internet research, rights or final-film approval.
"""
from copy import deepcopy
import json
import math
import subprocess
from types import SimpleNamespace
from jsonschema import Draft202012Validator

from gmk_qa import QARuntime
from gmk_runtime.persistence import RuntimeStore

from .edit import EditError, EditSession, asset_file, fingerprint, probe
from .media_bridge import MEDIA_EDITABLE_STATES, _pools, media_binding_status, media_input, owned_media_recon
from .media_review import shot_review_current, voice_input, voice_review_current
from .production import ProductionProject, RUNTIME_ROOT
from .production_bridge import _active, binding_status
from .storage import StorageError, atomic_json


RULES = {'version': '1.0.0', 'duration_basis': 'SCRATCH_VOICE',
         'semantic_matches': ['DIRECT', 'SUPPORTING'],
         'duration': 'frame-conformed used ranges bounded by the first video stream, union by byte hash; explicit final-frame hold separately disclosed',
         'requires_current_picture_and_listening_reviews': True,
         'rights_and_exhaustive_search_certification': False}


def _validate_profile(engine, name, payload):
    sid = 'gmk://schema/v1/qa-profile/'+name
    validator = Draft202012Validator(engine.structural.schemas[sid], registry=engine.structural.registry)
    error = next(validator.iter_errors(payload), None)
    if error: raise EditError('ผลตรวจไม่ตรงโครงสร้างข้อมูลผลิต: '+error.message)


def _ref(o):
    return {'id': o['id'], 'version': o['version']}


def _aref(a):
    return {k: a[k] for k in ('artifact_id', 'artifact_type', 'version', 'sha256')}


def _reports(state):
    return [o for o in _active(state).values() if o['object_type'] == 'QA_REPORT'
            and o.get('extensions', {}).get('project_coverage')]


def retire_coverage(tx, *, include_final=True):
    """Archive our superseded assessments/issues; never claim their repair.

    Run in the same transaction as the explicit upstream revision or retest.
    Historical exact decisions remain available and foreign QA is untouched.
    """
    for obj in _active(tx.staged).values():
        if obj['object_type'] in {'QA_REPORT', 'QA_ISSUE'} and obj.get('extensions', {}).get('project_coverage'):
            tx.archive_object(obj['id'])
    if include_final:
        from .final_production import retire_final
        retire_final(tx)


def prepare_coverage_reentry(engine):
    tx = engine.begin(); retire_coverage(tx)
    if tx.actions: tx.commit()
    else: tx.discard()


def coverage_input(edit, state):
    return {'rules_sha256': fingerprint(RULES), 'media': media_input(edit), 'fps': edit['fps'],
            'scenes': [{'id': s['id'], 'voice': voice_input(s),
                        'listening_review': {k: (s.get('voice') or {}).get(k) for k in ('listening_review', 'review_input_sha256')},
                        'hold': s['hold_last_frame']}
                       for s in edit['scenes'] if s['included']],
            'independent_coverage_reviews': [{'ref': _ref(q), 'result': q['result'], 'status': q['status'], 'stale': q.get('stale')}
                for q in sorted(_active(state).values(), key=lambda o: o['id'])
                if q['object_type'] == 'QA_REPORT' and q.get('report_type') == 'ASSET_COVERAGE_REPORT'
                and not q.get('extensions', {}).get('project_coverage')],
            'receipts': [_aref(p) for _, p in sorted(_pools(state).items())
                         if not p['extensions']['project_media'].get('retired')]}


def coverage_binding_status(project, state, *, edit=None, media_status=None):
    reports = [q for q in _reports(state) if q['report_type'] == 'ASSET_COVERAGE_REPORT']
    report = max(reports, key=lambda q: (q['evaluated_at'], q['id'])) if reports else None
    if edit is None:
        try: edit = json.loads((project.root/'edit.json').read_text(encoding='utf-8'))
        except (OSError, ValueError): edit = None
    ext = report.get('extensions', {}).get('project_coverage', {}) if report else {}
    current = bool(report and edit and ext.get('input_sha256') == fingerprint(coverage_input(edit, state))
                   and (media_status if media_status is not None else media_binding_status(project, state, edit=edit))['current']
                   and not report.get('stale', {}).get('is_stale')
                   and report['status'] not in {'STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED'})
    if current:
        # Voice is outside the draft media registration: verify its exact bytes.
        checked = set()
        for scene in edit['scenes']:
            if not scene['included'] or not scene.get('voice'): continue
            key = (scene['voice']['path'], scene['voice']['sha256'])
            if key in checked: continue
            checked.add(key)
            try: asset_file(project, scene['voice'], 'voice')
            except (OSError, StorageError): current = False
    return {'connected': bool(report), 'current': current,
            'ready': current and report['result'] == 'PASS',
            'result': report['result'] if current else 'PENDING',
            'report_ref': _ref(report) if report else None,
            'selection_closed': current and ext.get('selection_closed', False),
            'rights_cleared': False, 'documentary_completed': False,
            'reason': ('ภาพที่ใช้ตรงข้อกำหนดและครอบคลุมความยาวเสียงตามตัวเลือกของฉาก' if current and report['result'] == 'PASS'
                       else 'ยังขาดภาพหรือเสียงที่พร้อม' if current else 'ต้องตรวจความครอบคลุมภาพจากข้อมูลรุ่นปัจจุบัน')}


def unique_seconds(ranges):
    total = 0.
    for intervals in ranges.values():
        end = -1.
        for a, b in sorted(intervals):
            total += max(0., b-max(a, end)); end = max(end, b)
    return total


def _inspect(project, edit, loaded):
    state = loaded.engine.snapshot(); live = _active(state)
    story = binding_status(project, state); media = media_binding_status(project, state, edit=edit)
    issues, scenes, inputs, origins = [], [], [], []
    can_record = owned_media_recon(state) and media['current'] and story['current']
    if not can_record:
        issues.append({'code': 'CURRENT_MEDIA_BINDING_REQUIRED', 'scene_id': None,
                       'detail': 'ตรวจและเชื่อมบทกับฟุตเทจรุ่นปัจจุบันก่อนบันทึกผลตรวจภาพ', 'action': 'PRODUCTION_MEDIA'})
    pools = _pools(state); cache = {}
    def inspect_file(ref, role):
        key = (ref['path'], ref['sha256'], role)
        if key not in cache: cache[key] = probe(asset_file(project, ref, role))
        inputs.append({'file': {'path': ref['path'], 'sha256': ref['sha256']}, 'role': role})
        return cache[key]
    for scene in edit['scenes']:
        if not scene['included']: continue
        sid = scene['id']; row_issues = []; required = frames = 0; ranges = {}; matches = []; cuts = []
        def issue(code, detail, action):
            row_issues.append({'code': code, 'scene_id': sid, 'detail': detail, 'action': action})
        try:
            voice = scene.get('voice')
            if not voice or voice.get('text_sha256') != fingerprint(scene['narration']):
                raise EditError('ต้องมีเสียงพากย์ที่ตรงกับบทเพื่อวัดความยาว')
            info = inspect_file(voice, 'voice')
            if not any(s['codec_type'] == 'audio' for s in info['streams']) or not math.isfinite(info['duration_seconds']) or info['duration_seconds'] <= 0:
                raise EditError('ไฟล์เสียงไม่มีแทร็กหรือความยาวที่ใช้ได้')
            frames = math.ceil(info['duration_seconds']*edit['fps']); required = frames/edit['fps']
            if not voice_review_current(scene): issue('VOICE_LISTENING_REVIEW_REQUIRED', 'ต้องฟังและตรวจเสียงพากย์รุ่นนี้', 'VOICE')
        except (OSError, ValueError, KeyError, StorageError, subprocess.SubprocessError) as exc:
            issue('MEASURED_VOICE_REQUIRED', str(exc), 'VOICE')
        pool = pools.get(sid); rows = {r['shot_id']: r for r in pool['extensions']['project_media']['rows']} if pool else {}
        if pool: origins.append(_aref(pool))
        beat = story.get('scene_map', {}).get(sid, {}).get('beat_ref')
        if beat: origins.append(beat)
        remaining = frames
        for cut in scene['shots']:
            registered = rows.get(cut['id']); valid_match = False
            try:
                info = inspect_file(cut, 'footage')
                video = next((v for v in info['streams'] if v['codec_type'] == 'video'), None)
                duration = info['duration_seconds']
                if video:
                    try: stream_duration = float(video.get('duration', duration))
                    except (ValueError, TypeError): stream_duration = duration
                    if math.isfinite(stream_duration) and stream_duration > 0: duration = min(duration, stream_duration)
                if not video or not 0 <= cut['in_seconds'] < cut['out_seconds'] <= duration+.05:
                    raise EditError('ช่วงภาพไม่อยู่ในไฟล์จริง')
                if not registered: raise EditError('ช็อตนี้ยังไม่ตรงรายการภาพในข้อมูลผลิต')
                seg = live.get(registered['segment_ref']['id'])
                valid_match = (shot_review_current(scene, cut) and seg and seg['version'] == registered['segment_ref']['version']
                               and seg['production_state'] == 'VERIFIED' and seg['match_type'] in RULES['semantic_matches'])
                available = max(0, math.floor((min(cut['out_seconds'], duration)-cut['in_seconds'])*edit['fps']+1e-6))
                take = min(available, remaining); remaining -= take
                if take:
                    end = cut['in_seconds']+take/edit['fps']
                    cuts.append({'shot_id': cut['id'], 'file': registered['file'], 'source_in_seconds': cut['in_seconds'],
                                 'used_source_out_seconds': end, 'frames': take,
                                 'match_type': cut.get('visual_review', {}).get('match_type'), 'semantic_ready': bool(valid_match),
                                 'segment_ref': registered['segment_ref']})
                    ranges.setdefault(cut['sha256'], []).append((cut['in_seconds'], end))
                    if valid_match: matches.append(seg['match_type'])
                    else: issue('SEMANTIC_VISUAL_GAP', cut['id']+': ภาพที่ใช้ยังไม่ยืนยันว่าตรงสิ่งที่บทต้องการเห็น', 'SHOT_REVIEW')
                origins.extend(registered[k] for k in ('asset_ref', 'segment_ref', 'result_ref', 'search_ref'))
            except (OSError, ValueError, KeyError, StorageError, subprocess.SubprocessError) as exc:
                issue('USABLE_FOOTAGE_REQUIRED', cut['id']+': '+str(exc), 'FOOTAGE')
        unique = unique_seconds(ranges)
        held = remaining/edit['fps'] if cuts and scene['hold_last_frame'] else 0.
        repeated = max(0., sum(b-a for values in ranges.values() for a, b in values)-unique)
        if not cuts: issue('SELECTED_VISUAL_REQUIRED', 'ยังไม่มีช่วงภาพที่ใช้ในฉากนี้', 'FOOTAGE')
        if frames and remaining and not held: issue('VISUAL_DURATION_GAP', f'ภาพยังขาด {remaining/edit["fps"]:.2f} วินาที เพิ่มภาพหรือระบุการค้างเฟรมท้ายโดยตั้งใจ', 'FOOTAGE')
        if repeated > 1e-6:
            issue('REPEATED_VISUAL_DURATION', f'ช่วงภาพจริงไม่ซ้ำมี {unique:.2f} จากที่ต้องใช้ {required:.2f} วินาที', 'FOOTAGE')
        semantic = ('DIRECT_COVERED' if matches and all(x == 'DIRECT' for x in matches) else 'SUPPORTING_COVERED') if cuts and all(c['semantic_ready'] for c in cuts) else 'PARTIAL' if matches else 'UNRESOLVED'
        scenes.append({'scene_id': sid, 'title': scene['title'], 'beat_ref': beat, 'visual_requirement': scene['visual'],
                       'ready': not row_issues and bool(beat), 'semantic': semantic, 'required_seconds': required,
                       'unique_visual_seconds': unique, 'missing_seconds': max(0., required-unique-held),
                       'held_seconds': held, 'repeated_seconds': repeated,
                       'cuts': cuts, 'issues': row_issues})
        issues.extend(row_issues)
    # Our report must not silently replace an unresolved independent coverage
    # assessment. The general gate can select a newer report; this adapter
    # explicitly preserves reviewers' decisions within the selected scope.
    scope_ids = {o['id'] for o in live.values() if o['object_type'] == 'PROJECT'}
    scope_ids.update(s['beat_ref']['id'] for s in scenes if s['beat_ref'])
    scope_ids.update(r['id'] for r in origins if 'id' in r)
    for obj in live.values():
        if (obj['object_type'] == 'QA_REPORT' and obj.get('report_type') == 'ASSET_COVERAGE_REPORT'
                and not obj.get('extensions', {}).get('project_coverage')
                and obj.get('scope', {}).get('id') in scope_ids
                and (obj.get('result') != 'PASS' or obj['status'] in {'STALE', 'BLOCKED', 'REJECTED'}
                     or obj.get('stale', {}).get('is_stale'))):
            origins.append(_ref(obj))
            issues.append({'code': 'INDEPENDENT_COVERAGE_REVIEW_PENDING', 'scene_id': None,
                           'detail': 'มีผลตรวจภาพจากขั้นตอนอื่นค้างอยู่ ต้องจัดการก่อนหยุดค้นภาพ: '+obj['id'],
                           'action': 'COVERAGE'})
    if not scenes: issues.append({'code': 'INCLUDED_SCENE_REQUIRED', 'scene_id': None, 'detail': 'เลือกฉากก่อนตรวจภาพ', 'action': 'SCRIPT'})
    return {'can_record': can_record, 'ready': can_record and not issues, 'issues': issues, 'scenes': scenes,
            'profile_payload': {'beats': [{'beat_ref': s['beat_ref'], 'semantic': {'state': s['semantic']},
                'duration': {'basis': 'SCRATCH_VOICE', 'required_seconds': s['required_seconds'], 'unique_visual_seconds': s['unique_visual_seconds']},
                'production_ready_segment_refs': [c['segment_ref'] for c in s['cuts'] if c['semantic_ready']]} for s in scenes if s['beat_ref']]},
            'input_sha256': fingerprint(coverage_input(edit, state)), 'edit_sha256': fingerprint(edit),
            'manifest_sha256': loaded.manifest_sha256, 'production_state': state.project_state,
            'inputs': inputs, 'origin_refs': origins, 'binding': coverage_binding_status(project, state, edit=edit),
            'search_scope': 'HUMAN_REVIEWED_PROJECT_LIBRARY', 'rights_cleared': False, 'documentary_completed': False}


def inspect_coverage(project):
    EditSession(project).load()
    with project._lock():
        return _inspect(project, EditSession(project).load(), ProductionProject(project)._load())


def _planning_segments(engine, check):
    """Connect the measured, reviewed used segments to existing planning engines.

    These are registered local copies, with UNKNOWN rights/source independence.
    No acquisition Operation or assertion of origin-server bytes is introduced.
    """
    tx = engine.begin(); state = engine.snapshot(); live = _active(state)
    for scene in check['scenes']:
        pool = _pools(state)[scene['scene_id']]; ext = pool['extensions']['project_media']
        used = {c['shot_id'] for c in scene['cuts'] if c['semantic_ready']}; rows = deepcopy(ext['rows'])
        for row in rows:
            ready = row['shot_id'] in used
            asset = live[row['asset_ref']['id']]; segment = live[row['segment_ref']['id']]
            acq = {'batch_id': 'PROJECT_COVERAGE_'+check['input_sha256'][:20].upper(),
                   'representation': 'REGISTERED_PROJECT_LIBRARY', 'origin_bytes': False,
                   'production_ready': ready, 'verified_sha256': row['file']['sha256'],
                   'acquisition_method': 'EXISTING_PROJECT_LIBRARY',
                   'production_ready_basis': 'CURRENT_LOCAL_BYTES_AND_EXPLICIT_VISUAL_REVIEW_NOT_RIGHTS_CLEARANCE'}
            asset_ext = {**asset.get('extensions', {}),
                         'asset_recon': {'beat_key': scene['scene_id'], 'production_ready': ready}, 'asset_acquisition': acq}
            aref = tx.create_version(asset['id'], base_version=asset['version'], patch={'extensions': asset_ext})
            tx.promote_active_version(aref['id'], aref['version'])
            sref = tx.create_version(segment['id'], base_version=segment['version'], patch={
                'asset_ref': aref, 'extensions': {**segment.get('extensions', {}), 'asset_acquisition': acq}})
            tx.promote_active_version(sref['id'], sref['version'])
            row.update(asset_ref=aref, segment_ref=sref)
        payload = {'entries': deepcopy(rows), 'extensions': {'project_media': {**ext, 'rows': rows}}}
        # Retain the actual Scene/Beat/Search dependencies and replace the exact
        # media versions consumed by this receipt.
        source_refs = [r for r in pool['origin_refs'] if r.get('id') not in {live[x[k]['id']]['id'] for x in ext['rows'] for k in ('asset_ref', 'segment_ref')}]
        tx.create_artifact_version(pool['artifact_id'], base_version=pool['version'], payload_patch=payload,
                                   origin_refs=[*source_refs, *[r[k] for r in rows for k in ('asset_ref', 'segment_ref')]])
    tx.commit()


def record_coverage(project, *, expected_edit_sha256, expected_manifest_sha256, complete_selection=False, stop_reason=''):
    if not isinstance(complete_selection, bool): raise EditError('ระบุการหยุดค้นเป็นค่าจริงหรือเท็จ')
    reason = stop_reason.strip()
    if complete_selection and not reason: raise EditError('ระบุเหตุผลที่เลือกภาพในคลังนี้และหยุดค้น')
    production = ProductionProject(project); EditSession(project).load()
    with project._lock():
        edit = EditSession(project).load(); loaded = production._load(); engine = loaded.engine
        if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
            raise EditError('ภาพ เสียง หรือหลักฐานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจใหม่')
        check = _inspect(project, edit, loaded)
        if not check['can_record']: raise EditError('เชื่อมบทและภาพรุ่นปัจจุบันก่อนบันทึกผลตรวจความครอบคลุม')
        if complete_selection and not check['ready']: raise EditError('ยังหยุดค้นและผ่านขั้นภาพไม่ได้: '+'; '.join(i['detail'] for i in check['issues']))
        existing = next((q for q in _reports(engine.snapshot()) if q['report_type'] == 'ASSET_COVERAGE_REPORT'
                         and q['extensions']['project_coverage']['input_sha256'] == check['input_sha256']), None)
        if check['binding']['current'] and (not complete_selection or (existing['extensions']['project_coverage'].get('selection_closed')
                and existing['extensions']['project_coverage'].get('stop_reason') == reason)):
            return {**check, 'idempotent_replay': True}
        tx = engine.begin(); retire_coverage(tx)
        if engine.project_state in {'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY', 'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED'}:
            tx.reenter_stage('ASSET_RECON', actor_type='HUMAN')
        if tx.actions: tx.commit()
        else: tx.discard()
        if complete_selection:
            _planning_segments(engine, check)
            check = _inspect(project, edit, SimpleNamespace(engine=engine, manifest_sha256=loaded.manifest_sha256))
            if not check['ready']: raise EditError('ข้อมูลภาพเปลี่ยนระหว่างเตรียมฉาก กรุณาตรวจใหม่')
        _write_assessment(engine, check, complete_selection, reason)
        if complete_selection:
            for stage in ('ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY'):
                tx = engine.begin(); tx.transition_project_state(stage, actor_type='AI'); tx.commit()
        # Last byte check and a single publication keep failed staging off disk.
        for item in check['inputs']: asset_file(project, item['file'], item['role'])
        RuntimeStore(RUNTIME_ROOT, production.workspace).persist(engine)
        final = production._load(); data = project.read(); data['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, data)
        return {**check, 'production_state': engine.project_state, 'manifest_sha256': final.manifest_sha256,
                'binding': coverage_binding_status(project, final.engine.snapshot(), edit=edit), 'idempotent_replay': False}


def _write_assessment(engine, check, complete_selection=False, reason=''):
    _validate_profile(engine, 'asset-coverage', check['profile_payload'])
    # Capture a genuine assessment. Failed checks create genuine open QA
    # issues; a new upstream revision archives the obsolete assessment.
    snapshot = engine.snapshot(); project_ref = _ref(next(o for o in _active(snapshot).values() if o['object_type'] == 'PROJECT'))
    tx = engine.begin()
    artifact = tx.create_artifact('PROVENANCE_MANIFEST', {'entries': deepcopy(check['scenes']),
        'disclosures': ['Measured scratch voice and explicitly reviewed used frames; repeated ranges and explicitly selected held frames do not add unique footage.',
                        'No rights clearance or exhaustive external-source search is certified.'],
        'extensions': {'project_coverage': {'input_sha256': check['input_sha256'], 'rules': RULES,
                        'profile_payload': check['profile_payload'], 'inputs': check['inputs']}}}, origin_refs=check['origin_refs'])
    tx.commit()
    findings = [{'severity': 'MAJOR', 'code': i['code'], 'target': next((s['beat_ref'] for s in check['scenes'] if s['scene_id'] == i['scene_id']), project_ref),
                 'description': i['detail'], 'root_cause': {'state': 'IDENTIFIED', 'category': 'ASSET'}} for i in check['issues']]
    qa = QARuntime(engine).evaluate(report_type='ASSET_COVERAGE_REPORT', scope=project_ref, observed_artifact=artifact,
        qa_profile={'config_id': 'GMK_PROJECT_ASSET_COVERAGE', 'version': '1.0.0', 'sha256': fingerprint(RULES)}, findings=findings)
    ext = {'project_coverage': {'input_sha256': check['input_sha256'], 'selection_closed': complete_selection,
                               'stop_reason': reason if complete_selection else '', 'assessment_ref': artifact}}
    tx = engine.begin()
    issue_refs = []
    for issue in qa['issue_refs']:
        updated = tx.create_version(issue['id'], base_version=issue['version'], patch={'extensions': ext})
        tx.promote_active_version(updated['id'], updated['version'])
        issue_refs.append(updated)
    report = tx.create_version(qa['report_ref']['id'], base_version=qa['report_ref']['version'],
                               patch={'extensions': ext, 'issue_refs': issue_refs})
    tx.promote_active_version(report['id'], report['version'])
    tx.commit()
    if complete_selection:
        # The certificate explicitly records HUMAN_STOP_WITH_REASON for the
        # already completed project-library searches, not internet exhaustion.
        pools = _pools(engine.snapshot())
        decisions = [{'target_beat_ref': s['beat_ref'], 'priority': 'STANDARD',
                      'search_refs': [pools[s['scene_id']]['extensions']['project_media']['search_ref']],
                      'viable_candidate_refs': [], 'stop_reason': 'HUMAN_STOP_WITH_REASON',
                      'reason': reason, 'scope': 'HUMAN_REVIEWED_PROJECT_LIBRARY'} for s in check['scenes']]
        for decision in decisions:
            _validate_profile(engine, 'search-completion', {k: v for k, v in decision.items() if k not in {'reason', 'scope'}})
        cert = QARuntime(engine).evaluate(report_type='SEARCH_COMPLETION_CERTIFICATE', scope=project_ref,
            observed_artifact=artifact, qa_profile={'config_id': 'GMK_PROJECT_LIBRARY_HUMAN_STOP', 'version': '1.0.0',
                                                  'sha256': fingerprint({'scope': check['search_scope'], 'decisions': decisions})})
        tx = engine.begin()
        cr = tx.create_version(cert['report_ref']['id'], base_version=cert['report_ref']['version'], patch={
            'extensions': {**ext, 'project_library_stop': {'decisions': decisions, 'reason': reason}}})
        tx.promote_active_version(cr['id'], cr['version']); tx.commit()
