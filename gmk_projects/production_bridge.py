"""Compile reviewed editor scenes into the existing canonical production graph.

All decisions use StateEngine transactions and gates. The working edit stays a
draft; this bridge stops at visual requirements and grants no footage/film approval.
"""
from copy import deepcopy
import json

from gmk_narrative.runtime import RoughNarrativeRuntime
from gmk_narrative.visual_requirements import VisualRequirementsRuntime
from gmk_runtime.persistence import RuntimeStore

from .edit import EditError, EditSession, fingerprint
from .production import ProductionProject, RUNTIME_ROOT
from .research import _research_review
from .script_review import script_readiness
from .storage import atomic_json


EARLY_STATES = {'RESEARCH_INTAKE', 'RESEARCH_AUDITED', 'ROUGH_NARRATIVE_READY', 'VISUAL_REQUIREMENTS_READY',
                'ASSET_RECON', 'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY'}
ROLES = {'HOOK': ('HOOK', 'BUILD'), 'CONTEXT': ('SETUP', 'CALM'),
         'ESCALATION': ('ESCALATION', 'TENSE'), 'REVEAL': ('MAJOR_PEAK', 'REVEAL'),
         'RESOLUTION': ('REFLECTION', 'REFLECTIVE')}


def story_input(edit):
    """Media/timing changes do not silently revise the research-bound narrative."""
    fields = ('id', 'title', 'narration', 'visual', 'story_role', 'claim_refs', 'claim_review')
    return {**{key: edit.get(key, '') for key in ('title', 'central_question', 'narrative_arc')},
            'scenes': [{key: scene.get(key) for key in fields}
                       for scene in edit['scenes'] if scene['included']]}


def _spine(state):
    matches = [a for a in state.artifacts.values() if a.get('artifact_type') == 'NARRATIVE_SPINE'
               and a.get('extensions', {}).get('project_story')]
    identities = {a['artifact_id'] for a in matches}
    if len(identities) > 1:
        raise EditError('พบแกนเรื่องหลายชุดในโปรเจกต์ ต้องตรวจข้อมูลก่อนเชื่อมบท')
    return max(matches, key=lambda a: a['version']) if matches else None


def _active(state):
    return {oid: state.objects[(oid, entry.active_version)]
            for registry in state.registries.values() for oid, entry in registry.entries.items()
            if entry.active_version is not None}


def binding_status(project, state):
    spine = _spine(state)
    if spine is None:
        return {'connected': False, 'current': False, 'reason': 'ยังไม่ได้เชื่อมบทเข้าระบบผลิต'}
    binding = spine['extensions']['project_story']
    refs = binding['scene_map']
    try:
        edit = json.loads((project.root/'edit.json').read_text(encoding='utf-8'))
        current = fingerprint(story_input(edit)) == binding['input_sha256']
    except (OSError, ValueError, KeyError, TypeError):
        current = False
    active = _active(state)
    act_ref = binding['act_ref']
    act = active.get(act_ref['id'])
    if (not act or act['version'] != act_ref['version']
            or act.get('stale', {}).get('is_stale')
            or act.get('status') in ('STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED')):
        current = False
    for row in refs.values():
        for key in ('scene_ref', 'beat_ref'):
            obj = active.get(row[key]['id'])
            if (not obj or obj['version'] != row[key]['version']
                    or obj.get('stale', {}).get('is_stale')
                    or obj.get('status') in ('STALE', 'BLOCKED', 'ARCHIVED', 'REJECTED')):
                current = False
            if key == 'beat_ref' and obj:
                for claim_binding in obj.get('claim_bindings', []):
                    ref = claim_binding['claim_ref']; claim = active.get(ref['id'])
                    if (not claim or claim['version'] != ref['version']
                            or not claim.get('production_use', {}).get('narration_allowed')):
                        current = False
    return {'connected': True, 'current': current, 'input_sha256': binding['input_sha256'],
            'scene_map': refs, 'spine_ref': {'artifact_id': spine['artifact_id'], 'version': spine['version'],
                                          'artifact_type': 'NARRATIVE_SPINE', 'sha256': spine['sha256']},
            'reason': 'บทและข้อกำหนดภาพตรงกับข้อมูลผลิต' if current else 'บทหรือหลักฐานเปลี่ยน ต้องตรวจและเชื่อมใหม่'}


