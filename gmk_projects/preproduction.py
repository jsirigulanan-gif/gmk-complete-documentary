"""Human review and production locks for the exact general-project edit.

HTML pages expose source intervals and the approved master voice. They are
planning reviews, not assembled films or Shot/Scene/Full-film QA certificates.
Every mutation is staged in the frozen StateEngine and persisted only once.
"""
from copy import deepcopy
from html import escape
import json
import os
from pathlib import Path
import tempfile

from gmk_production import ProductionLockRuntime, ProductionLockStageRuntime

from .design_planning import design_binding_status, plan_binding_status, _persist
from .edit import EditError, EditSession, asset_file, fingerprint
from .final_production import _aref, _ref, _heads, final_binding_status, master_file
from .production import ProductionProject, RUNTIME_ROOT
from .production_bridge import _active
from .research import _research_review
from .storage import StorageError, digest, relative_path


STATES = {'SHOT_PLAN_READY', 'HTML_REVIEW', 'HTML_APPROVED', 'PRODUCTION_RENDER'}
PRELOCK_STATES = STATES - {'PRODUCTION_RENDER'}
ARTIFACTS = {'SCENE_PREVIEW', 'REVIEW_PACKAGE', 'PRODUCTION_LOCK_REVIEW_PACKAGE', 'PRODUCTION_LOCK_MANIFEST'}
RENDER_ARTIFACTS = {'RENDERER_PROMPT', 'RENDER_OUTPUT'}
CLASSES = {'SCENE_PREVIEW', 'SHOT_VISUAL', 'PRODUCTION_LOCK'}


def _tag(obj):
    return obj.get('extensions', {}).get('project_review') or obj.get('extensions', {}).get('project_render') or {}


def _records(state):
    return [a for a in _heads(state) if a['artifact_type'] in ARTIFACTS | RENDER_ARTIFACTS] + [
        o for o in _active(state).values() if o['object_type'] in {'RENDER_JOB', 'RENDER_MANIFEST'}
        or (o['object_type'] == 'APPROVAL' and o['approval_class'] in CLASSES)]


def owns_review(state):
    return all(_tag(o) for o in _records(state))


def retire_review(tx):
    if not owns_review(tx.staged): raise EditError('มีข้อมูลตรวจแผนหรือล็อกการผลิตจากระบบอื่น ต้องย้ายข้อมูลก่อน')
    for obj in _records(tx.staged):
        if not _tag(obj) or _tag(obj).get('retired'): continue
        if 'artifact_id' in obj:
            namespace = 'project_render' if obj.get('extensions', {}).get('project_render') else 'project_review'
            tx.create_artifact_version(obj['artifact_id'], base_version=obj['version'],
                                       payload_patch={'extensions': {namespace: {'retired': True}}})
        else: tx.archive_object(obj['id'])


def _live(state, kind):
    return [a for a in _heads(state, kind) if _tag(a) and not _tag(a).get('retired')]


def review_input(edit, state):
    plans = _live_plans(state)
    active = _active(state)
    refs = [row['shot_ref'] for p in plans for row in p['shots']]
    shots = [active.get(r['id']) for r in refs]
    return {'version': 1, 'edit_sha256': fingerprint(edit), 'plans': [_aref(p) for p in plans],
            'shots': refs, 'layers': [r for s in shots if s for r in s['layer_refs']],
            'cues': [r for s in shots if s for r in s['cue_refs']]}


def _live_plans(state):
    return sorted((p for p in _heads(state, 'SCENE_PLAN')
                   if p.get('extensions', {}).get('project_plan') and not p['extensions']['project_plan'].get('retired')),
                  key=lambda p: p['extensions']['project_plan']['key'])


def _eligible(obj):
    return not obj.get('stale', {}).get('is_stale') and obj['status'] not in {'STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED'}


