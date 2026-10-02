"""Register reviewed draft footage as exact canonical Assets and Segments.

This records an existing local acquisition; it does not invent a download,
search-completion certificate, rights clearance, or coverage/film approval.
"""
from copy import deepcopy
import json
import subprocess

from gmk_runtime.persistence import RuntimeStore

from .edit import EditError, EditSession, asset_file, fingerprint, probe
from .media_review import shot_input, shot_review_current
from .production import ProductionProject, RUNTIME_ROOT
from .production_bridge import _active, binding_status, story_input
from .storage import StorageError, atomic_json


MEDIA_EDITABLE_STATES = {'VISUAL_REQUIREMENTS_READY', 'ASSET_RECON', 'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY', 'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED'}
OWNED_MEDIA_STATES = MEDIA_EDITABLE_STATES - {'VISUAL_REQUIREMENTS_READY'}
MEDIA_READABLE_STATES = MEDIA_EDITABLE_STATES | {'DESIGN_DNA_APPROVED', 'SCENE_PLAN_READY', 'SHOT_PLAN_READY'}


def owned_media_recon(state):
    if state.project_state in {'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED'}:
        from .final_production import owns_final
        if not owns_final(state): return False
    return (state.project_state in OWNED_MEDIA_STATES and bool(_pools(state))
            and all(o.get('extensions', {}).get('project_media')
                    for o in _active(state).values()
                    if o['object_type'] in {'ASSET', 'SEGMENT', 'SEARCH', 'SEARCH_RESULT'}))


def media_input(edit):
    return {'story': fingerprint(story_input(edit)), 'scenes': [
        {'id': s['id'], 'shots': [{'input': shot_input(s, c), 'review': c.get('visual_review')}
                                for c in s['shots']]}
        for s in edit['scenes'] if s['included']]}


def _pools(state):
    result = {}
    for a in state.artifacts.values():
        ext = a.get('extensions', {}).get('project_media') or {}
        if a.get('artifact_type') != 'PROVENANCE_MANIFEST' or not ext.get('scene_id'):
            continue
        previous = result.get(ext['scene_id'])
        if previous and previous['artifact_id'] != a['artifact_id']:
            raise EditError('พบคลังภาพของฉากซ้ำ ต้องตรวจข้อมูลก่อนเชื่อมภาพ')
        if previous is None or a['version'] > previous['version']:
            result[ext['scene_id']] = a
    return result