def _inspect(project, edit, loaded):
    report = _research_review(project)
    readiness = script_readiness(project, edit, report)
    issues = [row['scene_id']+': '+issue for row in readiness['scenes'] for issue in row['issues']]
    if not readiness['scenes']:
        issues.append('ยังไม่ได้เลือกฉาก')
    for key, label in (('central_question', 'คำถามหลักของเรื่อง'), ('narrative_arc', 'แนวทางการเล่าเรื่อง')):
        if not str(edit.get(key, '')).strip():
            issues.append('ยังไม่มี'+label)
    for scene in edit['scenes']:
        if not scene['included']:
            continue
        try:
            VisualRequirementsRuntime._validate_requirement({
                'beat_key': scene['id'], 'viewer_must_see': scene['visual'],
                'viewer_must_understand': scene['narration'], 'preferred_match': ['DIRECT', 'SUPPORTING'],
                'asset_needs': ['VIDEO'], 'priority': 'STANDARD'})
        except RuntimeError as exc:
            issues.append(scene['id']+': ระบุภาพที่ต้องการให้ชัดเจน ('+str(exc)+')')
        if scene.get('story_role', 'CONTEXT') not in ROLES:
            issues.append(scene['id']+': บทบาทฉากไม่รองรับ')
    engine = loaded.engine
    audit = engine.gates.evaluate_gate(engine.snapshot(), 'RESEARCH_AUDIT', engine.now()).result
    if audit not in ('PASS', 'WARN'):
        issues.append('รีเสิร์ชยังไม่ผ่านเกณฑ์ ต้องตรวจข้อกล่าวอ้างและประเด็นที่ค้างก่อน')
    if engine.project_state not in EARLY_STATES:
        issues.append('โปรเจกต์อยู่ขั้น '+engine.project_state+' ต้องใช้ขั้นตอนแก้ไขงานผลิตที่ล็อกแล้ว')
    if engine.project_state in {'ASSET_RECON', 'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY'}:
        from .media_bridge import owned_media_recon
        if not owned_media_recon(engine.snapshot()):
            issues.append('ขั้นสำรวจฟุตเทจนี้มีข้อมูลจากระบบอื่น ต้องย้ายข้อมูลอย่างชัดเจนก่อนแก้บท')
    foreign = [o for o in _active(engine.snapshot()).values()
               if o['object_type'] in ('ACT', 'SCENE', 'NARRATION_BEAT')
               and not o.get('extensions', {}).get('project_story')]
    if foreign:
        issues.append('มีข้อมูลเรื่องจากระบบอื่นอยู่แล้ว ต้องย้ายข้อมูลอย่างชัดเจนก่อนเชื่อมบท')
    return {'ready': not issues, 'issues': issues, 'edit_sha256': fingerprint(edit),
            'manifest_sha256': loaded.manifest_sha256, 'story_sha256': fingerprint(story_input(edit)),
            'production_state': engine.project_state, 'scene_count': len(readiness['scenes']),
            'research_audit_gate': audit,
            'binding': binding_status(project, engine.snapshot()), 'documentary_completed': False}


def inspect_story(project):
    # Initialize before taking the non-reentrant writer lock.
    EditSession(project).load()
    with project._lock():
        return _inspect(project, EditSession(project).load(), ProductionProject(project)._load())


def scene_search_intent(project, scene_id):
    """A connected project searches from exact canonical Beats and claim versions."""
    return scene_search_context(project, scene_id)[0]


def scene_search_context(project, scene_id):
    """Return the search intent and the production version it was prepared from."""
    from gmk_footage.query_planner import FootageQueryPlanner
    with project._lock():
        loaded = ProductionProject(project)._load()
        return _scene_search_context(project, scene_id, loaded, FootageQueryPlanner)