def review_file(project, record):
    workspace = ProductionProject(project).workspace
    path = workspace/relative_path(record['path'])
    if (path.is_symlink() or not path.resolve().is_relative_to(workspace) or not path.is_file()
            or digest(path)['sha256'] != record['sha256']):
        raise EditError('ไฟล์ตรวจแผนหายหรือเปลี่ยน ต้องเตรียมและตรวจใหม่')
    return path


def _verify_media(project, edit):
    for scene in edit['scenes']:
        if not scene['included']: continue
        asset_file(project, scene['voice'], 'voice')
        if scene['voice'].get('subtitles'): asset_file(project, scene['voice']['subtitles'], 'voice')
        for cut in scene['shots']: asset_file(project, cut, 'footage')
    if edit.get('music'): asset_file(project, edit['music'], 'music')


def review_binding_status(project, state, *, edit=None, plan_status=None):
    if edit is None:
        try: edit = json.loads((project.root/'edit.json').read_text())
        except (OSError, ValueError): edit = None
    plan = plan_status if plan_status is not None else plan_binding_status(project, state, edit=edit)
    plans = _live_plans(state); previews = _live(state, 'SCENE_PREVIEW'); packages = _live(state, 'REVIEW_PACKAGE')
    signature = fingerprint(review_input(edit, state)) if edit else None
    current = bool(edit and state.project_state in STATES and plan['shot_plan_ready'] and owns_review(state)
                   and len(previews) == len(packages) == len(plans) > 0)
    by_key = {_tag(a)['key']: a for a in previews}; approvals = _active(state).values()
    decisions = []; indexes = []
    for p in plans:
        key = p['extensions']['project_plan']['key']; pv = by_key.get(key)
        rp = next((a for a in packages if _tag(a)['key'] == key), None)
        if not pv or not rp: current = False; continue
        if (_tag(pv).get('input_sha256') != signature or _tag(rp).get('input_sha256') != signature
                or pv['scene_plan'] != _aref(p) or rp['scene_preview'] != _aref(pv)
                or rp['scene_plan'] != _aref(p) or pv['shots'] != [r['shot_ref'] for r in p['shots']]
                or rp['shots'] != pv['shots']): current = False
        indexes.append(_tag(pv)['index'])
        try:
            review_file(project, _tag(pv)['page']); review_file(project, _tag(pv)['index'])
        except (OSError, StorageError): current = False
        exact = [a for a in approvals if a['object_type'] == 'APPROVAL' and a['approval_class'] == 'SCENE_PREVIEW'
                 and a['target'] == _aref(pv) and a.get('review_context') == _aref(rp) and _eligible(a)]
        decisions.append('REJECTED' if any(a['decision'] == 'REJECTED' for a in exact) else
                         'APPROVED' if any(a['decision'] == 'APPROVED' for a in exact) else None)
    if current:
        try: _verify_media(project, edit)
        except (OSError, StorageError): current = False
    rejected = current and 'REJECTED' in decisions
    approved = bool(current and state.project_state in {'HTML_APPROVED', 'PRODUCTION_RENDER'}
                    and decisions and all(d == 'APPROVED' for d in decisions))
    return {'connected': bool(previews), 'current': current, 'approved': approved,
            'decision': 'REJECTED' if rejected else 'APPROVED' if approved else None,
            'index': indexes[0] if indexes and all(i == indexes[0] for i in indexes) else None,
            'input_sha256': signature, 'scene_count': len(previews),
            'reason': 'ตรวจแผนทุกฉากและยืนยันรุ่นปัจจุบันแล้ว' if approved else
                      'แผนยังต้องแก้ — กลับไปแก้แผนแล้วตรวจใหม่' if rejected else
                      'รอเปิดแผนทุกฉากและยืนยัน' if current else 'ต้องเตรียมหน้าตรวจแผนจากช็อตรุ่นปัจจุบัน'}


