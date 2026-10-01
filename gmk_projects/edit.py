"""Editable draft assembly. Production gates remain owned by ProductionProject."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
from uuid import uuid4

from .storage import Project, StorageError, atomic_json, digest, relative_path


class EditError(StorageError):
    pass


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def probe(path: Path) -> dict:
    import os
    result = subprocess.run([os.environ.get('GMK_FFPROBE', 'ffprobe'), '-v', 'error',
                             '-show_format', '-show_streams', '-of', 'json', str(path)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise EditError('อ่านไฟล์สื่อไม่ได้: ' + path.name)
    data = json.loads(result.stdout)
    duration = float(data.get('format', {}).get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise EditError('ไฟล์สื่อต้องมีความยาวมากกว่าศูนย์')
    return {**data, 'duration_seconds': duration}


def asset_file(project: Project, reference: dict, role: str | None = None) -> Path:
    path = reference.get('path', '')
    asset = next((a for a in project.read()['assets'] if a['path'] == path), None)
    if asset is None or (role and asset['role'] != role) or asset['sha256'] != reference.get('sha256'):
        raise EditError('ไฟล์ไม่ได้อยู่ในคลังโปรเจกต์หรือรุ่นไฟล์ไม่ตรงกัน')
    local = project.root / relative_path(path)
    if local.is_symlink() or not local.resolve().is_relative_to(project.root) or not local.is_file():
        raise EditError('ไฟล์สื่อหายหรืออยู่นอกโปรเจกต์')
    if digest(local)['sha256'] != asset['sha256']:
        raise EditError('ไฟล์สื่อถูกแก้หลังลงทะเบียน กรุณานำเข้าเป็นรุ่นใหม่')
    return local


def media_ref(asset):
    return {'path': asset['path'], 'sha256': asset['sha256']}


class EditSession:
    def __init__(self, project: Project):
        self.project = project
        self.path = project.root/'edit.json'

    def load(self) -> dict:
        if not self.path.exists():
            return self.initialize()
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('project_id') != self.project.read()['project_id']:
            raise EditError('ไฟล์ตัดต่อเป็นของโปรเจกต์อื่น')
        return data

    def initialize(self) -> dict:
        with self.project._lock():
            if self.path.exists():
                return self.load()
            script_path = self.project.root/'script.json'
            script = json.loads(script_path.read_text(encoding='utf-8')) if script_path.exists() else {}
            scenes = [{'id': s['id'], 'title': s.get('heading', s['id']),
                       'narration': s.get('narration_th', ''), 'visual': s.get('cues', {}).get('visual', ''),
                       'audio_direction': s.get('cues', {}).get('audio', ''),
                       'included': True, 'shots': [], 'voice': None, 'hold_last_frame': False,
                       'show_title': False} for s in script.get('scenes', [])]
            if not scenes:
                scenes = [self.new_scene()]
            data = {'version': 1, 'revision': 1, 'project_id': self.project.read()['project_id'],
                    'source_script_sha256': digest(script_path)['sha256'] if script_path.exists() else None,
                    'title': self.project.read()['title'], 'scenes': scenes, 'music': None,
                    'music_gain': 0.12, 'width': 1280, 'height': 720, 'fps': 30}
            atomic_json(self.path, data)
            catalog = self.project.read()
            catalog['storage_status'] = 'PENDING_UPLOAD'
            atomic_json(self.project.manifest, catalog)
            return data

    @staticmethod
    def new_scene():
        return {'id': 'SCENE-'+uuid4().hex[:12], 'title': 'ฉากใหม่', 'narration': '', 'visual': '',
                'audio_direction': '', 'included': True, 'shots': [], 'voice': None,
                'hold_last_frame': False, 'show_title': False}

    def save(self, data: dict, *, expected_revision: int, expected_production_manifest_sha256: str | None = None) -> dict:
        data = deepcopy(data)
        ids = [s['id'] for s in data['scenes']]
        if not ids or len(set(ids)) != len(ids):
            raise EditError('ต้องมีฉากอย่างน้อยหนึ่งฉากและรหัสฉากห้ามซ้ำ')
        if not 0 <= float(data.get('music_gain', .12)) <= 1:
            raise EditError('ระดับดนตรีต้องอยู่ระหว่าง 0 ถึง 1')
        if (data.get('width'), data.get('height')) not in ((640, 360), (1280, 720), (1920, 1080)) or data.get('fps') not in (24, 25, 30):
            raise EditError('ขนาดภาพหรือเฟรมเรตไม่รองรับ')
        with self.project._lock():
            current = self.load()
            if expected_production_manifest_sha256 is not None:
                from .production import ProductionProject
                if ProductionProject(self.project)._load().manifest_sha256 != expected_production_manifest_sha256:
                    raise EditError('หลักฐานหรือข้อมูลผลิตเปลี่ยนระหว่างเตรียมภาพ กรุณาตรวจแล้วลองใหม่ ไฟล์ที่ดาวน์โหลดยังอยู่ในคลัง')
            if current['revision'] != expected_revision or data.get('project_id') != current['project_id']:
                raise EditError('มีการแก้โปรเจกต์จากหน้าต่างอื่น กรุณาโหลดใหม่ก่อนบันทึก')
            old = {s['id']: s for s in current['scenes']}
            for scene in data['scenes']:
                if scene['id'] in old and scene['narration'] != old[scene['id']]['narration']:
                    scene['voice'] = None  # Every changed narration needs a matching voice revision.
                    scene.pop('claim_review', None)
                voice = scene.get('voice')
                if voice and voice.get('text_sha256') != fingerprint(scene['narration']):
                    raise EditError('เสียงพากย์ไม่ตรงกับข้อความฉากนี้')
            data['revision'] = current['revision']
            if data == current:
                return current
            data['revision'] = current['revision'] + 1
            atomic_json(self.path, data)
            catalog = self.project.read()
            catalog['storage_status'] = 'PENDING_UPLOAD'
            atomic_json(self.project.manifest, catalog)
        return data

    def attach_voice(self, scene_id: str, path: Path, *, expected_revision: int) -> dict:
        data = self.load()
        if data['revision'] != expected_revision:
            raise EditError('โปรเจกต์ถูกแก้ระหว่างเลือกไฟล์เสียง กรุณาโหลดใหม่')
        scene = next(s for s in data['scenes'] if s['id'] == scene_id)
        info = probe(path)
        if not any(s['codec_type'] == 'audio' for s in info['streams']):
            raise EditError('ไฟล์นี้ไม่มีเสียง')
        asset = self.project.add_file(path, 'voice', scenes=[scene_id])
        scene['voice'] = {**media_ref(asset), 'duration_seconds': info['duration_seconds'],
                          'text_sha256': fingerprint(scene['narration']), 'provider': 'IMPORTED_AUDIO',
                          'listening_review': 'PENDING'}
        return self.save(data, expected_revision=expected_revision)

    def synthesize(self, provider, *, scene_ids: list[str] | None = None) -> dict:
        """Only an explicit UI/CLI action sends text to a selected provider."""
        data = self.load()
        selected = set(scene_ids) if scene_ids is not None else {s['id'] for s in data['scenes'] if s['included']}
        if not selected.issubset({s['id'] for s in data['scenes']}):
            raise EditError('ไม่พบฉากที่เลือก')
        from .voice import audio_duration
        generated = self.project.root/'generated_voice'
        generated.mkdir(exist_ok=True)
        for scene_id in [s['id'] for s in data['scenes'] if s['id'] in selected]:
            data = self.load()
            scene = next(s for s in data['scenes'] if s['id'] == scene_id)
            text = scene['narration'].strip()
            if not text:
                raise EditError('ฉากไม่มีบทพากย์: '+scene_id)
            key = fingerprint({'provider': provider.name, 'voice': provider.voice, 'rate': provider.rate, 'text': text})
            audio, cache = generated/(key+'.mp3'), generated/(key+'.json')
            valid = False
            if audio.is_file() and cache.is_file():
                try:
                    valid = digest(audio)['sha256'] == json.loads(cache.read_text()).get('sha256')
                except (ValueError, AttributeError):
                    pass
            if not valid:
                atomic_json(cache, provider.synthesize(text, audio))
            asset = self.project.add_file(audio, 'voice', scenes=[scene_id])
            scene['voice'] = {**media_ref(asset), 'text_sha256': fingerprint(scene['narration']),
                              'duration_seconds': audio_duration(audio), 'provider': provider.name,
                              'listening_review': 'PENDING'}
            subtitle = audio.with_suffix('.srt')
            if subtitle.is_file():
                scene['voice']['subtitles'] = media_ref(self.project.add_file(subtitle, 'voice', scenes=[scene_id]))
            data = self.save(data, expected_revision=data['revision'])
        return data

    def import_existing_voice(self) -> dict:
        data = self.load()
        script_path = self.project.root/'script.json'
        if not (self.project.root/'voice_timeline.json').is_file():
            raise EditError('ยังไม่มีเสียงจากระบบเดิม ให้นำเข้าเสียงหรือสร้างเสียงในโต๊ะตัดต่อ')
        voice = json.loads((self.project.root/'voice_timeline.json').read_text(encoding='utf-8'))
        if voice['script_sha256'] != digest(script_path)['sha256']:
            raise EditError('เสียงเดิมเป็นของบทคนละรุ่น')
        by_id = {s['id']: s for s in data['scenes']}
        for row in voice['scenes']:
            scene = by_id.get(row['scene_id'])
            if scene is None or scene['narration'] != row['text']:
                raise EditError('เสียงเดิมไม่ตรงกับบทที่แก้ในโต๊ะตัดต่อ')
            ref = {'path': row['audio_path'], 'sha256': row['sha256']}
            asset_file(self.project, ref, 'voice')
            scene['voice'] = {**ref, 'duration_seconds': row['duration_seconds'],
                              'text_sha256': fingerprint(scene['narration']), 'provider': voice['provider'],
                              'listening_review': 'PENDING'}
        return self.save(data, expected_revision=data['revision'])

    def add_shot(self, scene_id: str, path: Path, start: float, end: float, *, source_url='', expected_revision: int) -> dict:
        data = self.load()
        if data['revision'] != expected_revision:
            raise EditError('โปรเจกต์ถูกแก้ กรุณาโหลดใหม่ก่อนเลือกภาพ')
        info = probe(path)
        if not any(s['codec_type'] == 'video' for s in info['streams']):
            raise EditError('ไฟล์นี้ไม่มีวิดีโอ')
        start, end = float(start), float(end)
        if not math.isfinite(start + end) or not 0 <= start < end <= info['duration_seconds'] + .05:
            raise EditError('ช่วงภาพต้องอยู่ภายในความยาววิดีโอ')
        asset = self.project.add_file(path, 'footage', source_url=source_url, scenes=[scene_id])
        scene = next(s for s in data['scenes'] if s['id'] == scene_id)
        scene['shots'].append({**media_ref(asset), 'id': 'CUT-'+uuid4().hex[:12],
                               'in_seconds': start, 'out_seconds': end,
                               'source_url': source_url or next(iter(asset['source_urls']), ''),
                               'selection': 'USER_SELECTED', 'original_name': asset['original_name']})
        return self.save(data, expected_revision=data['revision'])

    def trim_shot(self, scene_id: str, shot_id: str, start: float, end: float, *, expected_revision: int) -> dict:
        data = self.load()
        if data['revision'] != expected_revision:
            raise EditError('โปรเจกต์ถูกแก้ กรุณาโหลดใหม่ก่อนปรับช่วงภาพ')
        scene = next((s for s in data['scenes'] if s['id'] == scene_id), None)
        shot = next((s for s in scene['shots'] if s['id'] == shot_id), None) if scene else None
        if shot is None:
            raise EditError('ไม่พบช็อตที่เลือก')
        info = probe(asset_file(self.project, shot, 'footage'))
        start, end = float(start), float(end)
        if not math.isfinite(start + end) or not 0 <= start < end <= info['duration_seconds'] + .05:
            raise EditError('ช่วงภาพต้องอยู่ภายในความยาววิดีโอ')
        shot.update(in_seconds=start, out_seconds=end, selection='USER_SELECTED')
        return self.save(data, expected_revision=expected_revision)

    def preflight(self, data: dict | None = None) -> dict:
        data = deepcopy(data or self.load())
        issues, warnings, timeline = [], [], []
        from .script_review import script_readiness
        script_review = script_readiness(self.project, data)
        research_manifest = script_review['research_manifest_sha256']
        for row in script_review['scenes']:
            warnings.extend(row['scene_id']+': '+issue for issue in row['issues'])
        script = self.project.root/'script.json'
        if script.exists() and digest(script)['sha256'] != data.get('source_script_sha256'):
            warnings.append('เอกสารบทที่นำเข้าเปลี่ยนรุ่นแล้ว โปรดเทียบกับร่างที่กำลังตัดต่อ')
        cursor, fps = 0, data['fps']
        for scene in data['scenes']:
            if not scene['included']:
                continue
            try:
                if not scene['narration'].strip():
                    raise EditError('ยังไม่มีบทพากย์')
                voice = scene.get('voice')
                if not voice or voice.get('text_sha256') != fingerprint(scene['narration']):
                    raise EditError('ยังไม่มีเสียงที่ตรงกับบทปัจจุบัน')
                vpath = asset_file(self.project, voice, 'voice')
                info = probe(vpath)
                if not any(s['codec_type'] == 'audio' for s in info['streams']):
                    raise EditError('ไฟล์เสียงไม่มีแทร็กเสียง')
                frames = math.ceil(info['duration_seconds'] * fps)
                remaining, cuts = frames, []
                for shot in scene['shots']:
                    if shot.get('selection') != 'USER_SELECTED':
                        warnings.append(scene['id']+': ช่วงภาพที่เสนออัตโนมัติยังต้องตรวจความตรงของภาพจริง')
                    path = asset_file(self.project, shot, 'footage')
                    media = probe(path)
                    if not any(s['codec_type'] == 'video' for s in media['streams']):
                        raise EditError('ฟุตเทจไม่มีภาพ')
                    start, end = float(shot['in_seconds']), float(shot['out_seconds'])
                    if not math.isfinite(start + end) or not 0 <= start < end <= media['duration_seconds'] + .05:
                        raise EditError('ช่วงภาพเกินความยาวไฟล์')
                    available = math.floor((end-start) * fps + 1e-6)
                    if available < 1:
                        raise EditError('ช่วงภาพสั้นกว่าหนึ่งเฟรม')
                    take = min(available, remaining)
                    if take:
                        cuts.append({**shot, 'frames': take, 'freeze_frames': 0})
                        remaining -= take
                if remaining:
                    if not cuts or not scene['hold_last_frame']:
                        raise EditError(f'ภาพยังขาด {remaining/fps:.2f} วินาที เพิ่มภาพหรืออนุญาตค้างเฟรมท้าย')
                    cuts[-1]['freeze_frames'] = remaining
                    cuts[-1]['frames'] += remaining
                    warnings.append(scene['id'] + f': ค้างภาพท้าย {remaining/fps:.2f} วินาที')
                if voice.get('listening_review') != 'APPROVED':
                    warnings.append(scene['id']+': ยังไม่ได้ยืนยันการฟังเสียง')
                timeline.append({'scene_id': scene['id'], 'title': scene['title'], 'show_title': scene['show_title'],
                                 'narration': scene['narration'], 'voice': voice, 'cuts': cuts,
                                 'claim_refs': scene.get('claim_refs', []),
                                 'start_frame': cursor, 'frames': frames, 'duration_seconds': frames/fps})
                cursor += frames
            except (ValueError, OSError, StorageError, subprocess.SubprocessError) as exc:
                issues.append({'scene_id': scene['id'], 'detail': str(exc)})
        if not any(s['included'] for s in data['scenes']):
            issues.append({'scene_id': None, 'detail': 'ยังไม่ได้เลือกฉากสำหรับส่งออก'})
        if data.get('music'):
            try:
                info = probe(asset_file(self.project, data['music'], 'music'))
                if not any(s['codec_type'] == 'audio' for s in info['streams']):
                    raise EditError('ไฟล์ดนตรีไม่มีเสียง')
            except (ValueError, OSError, StorageError, subprocess.SubprocessError) as exc:
                issues.append({'scene_id': None, 'detail': str(exc)})
        return {'ready_to_render': not issues, 'issues': issues, 'warnings': warnings,
                'script_review': script_review,
                'research_manifest_sha256': research_manifest,
                'edit_sha256': fingerprint(data), 'edit_revision': data['revision'], 'timeline': timeline,
                'total_frames': cursor, 'duration_seconds': cursor/fps,
                'width': data['width'], 'height': data['height'], 'fps': fps}
