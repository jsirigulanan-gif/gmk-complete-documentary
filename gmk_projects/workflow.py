"""Readiness projection of the documentary lifecycle; never a second state engine."""
import json
import subprocess

from .edit import EditError, EditSession, asset_file, fingerprint, probe
from .media_review import shot_review_current, voice_review_current
from .production import ProductionProject
from .production_bridge import inspect_story
from .storage import StorageError


FILM_CHECKS = {
    'facts': 'ข้อเท็จจริงและการอ้างแหล่งข้อมูล',
    'visuals': 'ภาพตรงกับบทและระบุภาพประกอบชัดเจน',
    'pacing': 'ลำดับเรื่องและจังหวะการเล่า',
    'sync': 'ภาพตรงกับเสียงพากย์ตลอดเรื่อง',
    'pronunciation': 'คำอ่านและเสียงพากย์',
    'mix': 'ระดับเสียง ดนตรี และการฟังชัดเจน',
    'captions': 'คำบรรยายและข้อความบนภาพ',
    'credits': 'เครดิตและที่มาของภาพ/ดนตรี',
}


def workflow_status(project):
    """Inspect local bytes and reviews. No search, generation, upload or gate advance."""
    session = EditSession(project); edit = session.load()
    production = ProductionProject(project).status()
    if not production['connected']:
        return {'stages': [], 'next_action': 'CONNECT', 'next_label': 'เชื่อมโปรเจกต์รุ่นเดิม',
                'documentary_completed': False, 'issues': ['ยังไม่มีข้อมูลผลิตหลักของโปรเจกต์']}
    plan = session.preflight(edit)
    story = inspect_story(project)
    scenes = [s for s in edit['scenes'] if s['included']]
    stages = []
    def stage(key, label, ready, action, detail):
        stages.append({'key': key, 'label': label, 'ready': bool(ready), 'action': action, 'detail': detail})
    brief = edit.get('brief') or {}
    brief_ready = all(brief.get(k) for k in ('topic', 'audience', 'central_question', 'target_seconds'))
    stage('BRIEF', 'หัวเรื่องและโจทย์', brief_ready, 'BRIEF', 'ระบุผู้ชม คำถามหลัก ขอบเขต และความยาวเป้าหมาย')
    has_research = production['research_pack_count'] > 0
    stage('RESEARCH', 'รีเสิร์ช', has_research, 'IMPORT_RESEARCH', 'นำเข้าเอกสาร Gemini/Drive หรือไฟล์รีเสิร์ช')
    evidence = production['claim_count'] > 0 and story['research_audit_gate'] in {'PASS', 'WARN'}
    stage('EVIDENCE', 'หลักฐานและข้อกล่าวอ้าง', evidence, 'RESEARCH',
          f'ข้อความรอตรวจ {production["unreviewed_claim_count"]} / ทั้งหมด {production["claim_count"]} รายการ')
    narrative = bool(scenes) and bool(edit.get('central_question')) and bool(edit.get('narrative_arc')) and all(s['narration'].strip() for s in scenes)
    stage('NARRATIVE', 'โครงเรื่อง', narrative, 'STORY', 'ต้องมีคำถามหลัก แนวทางเล่าเรื่อง และบทฉากที่เลือก')
    stage('SCRIPT', 'บทพากย์', plan['script_review']['ready'] and narrative, 'SCRIPT', 'เทียบถ้อยคำของทุกฉากกับหลักฐานรุ่นปัจจุบัน')
    bound = story['binding']['current']
    stage('BEATS', 'ฉากและจังหวะการเล่า', bound, 'PRODUCTION', story['binding']['reason'])
    stage('VISUAL', 'ข้อกำหนดภาพ', bound, 'PRODUCTION', 'เชื่อมบทที่ตรวจแล้วเข้าฉากและข้อกำหนดภาพ')
    has_search = any((project.root/'footage_research').glob('*.json')) or (bool(scenes) and all(s['shots'] for s in scenes))
    stage('FOOTAGE_RESEARCH', 'ค้นฟุตเทจ', has_search, 'FOOTAGE', 'ค้นจากภาพที่ต้องการ หรือเลือกฟุตเทจของคุณ')
    all_shots = bool(scenes) and all(s['shots'] for s in scenes)
    reviews = all_shots and all(shot_review_current(s, cut) for s in scenes for cut in s['shots'])
    stage('SELECTION', 'ตรวจและเลือกภาพ', reviews, 'SHOT_REVIEW', 'เปิดดูแต่ละช่วงภาพ แล้วบันทึกสิ่งที่เห็นและเหตุผลที่ตรงบท')
    media_issues, missing_footage = [], set()
    for s in scenes:
        for cut in s['shots']:
            try:
                info = probe(asset_file(project, cut, 'footage'))
                if not any(x['codec_type'] == 'video' for x in info['streams']) or not 0 <= cut['in_seconds'] < cut['out_seconds'] <= info['duration_seconds']+.05:
                    raise EditError('ช่วงภาพไม่ตรงไฟล์จริง')
            except (ValueError, OSError, StorageError, subprocess.SubprocessError) as exc:
                media_issues.append(s['id']+': '+str(exc))
                missing_footage.add(s['id'])
    next(row for row in stages if row['key'] == 'SELECTION')['ready'] = reviews and not media_issues
    media_binding = production['media_binding']
    acquisition_action = 'PRODUCTION_MEDIA' if all_shots and not media_issues else 'FOOTAGE'
    stage('ACQUISITION', 'ไฟล์ฟุตเทจและข้อมูลผลิต', all_shots and not media_issues and media_binding['current'], acquisition_action,
          '; '.join(media_issues) or media_binding['reason'])
    stage('SCENE_PLAN', 'ลำดับฉาก', narrative, 'SCRIPT', 'เรียงฉากและกำหนดการพาคนดูจากคำถามไปสู่คำตอบ')
    coverage = production['coverage_binding']
    stage('SHOT_PLAN', 'ช็อตและความครอบคลุมภาพ', reviews and not media_issues and coverage['ready'], 'COVERAGE', coverage['reason'])
    stage('TIMELINE', 'ไทม์ไลน์', plan['ready_to_render'], 'TIMELINE',
          '; '.join(x['detail'] for x in plan['issues']) or f'ความยาวจริง {plan["duration_seconds"]:.2f} วินาที')
    voices = bool(scenes) and all(s.get('voice') and s['voice'].get('text_sha256') == fingerprint(s['narration']) for s in scenes)
    voice_issues, missing_voice = [], set()
    if voices:
        for scene in scenes:
            try:
                info = probe(asset_file(project, scene['voice'], 'voice'))
                if not any(x['codec_type'] == 'audio' for x in info['streams']):
                    raise EditError('ไฟล์ไม่มีเสียง')
            except (ValueError, OSError, StorageError, subprocess.SubprocessError) as exc:
                voice_issues.append(scene['id']+': '+str(exc))
                missing_voice.add(scene['id'])
        voices = not voice_issues
    stage('VOICE', 'เสียงพากย์', voices and all(voice_review_current(s) for s in scenes), 'VOICE',
          '; '.join(voice_issues) or 'สร้างหรือนำเข้าเสียงตรงบท แล้วฟังตรวจคำอ่านและยืนยันแต่ละฉาก')
    music_ready = bool(edit.get('music_omitted')) and not edit.get('music')
    if edit.get('music'):
        try:
            info = probe(asset_file(project, edit['music'], 'music'))
            music_ready = any(x['codec_type'] == 'audio' for x in info['streams'])
        except (ValueError, OSError, StorageError, subprocess.SubprocessError):
            music_ready = False
    stage('DESIGN', 'ดนตรีและกราฟิก', music_ready, 'DESIGN',
          'เลือกดนตรี ระดับเสียง และชื่อฉาก หรือระบุว่าตั้งใจไม่ใช้ดนตรี')
    render_ready, render_issue = False, 'ยังไม่มีวิดีโอจากบทและไทม์ไลน์รุ่นปัจจุบัน'
    try:
        render = json.loads((project.root/'last_render.json').read_text())
        if (render['edit_sha256'] == fingerprint(edit)
                and render['research_manifest_sha256'] == production['manifest_sha256']
                and render['technical_qa']['passed'] is True):
            asset_file(project, render['registered']['preview.mp4'], 'exports')
            render_ready, render_issue = True, 'วิดีโอตรงกับบทและไทม์ไลน์ปัจจุบัน'
    except (ValueError, OSError, StorageError, KeyError):
        pass
    stage('RENDER', 'เรนเดอร์วิดีโอ', render_ready, 'RENDER', render_issue)
    qa_ready, qa_issue = False, 'ดูและฟังทั้งเรื่อง แล้วบันทึกผลตรวจครบทุกด้าน'
    if render_ready:
        from .delivery import current_reviewed_render
        try:
            _, decision, _, _ = current_reviewed_render(project)
            qa_ready = all((decision.get('full_film_checklist') or {}).get(key) is True for key in FILM_CHECKS)
        except (ValueError, OSError, StorageError) as exc:
            qa_issue = str(exc)
    stage('FILM_QA', 'ตรวจสารคดีทั้งเรื่อง', qa_ready, 'FILM_QA', qa_issue)
    package_ready, package_issue = False, 'สร้างชุด MP4 บท คำบรรยาย เครดิต และผลตรวจ'
    if qa_ready:
        from .delivery import verify_delivery
        try:
            verify_delivery(project); package_ready = True
        except (ValueError, OSError, StorageError) as exc:
            package_issue = str(exc)
    stage('DELIVERY', 'ชุดส่งออก', package_ready, 'EXPORT', package_issue)
    stage('EXPORT', 'ส่งและตรวจไฟล์บน Drive', package_ready and project.read()['storage_status'] == 'VERIFIED', 'DRIVE',
          'ส่งชุดไฟล์และต้นฉบับที่เก็บไว้ แล้วตรวจสำเนาบน Drive')
    stage('COMPLETED', 'สารคดีเสร็จสมบูรณ์', production['documentary_completed'], 'FINAL_RELEASE',
          'รอเชื่อมหลักฐานการส่งมอบเข้าขั้นอนุมัติสุดท้ายของข้อมูลผลิตหลัก')
    # Narration timing feeds the timeline: get voice before trying to fill shots.
    pending = next((s for s in stages if not s['ready']), None)
    if pending and pending['action'] == 'SHOT_REVIEW' and media_issues:
        pending = next(s for s in stages if s['key'] == 'ACQUISITION')
    if pending and pending['action'] in {'FOOTAGE', 'SHOT_REVIEW', 'PRODUCTION_MEDIA', 'TIMELINE', 'COVERAGE'} and not voices:
        pending = next(s for s in stages if s['key'] == 'VOICE')
    if pending and pending['action'] == 'COVERAGE' and not next(s for s in stages if s['key'] == 'VOICE')['ready']:
        pending = next(s for s in stages if s['key'] == 'VOICE')
    target = None
    if pending:
        if pending['action'] == 'VOICE':
            target = next((s['id'] for s in scenes if s['id'] in missing_voice or not s.get('voice')
                           or s['voice'].get('text_sha256') != fingerprint(s['narration'])), None)
            target = target or next((s['id'] for s in scenes if not voice_review_current(s)), None)
        elif pending['action'] == 'FOOTAGE':
            target = next((s['id'] for s in scenes if s['id'] in missing_footage or not s['shots']), None)
        elif pending['action'] == 'SHOT_REVIEW':
            target = next((s['id'] for s in scenes if any(not shot_review_current(s, c) for c in s['shots'])), None)
    if fingerprint(session.load()) != fingerprint(edit) or ProductionProject(project)._load().manifest_sha256 != production['manifest_sha256']:
        raise EditError('โปรเจกต์เปลี่ยนระหว่างตรวจ กรุณาตรวจความพร้อมใหม่')
    return {'stages': stages, 'next_action': pending['action'] if pending else None,
            'next_scene_id': target,
            'next_label': pending['label'] if pending else 'สารคดีเสร็จสมบูรณ์',
            'edit_sha256': fingerprint(edit), 'production_state': production['production_state'],
            'documentary_completed': production['documentary_completed'], 'timeline': plan,
            'media_binding': media_binding,
            'coverage_binding': coverage,
            'issues': media_issues}