def lock_binding_status(project, state, *, edit=None, review_status=None):
    review = review_status if review_status is not None else review_binding_status(project, state, edit=edit)
    packages = _live(state, 'PRODUCTION_LOCK_REVIEW_PACKAGE'); locks = _live(state, 'PRODUCTION_LOCK_MANIFEST')
    pkg = packages[0] if len(packages) == 1 else None
    project_locks = [a for a in locks if a['scope']['type'] == 'PROJECT']
    lock = project_locks[0] if len(project_locks) == 1 else None
    current = bool(review['approved'] and pkg and _tag(pkg)['input_sha256'] == review['input_sha256'] and owns_review(state))
    if current:
        try:
            _, _, closure, sha = ProductionLockStageRuntime(RUNTIME_ROOT, ProductionProject(project).workspace)._closure(state)
            current = pkg['closure_sha256'] == sha and all(pkg[k] == v for k, v in closure.items())
        except RuntimeError: current = False
    approvals = [o for o in _active(state).values() if o['object_type'] == 'APPROVAL' and o['approval_class'] == 'PRODUCTION_LOCK'
                 and pkg and o.get('review_context') == _aref(pkg) and _eligible(o)]
    rejected = current and any(a['decision'] == 'REJECTED' for a in approvals)
    locked = bool(current and state.project_state == 'PRODUCTION_RENDER' and lock and not rejected
                  and _tag(lock)['input_sha256'] == review['input_sha256']
                  and set((r['artifact_id'], r['version']) for r in lock['scene_locks']) ==
                      set((a['artifact_id'], a['version']) for a in locks if a['scope']['type'] == 'SCENE')
                  and all(any(a['target'] == _aref(l) and a['decision'] == 'APPROVED' for a in approvals) for l in locks))
    if locked:
        try:
            # A fresh approval cannot make an invalidated lock executable.
            from gmk_state.errors import StateEngineError
            from types import SimpleNamespace
            runtime = ProductionLockRuntime(SimpleNamespace(root=RUNTIME_ROOT, snapshot=lambda: state))
            for item in locks: runtime.assert_valid(_aref(item))
        except StateEngineError: locked = False
    return {'current': bool(current), 'locked': locked, 'decision': 'REJECTED' if rejected else 'APPROVED' if locked else None,
            'review_ref': _aref(pkg) if pkg else None, 'production_lock_ref': _aref(lock) if lock else None,
            'closure_sha256': pkg['closure_sha256'] if pkg else None,
            'reason': 'ล็อกแผน ภาพ และเสียงรุ่นที่ตรวจแล้วสำหรับผลิต' if locked else
                      'รอยืนยันล็อกการผลิตจากแผนทุกฉากที่ผ่านตรวจ'}


def _inspect(project, edit, loaded):
    state = loaded.engine.snapshot(); final = final_binding_status(project, state, edit=edit)
    design = design_binding_status(project, state, edit=edit, final_status=final)
    plan = plan_binding_status(project, state, edit=edit, design_status=design)
    timeline = EditSession(project).preflight(edit, research=_research_review(project))
    review = review_binding_status(project, state, edit=edit, plan_status=plan)
    lock = lock_binding_status(project, state, edit=edit, review_status=review)
    issues = [x['detail'] for x in timeline['issues']]
    if state.project_state not in STATES: issues.append('เตรียมแผนช็อตขั้นผลิตให้ครบก่อนตรวจและล็อก')
    if not final['voice_locked'] or not design['approved'] or not plan['shot_plan_ready']:
        issues.append('แผน ภาพ หรือเสียงไม่ตรงรุ่นที่ยืนยัน ต้องกลับไปแก้ขั้นที่เกี่ยวข้อง')
    if not owns_review(state): issues.append('มีข้อมูลตรวจแผนหรือล็อกจากระบบอื่น ต้องย้ายข้อมูลก่อน')
    try: _verify_media(project, edit)
    except (OSError, StorageError) as exc: issues.append(str(exc))
    return {'ready': not issues, 'issues': issues, 'edit_sha256': fingerprint(edit),
            'manifest_sha256': loaded.manifest_sha256, 'production_state': state.project_state,
            'timeline': timeline, 'review_binding': review, 'lock_binding': lock, 'documentary_completed': False}