def media_binding_status(project, state, *, edit=None, verify_files=True):
    pools = _pools(state)
    if edit is None:
        try: edit = json.loads((project.root/'edit.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {'connected': bool(pools), 'current': False, 'asset_count': 0, 'segment_count': 0,
                    'coverage_approved': False, 'rights_cleared': False, 'reason': 'ยังไม่มีร่างตัดต่อให้เชื่อมภาพ'}
    selected = [s for s in edit['scenes'] if s['included']]
    signature = fingerprint(media_input(edit))
    live = _active(state)
    current = bool(pools) and state.project_state in MEDIA_READABLE_STATES and binding_status(project, state)['current']
    rows = []
    for scene in selected:
        pool = pools.get(scene['id'])
        ext = pool.get('extensions', {}).get('project_media', {}) if pool else {}
        if ext.get('retired') or ext.get('input_sha256') != signature:
            current = False
        for row in ext.get('rows', []):
            rows.append(row)
            for key in ('asset_ref', 'segment_ref', 'result_ref', 'search_ref', 'beat_ref'):
                ref = row[key]; obj = live.get(ref['id'])
                if (not obj or obj['version'] != ref['version'] or obj.get('stale', {}).get('is_stale')
                        or obj.get('status') in {'STALE', 'ARCHIVED', 'BLOCKED', 'REJECTED'}):
                    current = False
            if verify_files:
                try: asset_file(project, row['file'], 'footage')
                except (OSError, StorageError): current = False
    if any(not p.get('extensions', {}).get('project_media', {}).get('retired')
           for key, p in pools.items() if key not in {s['id'] for s in selected}):
        current = False
    return {'connected': bool(pools), 'current': current, 'input_sha256': signature,
            'asset_count': len(rows), 'segment_count': len(rows),
            'coverage_approved': False, 'rights_cleared': False,
            'reason': 'รายการภาพและช่วงตัดตรงกับข้อมูลผลิต' if current else 'ยังไม่ได้เชื่อมภาพ หรือภาพ บท และผลตรวจเปลี่ยนรุ่น'}


def _inspect(project, edit, loaded):
    state = loaded.engine.snapshot(); story = binding_status(project, state)
    issues, clips, missing = [], [], []
    if not story['current']: issues.append('ตรวจและเชื่อมบทเข้าระบบผลิตก่อนเชื่อมภาพ')
    if loaded.engine.project_state not in MEDIA_EDITABLE_STATES:
        issues.append('เชื่อมภาพได้ในขั้นร่างภาพก่อนล็อกการผลิตเท่านั้น')
    if loaded.engine.project_state in {'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED'} and not owned_media_recon(state):
        issues.append('งานบทหรือเสียงขั้นผลิตมาจากระบบอื่น ต้องย้ายข้อมูลก่อนแก้ภาพ')
    foreign = [o for o in _active(state).values() if o['object_type'] in {'ASSET', 'SEGMENT', 'SEARCH', 'SEARCH_RESULT'}
               and not o.get('extensions', {}).get('project_media')]
    if foreign: issues.append('มีรายการภาพจากระบบอื่น ต้องย้ายข้อมูลอย่างชัดเจนก่อนเชื่อมภาพ')
    for scene in edit['scenes']:
        if not scene['included']: continue
        if not scene['shots']: missing.append(scene['id'])
        seen = set()
        for cut in scene['shots']:
            label = scene['id']+' / '+cut['id']
            if cut['id'] in seen:
                issues.append(label+': รหัสช็อตซ้ำในฉากเดียวกัน')
            seen.add(cut['id'])
            if not shot_review_current(scene, cut): issues.append(label+': ยังไม่มีผลตรวจภาพที่ตรงกับบทและช่วงตัดปัจจุบัน')
            try:
                info = probe(asset_file(project, cut, 'footage'))
                video = next((v for v in info['streams'] if v['codec_type'] == 'video'), None)
                if not video or not 0 <= cut['in_seconds'] < cut['out_seconds'] <= info['duration_seconds']+.05:
                    raise EditError('ช่วงภาพไม่ตรงกับวิดีโอจริง')
                catalog = next(a for a in project.read()['assets'] if a['path'] == cut['path'])
                url = cut.get('source_url') or ''
                if url and url not in catalog['source_urls']:
                    raise EditError('ที่มาของช็อตไม่ตรงกับไฟล์ที่ลงทะเบียน')
                clips.append({'scene_id': scene['id'], 'shot_id': cut['id'],
                              'file': {'path': cut['path'], 'sha256': cut['sha256']},
                              'technical': {'duration_seconds': info['duration_seconds'], 'width': video['width'],
                                            'height': video['height'], 'codec': video.get('codec_name', ''),
                                            'file_size_bytes': catalog['size'],
                                            'audio_present': any(s['codec_type'] == 'audio' for s in info['streams'])}})
            except (OSError, ValueError, KeyError, StorageError, subprocess.SubprocessError) as exc:
                issues.append(label+': '+str(exc))
    if not clips and not _pools(state): issues.append('ยังไม่มีฟุตเทจที่เลือกในฉาก')
    return {'ready': not issues, 'issues': issues, 'clips': clips, 'missing_scene_ids': missing,
            'edit_sha256': fingerprint(edit), 'manifest_sha256': loaded.manifest_sha256,
            'production_state': loaded.engine.project_state, 'binding': media_binding_status(project, state, edit=edit),
            'documentary_completed': False}


def inspect_media(project):
    EditSession(project).load()
    with project._lock():
        return _inspect(project, EditSession(project).load(), ProductionProject(project)._load())


def connect_media(project, *, expected_edit_sha256, expected_manifest_sha256):
    production = ProductionProject(project); EditSession(project).load()
    with project._lock():
        edit = EditSession(project).load(); loaded = production._load()
        if fingerprint(edit) != expected_edit_sha256 or loaded.manifest_sha256 != expected_manifest_sha256:
            raise EditError('ภาพ บท หรือหลักฐานเปลี่ยนหลังเปิดตรวจ กรุณาตรวจใหม่')
        check = _inspect(project, edit, loaded)
        if not check['ready']: raise EditError('ยังเชื่อมภาพไม่ได้: '+'; '.join(check['issues']))
        if check['binding']['current']: return {**check, 'idempotent_replay': True}
        engine = loaded.engine; state = engine.snapshot(); pools = _pools(state)
        story = binding_status(project, state); signature = fingerprint(media_input(edit))
        live = _active(state)
        sources = {o['extensions']['project_media']['source_key']: o for o in live.values()
                   if o['object_type'] == 'SOURCE' and o.get('extensions', {}).get('project_media', {}).get('source_key')}
        # Historical receipts retain identities when a removed cut is restored.
        old_rows = {}
        for receipt in sorted(state.artifacts.values(), key=lambda a: a['version']):
            ext = receipt.get('extensions', {}).get('project_media', {})
            if receipt.get('artifact_type') == 'PROVENANCE_MANIFEST' and ext.get('scene_id'):
                for row in ext.get('rows', []):
                    old_rows[(ext['scene_id'], row['shot_id'])] = row
        tx = engine.begin()
        from .coverage import retire_coverage
        retire_coverage(tx)
        if engine.project_state in {'ASSET_CATALOG_READY', 'VISUAL_COVERAGE_READY', 'SCRIPT_READY', 'TTS_READY', 'VOICE_LOCKED'}:
            tx.reenter_stage('ASSET_RECON', actor_type='HUMAN')
        if engine.project_state == 'VISUAL_REQUIREMENTS_READY':
            tx.transition_project_state('ASSET_RECON', actor_type='SYSTEM')

        def put(kind, payload, prior=None):
            if not prior: return tx.create_object(kind, payload)
            before = max((o for o in tx.staged.objects.values() if o['id'] == prior['id']), key=lambda o: o['version'])
            if before.get('status') not in {'ARCHIVED', 'STALE', 'BLOCKED', 'REJECTED'} and not before.get('stale', {}).get('is_stale') and all(before.get(k) == v for k, v in payload.items()):
                return {'id': before['id'], 'version': before['version']}
            ref = tx.create_version(before['id'], base_version=before['version'], patch=payload)
            tx.promote_active_version(ref['id'], ref['version'])
            return ref

        selected_ids, retained = set(), set()
        for scene in edit['scenes']:
            if not scene['included']: continue
            selected_ids.add(scene['id']); beat = story['scene_map'][scene['id']]['beat_ref']
            scene_ref = story['scene_map'][scene['id']]['scene_ref']
            old_pool = pools.get(scene['id']); old = old_pool['extensions']['project_media'] if old_pool else {}
            ext = {'project_media': {'scene_id': scene['id']}}
            search = put('SEARCH', {'target_beat_ref': beat, 'priority': 'STANDARD', 'search_round': 1,
                'search_pass': 'LONG_FORM_FOOTAGE', 'query_family': 'VISUAL_DESCRIPTION', 'query': scene['visual'],
                'language': 'und', 'provider': {'type': 'GMK_REVIEWED_PROJECT_LIBRARY'},
                'trigger': {'type': 'HUMAN_REQUEST'}, 'workflow_state': 'COMPLETED', 'extensions': ext}, old.get('search_ref'))
            rows = []
            for cut in scene['shots']:
                retained.add((scene['id'], cut['id'])); previous = old_rows.get((scene['id'], cut['id']), {})
                clip = next(c for c in check['clips'] if c['scene_id'] == scene['id'] and c['shot_id'] == cut['id'])
                review = cut['visual_review']; url = cut.get('source_url') or ''
                key = fingerprint({'file': clip['file'], 'source_url': url})
                source = sources.get(key)
                if source is None:
                    ref = tx.create_object('SOURCE', {'source_type': 'VIDEO', 'title': 'Registered footage '+cut['sha256'][:12],
                        'authority_class': 'UNKNOWN', 'independence': {'group_id': 'SRCGRP_UNCONFIRMED_FOOTAGE', 'relationship': 'UNKNOWN'},
                        'language': 'und', 'availability': {'state': 'ARCHIVED'}, 'accessed_at': engine.now(),
                        **({'url': url} if url else {}), 'extensions': {'project_media': {'source_key': key, 'file': clip['file']}}})
                    source = tx.staged.objects[(ref['id'], ref['version'])]; sources[key] = source
                source_ref = {'id': source['id'], 'version': source['version']}
                selector = {'type': 'VIDEO_TIME_RANGE', 'start_seconds': cut['in_seconds'], 'end_seconds': cut['out_seconds']}
                match = review['match_type'] if review['match_type'] != 'CONTEXT' else 'MISMATCH'
                mapped = {'project_media': {'scene_id': scene['id'], 'shot_id': cut['id'], 'file': clip['file'],
                                           'input_sha256': fingerprint(shot_input(scene, cut)), 'editor_match_type': review['match_type']}}
                result = put('SEARCH_RESULT', {'search_ref': search, 'discovery_method': 'HUMAN_INJECTION',
                    'discovery_locator': {'type': 'WEB_URI', 'value': url} if url else {'type': 'LOGICAL_URI', 'value': f'gmk://project/{project.read()["project_id"]}/{cut["path"]}'},
                    'title': scene['title']+' / '+cut['id'], 'source_family': 'REUPLOAD', 'source_ref': source_ref,
                    'candidate_state': 'INSPECTED', 'inspection': {'visible_content': review['visible_content'],
                        'exact_moment_found': True, 'candidate_locator': selector, 'match_type': match,
                        'match_reason': review['match_reason'], 'viewer_takeaway_supported': match != 'MISMATCH'},
                    'extensions': mapped}, previous.get('result_ref'))
                asset = put('ASSET', {'origin_search_result_ref': result, 'source_ref': source_ref, 'media_type': 'VIDEO',
                    'asset_class': 'CONTEXTUAL_B_ROLL' if match == 'MISMATCH' else 'DIRECT_FOOTAGE' if match == 'DIRECT' else 'ILLUSTRATIVE',
                    'workflow_state': 'CATALOGED', 'original_file': {'uri': f'gmk://project/{project.read()["project_id"]}/{cut["path"]}',
                        'checksum': cut['sha256'], 'immutable': True}, 'technical': clip['technical'],
                    'rights': {'status': 'UNKNOWN', 'basis': 'Registration of acquired bytes is not rights clearance.'},
                    'extensions': mapped}, previous.get('asset_ref'))
                segment = put('SEGMENT', {'asset_ref': asset, 'selector': selector, 'source_locator': selector,
                    'visual_content': review['visible_content'], 'match_type': match, 'match_reason': review['match_reason'],
                    'production_state': 'UNVERIFIED' if match == 'MISMATCH' else 'VERIFIED', 'extensions': mapped}, previous.get('segment_ref'))
                rows.append({'shot_id': cut['id'], 'search_ref': search, 'result_ref': result, 'asset_ref': asset,
                             'segment_ref': segment, 'beat_ref': beat, 'file': clip['file']})
            payload = {'entries': deepcopy(rows),
                'disclosures': ['Recorded local copies and explicit visual reviews; source independence, rights clearance, search completion and canonical coverage remain unapproved.'],
                'extensions': {'project_media': {
                    'scene_id': scene['id'], 'input_sha256': signature, 'search_ref': search, 'rows': rows,
                    'retired': False, 'coverage_status': 'PENDING_CANONICAL_COVERAGE_ASSESSMENT'}}}
            origins = [scene_ref, beat, search, *[r[k] for r in rows for k in ('asset_ref', 'segment_ref')]]
            if old_pool:
                tx.create_artifact_version(old_pool['artifact_id'], base_version=old_pool['version'], payload_patch=payload, origin_refs=origins)
            else: tx.create_artifact('PROVENANCE_MANIFEST', payload, origin_refs=origins)
        for cut_id, row in old_rows.items():
            if cut_id not in retained:
                for key in ('asset_ref', 'segment_ref', 'result_ref'):
                    obj = live.get(row[key]['id'])
                    if obj and obj.get('status') != 'ARCHIVED': tx.archive_object(obj['id'])
        for scene_id, pool in pools.items():
            if scene_id not in selected_ids and not pool['extensions']['project_media'].get('retired'):
                tx.create_artifact_version(pool['artifact_id'], base_version=pool['version'], payload_patch={
                    'extensions': {'project_media': {'retired': True}}})
                search = live.get(pool['extensions']['project_media']['search_ref']['id'])
                if search and search.get('status') != 'ARCHIVED': tx.archive_object(search['id'])
        tx.commit()
        # Recheck registered bytes before publishing the staged graph.
        for clip in check['clips']: asset_file(project, clip['file'], 'footage')
        RuntimeStore(RUNTIME_ROOT, production.workspace).persist(engine)
        final = production._load()
        data = project.read(); data['storage_status'] = 'PENDING_UPLOAD'; atomic_json(project.manifest, data)
        return {**check, 'production_state': engine.project_state, 'manifest_sha256': final.manifest_sha256,
                'binding': media_binding_status(project, engine.snapshot(), edit=edit), 'idempotent_replay': False}