def _scene_search_context(project, scene_id, loaded, planner):
    state = loaded.engine.snapshot()
    binding = binding_status(project, state)
    if not binding['connected']:
        return None, loaded.manifest_sha256
    if not binding['current']:
        raise EditError('บทหรือหลักฐานเปลี่ยน ต้องตรวจและเชื่อมบทใหม่ก่อนค้นภาพอัตโนมัติ')
    intents = planner.from_state(state).beat_intents
    intent = next((row for row in intents if row.beat_key == scene_id), None)
    if intent is None:
        raise EditError('ฉากนี้ไม่ได้อยู่ในบทที่เชื่อมเข้าระบบผลิต')
    return intent, loaded.manifest_sha256


def _transition(engine, target):
    tx = engine.begin()
    tx.transition_project_state(target, actor_type='AI')
    tx.commit()


def connect_story(project, *, expected_edit_sha256, expected_manifest_sha256):
    """Explicit operator action; the tokens bind it to the previewed editor/research."""
    production = ProductionProject(project)
    EditSession(project).load()
    with project._lock():
        edit = EditSession(project).load()
        loaded = production._load()
        if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
            raise EditError('บทหรือหลักฐานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจความพร้อมใหม่')
        check = _inspect(project, edit, loaded)
        if not check['ready']:
            raise EditError('ยังเชื่อมบทไม่ได้: '+'; '.join(check['issues']))
        if check['binding']['current']:
            return {**check, 'idempotent_replay': True}
        engine = loaded.engine
        state = engine.snapshot()
        old_spine = _spine(state)
        if engine.project_state != 'RESEARCH_INTAKE':
            # Only this explicit operator action reopens these early editable stages.
            tx = engine.begin()
            from .coverage import retire_coverage
            retire_coverage(tx)
            tx.reenter_stage('RESEARCH_INTAKE', actor_type='HUMAN')
            tx.commit()
        _transition(engine, 'RESEARCH_AUDITED')
        active = _active(engine.snapshot())
        project_obj = next(o for o in active.values() if o['object_type'] == 'PROJECT')
        project_ref = {'id': project_obj['id'], 'version': project_obj['version']}
        content = story_input(edit)
        content_sha = fingerprint(content)
        batch = 'EDITOR_STORY_'+content_sha[:20].upper()
        old_map = old_spine['extensions']['project_story']['scene_map'] if old_spine else {}
        old_retired = old_spine['extensions']['project_story'].get('retired_scene_map', {}) if old_spine else {}
        retired = deepcopy(old_retired)
        old_act = old_spine['extensions']['project_story']['act_ref'] if old_spine else None
        tx = engine.begin()

        def put(kind, payload, prior=None):
            if prior is None:
                return tx.create_object(kind, {key: value for key, value in payload.items() if value is not None})
            # Archived excluded scenes keep their IDs when included again.
            obj = max((o for o in tx.staged.objects.values() if o['id'] == prior['id']), key=lambda o: o['version'])
            ref = tx.create_version(obj['id'], base_version=obj['version'], patch=payload)
            tx.promote_active_version(ref['id'], ref['version'])
            return ref

        act_ref = put('ACT', {'project_ref': project_ref, 'order': 1, 'title': edit['title'],
            'narrative': {'job': edit['narrative_arc'], 'audience_question': edit['central_question'],
                          'knowledge_before': edit['central_question'], 'knowledge_after': content['scenes'][-1]['narration']},
            'extensions': {'project_story': {'input_sha256': content_sha}}}, old_act)
        scene_map, scene_refs, beat_refs, claim_refs = {}, [], [], []
        for index, scene in enumerate(content['scenes'], 1):
            role, energy = ROLES[scene.get('story_role') or 'CONTEXT']
            prior = old_map.get(scene['id']) or retired.pop(scene['id'], {})
            common = {'input_sha256': content_sha, 'editor_scene_id': scene['id']}
            scene_ref = put('SCENE', {'act_ref': act_ref, 'order': index, 'title': scene['title'],
                'narrative': {'purpose': scene['title'] or scene['id'], 'viewer_question_entering': edit['central_question'],
                              'viewer_understanding_leaving': scene['narration']},
                'dynamics': {'role': role, 'energy': energy}, 'extensions': {'project_story': common}}, prior.get('scene_ref'))
            bindings = []
            for ref in scene['claim_refs']:
                claim = active.get(ref['id'])
                if claim is None or claim['version'] != ref['version']:
                    raise EditError('ข้อกล่าวอ้างไม่ใช่รุ่นที่ใช้งานอยู่: '+ref['id'])
                RoughNarrativeRuntime._validate_claim(claim)
                bindings.append({'claim_ref': ref, 'role': 'PRIMARY_FACT' if not bindings else 'SUPPORTING_FACT'})
                if ref not in claim_refs:
                    claim_refs.append(ref)
            beat_ref = put('NARRATION_BEAT', {'scene_ref': scene_ref, 'order': 1, 'beat_type': 'FACT',
                'idea': {'summary': scene['narration']}, 'viewer_takeaway': scene['narration'],
                'claim_bindings': bindings, 'workflow_state': 'RESEARCH_BOUND',
                'visual_requirement': None, 'narration': None,
                'extensions': {'project_story': common, 'rough_narrative': {'batch_id': batch, 'key': scene['id']}}},
                prior.get('beat_ref'))
            scene_refs.append(scene_ref); beat_refs.append(beat_ref)
            scene_map[scene['id']] = {'scene_ref': scene_ref, 'beat_ref': beat_ref}
        for key, refs in old_map.items():
            if key not in scene_map:
                tx.archive_object(refs['beat_ref']['id']); tx.archive_object(refs['scene_ref']['id'])
                retired[key] = refs
        binding = {'input_sha256': content_sha, 'act_ref': act_ref,
                   'scene_map': {**{key: None for key in old_map if key not in scene_map}, **scene_map},
                   'retired_scene_map': {**{key: None for key in old_retired if key not in retired}, **retired}}
        payload = {'project_ref': project_ref, 'core_question': edit['central_question'],
            'opening_promise': edit['narrative_arc'], 'major_turns': [s['title'] or s['id'] for s in content['scenes']],
            'extensions': {'project_story': binding, 'rough_narrative': {'batch_id': batch,
                'plan_sha256': content_sha, 'act_refs': [act_ref], 'scene_refs': scene_refs,
                'beat_refs': beat_refs, 'included_claim_refs': claim_refs, 'excluded_claim_ids': []}}}
        origins = [project_ref, *claim_refs]
        if old_spine:
            spine_ref = tx.create_artifact_version(old_spine['artifact_id'], base_version=old_spine['version'],
                                                   payload_patch=payload, origin_refs=origins)
        else:
            spine_ref = tx.create_artifact('NARRATIVE_SPINE', payload, origin_refs=origins)
        tx.commit()
        _transition(engine, 'ROUGH_NARRATIVE_READY')
        tx = engine.begin()
        for scene in content['scenes']:
            base = scene_map[scene['id']]['beat_ref']
            ref = tx.create_version(base['id'], base_version=base['version'], patch={
                'visual_requirement': {'viewer_must_see': scene['visual'], 'viewer_must_understand': scene['narration'],
                    'preferred_match': ['DIRECT', 'SUPPORTING'], 'asset_needs': ['VIDEO'], 'priority': 'STANDARD'},
                'workflow_state': 'VISUAL_REQUIREMENT_READY'})
            tx.promote_active_version(ref['id'], ref['version'])
            scene_map[scene['id']]['beat_ref'] = ref
        # The final spine pins the current Beat versions, so later readers see one graph.
        binding['scene_map'] = {**{key: None for key in old_map if key not in scene_map}, **scene_map}
        tx.create_artifact_version(spine_ref['artifact_id'], base_version=spine_ref['version'], payload_patch={
            'extensions': {'project_story': binding, 'rough_narrative': {'beat_refs': [r['beat_ref'] for r in scene_map.values()]}}},
            origin_refs=origins)
        tx.commit()
        _transition(engine, 'VISUAL_REQUIREMENTS_READY')
        # No live workspace writes occur until all graph/gate validation has succeeded.
        RuntimeStore(RUNTIME_ROOT, production.workspace).persist(engine)
        catalog = project.read(); catalog['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, catalog)
        return {'production_state': engine.project_state, 'binding': binding_status(project, engine.snapshot()),
                'idempotent_replay': False, 'documentary_completed': False}