def inspect_preproduction(project):
    EditSession(project).load()
    with project._lock(): return _inspect(project, EditSession(project).load(), ProductionProject(project)._load())


def _tokens(project, expected_edit_sha256, expected_manifest_sha256):
    edit = EditSession(project).load(); loaded = ProductionProject(project)._load()
    if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
        raise EditError('งานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจแผนใหม่')
    return edit, loaded


def _artifact(tx, kind, key, payload, origins):
    old = [a for a in _heads(tx.staged, kind) if _tag(a).get('key') == key]
    if len(old) > 1: raise EditError('ข้อมูลตรวจแผนซ้ำ: '+key)
    if old: return tx.create_artifact_version(old[0]['artifact_id'], base_version=old[0]['version'], payload_patch=payload, origin_refs=origins)
    return tx.create_artifact(kind, payload, origin_refs=origins)


def _publish_html(project, content):
    folder = ProductionProject(project).workspace/'review'/'project'; folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=folder, prefix='.review-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream: stream.write(content)
        meta = digest(Path(name)); path = folder/(meta['sha256']+'.html')
        if path.is_symlink() or (path.exists() and digest(path) != meta): raise EditError('ไฟล์ตรวจแผนในคลังถูกแก้')
        if not path.exists(): os.link(name, path)
        return {'path': path.relative_to(ProductionProject(project).workspace).as_posix(), **meta}
    finally: Path(name).unlink(missing_ok=True)


def _html(title, body):
    return ('<!doctype html><html lang="th"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; media-src file:; img-src file:">'
            '<title>'+escape(title)+'</title><style>body{font:17px system-ui;max-width:1050px;margin:32px auto;padding:20px;background:#151719;color:#eee}'
            'article{border:1px solid #666;padding:16px;margin:20px 0}video,img{max-width:100%;max-height:340px}a{color:#8acbff}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            '<h1>'+escape(title)+'</h1>'+body+'</html>')


def prepare_review(project, *, expected_edit_sha256, expected_manifest_sha256):
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        check = _inspect(project, edit, loaded)
        if not check['ready']: raise EditError('; '.join(check['issues']))
        if check['review_binding']['current']: return {**check, 'idempotent_replay': True}
        if engine.project_state != 'SHOT_PLAN_READY' or any(_live(engine.snapshot(), k) for k in ARTIFACTS):
            raise EditError('กลับไปแก้แผนก่อนเตรียมการตรวจรุ่นใหม่')
        state = engine.snapshot(); signature = check['review_binding']['input_sha256']; rows = []
        master = next(a for a in _heads(state, 'MASTER_VOICE') if a.get('extensions', {}).get('project_final')
                      and not a['extensions']['project_final'].get('retired'))
        audio = escape(master_file(ProductionProject(project), master).as_uri(), quote=True)
        plans = {p['extensions']['project_plan']['key']: p for p in _live_plans(state)}
        for scene in check['timeline']['timeline']:
            body = '<p>แผนก่อนผลิต: ภาพต้นฉบับแต่ละช่วง ยังไม่ใช่วิดีโอทั้งเรื่อง</p><p>บทพากย์</p><pre>'+escape(scene['narration'])+'</pre>'
            body += f'<p>เวลาเสียง {scene["start_frame"]/edit["fps"]:.3f}–{(scene["start_frame"]+scene["frames"])/edit["fps"]:.3f} วินาที</p>'
            body += '<p>ชื่อฉาก: '+('แสดงเฉพาะช่วงแรก สูงสุด 3 วินาที' if scene['show_title'] else 'ไม่แสดง')+'</p>'
            for cut in scene['cuts']:
                uri = escape(asset_file(project, cut, 'footage').as_uri(), quote=True)
                body += (f'<article><h2>{escape(cut["id"])}</h2><video controls preload="metadata" src="{uri}#t={cut["in_seconds"]},{cut["out_seconds"]}"></video>'
                         f'<p>ต้นฉบับ {cut["in_seconds"]:.3f}–{cut["out_seconds"]:.3f} วินาที · ใช้ {cut["frames"]-cut["freeze_frames"]} เฟรม · ค้างท้าย {cut["freeze_frames"]} เฟรม</p>'
                         '<p>สถานะสิทธิ์: ยังไม่ได้รับการยืนยัน</p></article>')
            rows.append((scene, plans[scene['scene_id']], _publish_html(project, _html(scene['title'], body))))
        body = '<p>เปิดตรวจทุกฉาก ฟังเสียงรวม และกลับไปบันทึกผลใน GMK</p>'
        body += f'<audio controls preload="metadata" src="{audio}"></audio><p>เสียงรวม SHA256: {escape(master["audio"]["sha256"])}</p>'
        body += '<p>คำบรรยายและภาพเคลื่อนไหวต้องตรวจในวิดีโอทั้งเรื่องอีกครั้ง ดนตรีใช้ค่าที่ตรวจรูปแบบแล้ว</p>'
        body += f'<p>ภาพ {edit["width"]} × {edit["height"]} · {edit["fps"]} fps · ระดับดนตรี {edit["music_gain"]:.3f}</p>'
        if edit.get('music'): body += '<p>ดนตรี: '+escape(edit['music']['path'])+'</p>'
        else: body += '<p>ตั้งใจไม่ใช้ดนตรี</p>'
        for scene, plan, page in rows:
            body += '<p><a href="'+escape(Path(page['path']).name, quote=True)+'">'+escape(scene['title'])+'</a></p>'
        body += '<p>แผนรุ่น SHA256: '+signature+'</p>'
        index = _publish_html(project, _html(edit['title']+' — ตรวจแผนก่อนผลิต', body))
        tx = engine.begin()
        for scene, plan, page in rows:
            shots = [r['shot_ref'] for r in plan['shots']]
            tag = {'project_review': {'key': scene['scene_id'], 'input_sha256': signature, 'retired': False, 'page': page, 'index': index}}
            pv = _artifact(tx, 'SCENE_PREVIEW', scene['scene_id'], {'scene_ref': plan['scene_ref'], 'scene_plan': _aref(plan),
                'shots': shots, 'preview': {'format': 'HTML', 'workspace_path': page['path'], 'sha256': page['sha256'],
                                         'size_bytes': page['size'], 'purpose': 'HUMAN_SCENE_REVIEW'}, 'extensions': tag},
                [plan['scene_ref'], _aref(plan), *shots])
            _artifact(tx, 'REVIEW_PACKAGE', scene['scene_id'], {'scope': {'type': 'SCENE', 'scene_ref': plan['scene_ref']},
                'scene_preview': pv, 'scene_plan': _aref(plan), 'shots': shots, 'extensions': tag}, [pv, _aref(plan), *shots])
        tx.transition_project_state('HTML_REVIEW', actor_type='SYSTEM'); tx.commit()
        _verify_media(project, edit); master_file(ProductionProject(project), master)
        for _, _, page in rows: review_file(project, page)
        review_file(project, index); _persist(project, engine)
        return {**_inspect(project, edit, ProductionProject(project)._load()), 'idempotent_replay': False}


def _prior(state, classes, context=None):
    return [o for o in _active(state).values() if o['object_type'] == 'APPROVAL' and _tag(o)
            and o['approval_class'] in classes and (context is None or o.get('review_context') == context)]


def _decision_replay(prior, decision, actor_id):
    if not prior: return False
    if all(o['decision'] == decision and o['actor']['actor_id'] == actor_id for o in prior): return True
    raise EditError('มีผลตรวจแล้ว ต้องกลับไปแก้แผนและเตรียมรุ่นใหม่')


def decide_review(project, *, expected_edit_sha256, expected_manifest_sha256, decision, actor_id):
    if decision not in {'APPROVED', 'REJECTED'} or not actor_id.strip(): raise EditError('ระบุผลตรวจและชื่อผู้ตรวจแผนทุกฉาก')
    actor_id = actor_id.strip()
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        check = _inspect(project, edit, loaded); state = engine.snapshot()
        if not check['ready'] or not check['review_binding']['current']: raise EditError('หน้าตรวจแผนไม่ตรงงานปัจจุบัน')
        if _decision_replay(_prior(state, {'SCENE_PREVIEW'}), decision, actor_id): return {**check, 'idempotent_replay': True}
        if engine.project_state != 'HTML_REVIEW': raise EditError('ตรวจแผนได้ก่อนล็อกการผลิตเท่านั้น')
        tx = engine.begin()
        for pv in _live(state, 'SCENE_PREVIEW'):
            rp = next(a for a in _live(state, 'REVIEW_PACKAGE') if a['scene_preview'] == _aref(pv))
            tx.create_approval({'approval_class': 'SCENE_PREVIEW', 'target': _aref(pv), 'review_context': _aref(rp),
                'decision': decision, 'actor': {'type': 'HUMAN', 'actor_id': actor_id}, 'decided_at': engine.now(),
                'extensions': {'project_review': {'input_sha256': check['review_binding']['input_sha256']}}})
        if decision == 'APPROVED': tx.transition_project_state('HTML_APPROVED', actor_type='HUMAN', human_confirmed=True)
        tx.commit(); _persist(project, engine)
        return {**_inspect(project, edit, ProductionProject(project)._load()), 'idempotent_replay': False}


def prepare_lock(project, *, expected_edit_sha256, expected_manifest_sha256):
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        check = _inspect(project, edit, loaded)
        if not check['ready'] or not check['review_binding']['approved']: raise EditError('ยืนยันแผนทุกฉากก่อนเตรียมล็อกการผลิต')
        if check['lock_binding']['current']: return {**check, 'idempotent_replay': True}
        if engine.project_state != 'HTML_APPROVED' or _live(engine.snapshot(), 'PRODUCTION_LOCK_REVIEW_PACKAGE'):
            raise EditError('กลับไปแก้แผนก่อนเตรียมล็อกรุ่นใหม่')
        project_obj, pairs, closure, sha = ProductionLockStageRuntime(RUNTIME_ROOT, ProductionProject(project).workspace)._closure(engine.snapshot())
        tx = engine.begin()
        _artifact(tx, 'PRODUCTION_LOCK_REVIEW_PACKAGE', 'production', {'scope': {'type': 'PROJECT_PRODUCTION_LOCK', 'project_ref': _ref(project_obj)},
            **closure, 'closure_sha256': sha, 'review_summary': {'scene_count': len(pairs), 'shot_count': len(closure['shots']),
                'layer_count': len(closure['layers']), 'cue_count': len(closure['cues'])},
            'extensions': {'project_review': {'key': 'production', 'input_sha256': check['review_binding']['input_sha256'], 'retired': False}}},
            [_ref(project_obj), *[r for refs in closure.values() for r in refs]])
        tx.commit(); _persist(project, engine)
        return {**_inspect(project, edit, ProductionProject(project)._load()), 'idempotent_replay': False}


def decide_lock(project, *, expected_edit_sha256, expected_manifest_sha256, decision, actor_id):
    if decision not in {'APPROVED', 'REJECTED'} or not actor_id.strip(): raise EditError('ระบุผลตรวจและชื่อผู้ยืนยันล็อกการผลิต')
    actor_id = actor_id.strip()
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        check = _inspect(project, edit, loaded); state = engine.snapshot(); binding = check['lock_binding']
        if not check['ready'] or not binding['current']: raise EditError('ชุดตรวจล็อกไม่ตรงงานปัจจุบัน')
        prior = _prior(state, {'PRODUCTION_LOCK'}, binding['review_ref'])
        if _decision_replay(prior, decision, actor_id): return {**check, 'idempotent_replay': True}
        if engine.project_state != 'HTML_APPROVED': raise EditError('กลับไปแก้แผนก่อนเปลี่ยนผลตรวจล็อกการผลิต')
        _, pairs, closure, _ = ProductionLockStageRuntime(RUNTIME_ROOT, ProductionProject(project).workspace)._closure(state)
        signature = check['review_binding']['input_sha256']; pkgref = binding['review_ref']
        tag = {'project_review': {'input_sha256': signature, 'retired': False}}
        def approve(tx, cls, target, obj=None):
            payload = {'approval_class': cls, 'target': target, 'review_context': pkgref, 'decision': decision,
                       'actor': {'type': 'HUMAN', 'actor_id': actor_id}, 'decided_at': engine.now(), 'extensions': tag}
            if obj: payload['target_decision_sha256'] = engine.semantic.decision_hash(obj)
            return tx.create_approval(payload)
        tx = engine.begin()
        if decision == 'REJECTED': approve(tx, 'PRODUCTION_LOCK', pkgref)
        else:
            for ref in closure['shots']: approve(tx, 'SHOT_VISUAL', ref, state.objects[(ref['id'], ref['version'])])
        tx.commit()
        if decision == 'APPROVED':
            runtime = ProductionLockRuntime(engine); refs = []
            def identity(key):
                old = [a for a in _heads(engine.snapshot(), 'PRODUCTION_LOCK_MANIFEST') if _tag(a).get('key') == key]
                if len(old) > 1: raise EditError('ข้อมูลล็อกการผลิตซ้ำ: '+key)
                return old[0]['artifact_id'] if old else None
            for scene, plan, preview, shots in pairs:
                key = 'scene:'+scene['id']; lock_tag = deepcopy(tag); lock_tag['project_review']['key'] = key
                refs.append(runtime.create_scene_lock(voice_lock_ref=plan['voice_lock'], design_dna_ref=plan['design_dna_ref'],
                    scene_plan_ref=_aref(plan), scene_preview_ref=_aref(preview), shot_refs=[_ref(s) for s in shots],
                    extensions=lock_tag, artifact_id=identity(key)))
            lock_tag = deepcopy(tag); lock_tag['project_review']['key'] = 'project'
            project_lock = runtime.create_project_lock(scene_lock_refs=refs, extensions=lock_tag, artifact_id=identity('project'))
            tx = engine.begin()
            for ref in [*refs, project_lock]: approve(tx, 'PRODUCTION_LOCK', ref)
            tx.transition_project_state('PRODUCTION_RENDER', actor_type='HUMAN', human_confirmed=True); tx.commit()
        _verify_media(project, edit); _persist(project, engine)
        return {**_inspect(project, edit, ProductionProject(project)._load()), 'idempotent_replay': False}


def reopen_preproduction(project, *, expected_edit_sha256, expected_manifest_sha256):
    with project._lock():
        edit, loaded = _tokens(project, expected_edit_sha256, expected_manifest_sha256); engine = loaded.engine
        if engine.project_state not in STATES or not owns_review(engine.snapshot()): raise EditError('กลับไปแก้ได้เฉพาะการผลิตที่เชื่อมจากโปรเจกต์นี้')
        tx = engine.begin(); retire_review(tx)
        if engine.project_state != 'SHOT_PLAN_READY': tx.reenter_stage('SHOT_PLAN_READY', actor_type='HUMAN')
        tx.commit(); _persist(project, engine)
        return _inspect(project, edit, ProductionProject(project)._load())
