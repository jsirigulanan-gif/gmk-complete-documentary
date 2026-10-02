"""Render exact editable project snapshots with measured speech, cuts and ducked music."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from .edit import EditError, EditSession, asset_file, fingerprint, media_ref, probe
from .storage import atomic_json, digest
from .production import ProductionProject


def _run(args, *, cwd=None, timeout=3600):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise EditError('เครื่องมือวิดีโอทำงานไม่สำเร็จ: ' + (result.stderr or result.stdout)[-1800:])
    return result


def _ffmpeg(*args):
    return [os.environ.get('GMK_FFMPEG', 'ffmpeg'), '-hide_banner', '-loglevel', 'error',
            '-nostdin', '-y', '-filter_threads', '1', '-filter_complex_threads', '1', *map(str, args)]


def _clock(seconds):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{sec:02},{ms:03}'


def _seconds(value):
    h, m, s = value.replace(',', '.').split(':')
    return int(h)*3600 + int(m)*60 + float(s)


def _title_ass(title, width, height):
    # libass performs font fallback for mixed Thai/Latin text. A script-only Thai
    # font in drawtext can otherwise render Latin headings as missing-glyph boxes.
    text=title[:120].replace('\\','/').replace('{','(').replace('}',')').replace('\n',' ')
    return (f'[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n'
            '[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n'
            f'Style: Title,Noto Sans,{max(16,height//28)},&H00FFFFFF,&H00FFFFFF,&H99000000,&H99000000,0,0,0,0,100,100,0,0,3,8,0,1,{width//20},{width//20},{height//10},1\n'
            '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
            f'Dialogue: 0,0:00:00.00,0:00:03.00,Title,,0,0,0,,{text}\n')


def _captions(project, timeline, fps):
    entries, estimated = [], []
    for scene in timeline:
        offset = scene['start_frame']/fps
        duration = scene['duration_seconds']
        subtitle = scene['voice'].get('subtitles')
        rows = []
        if subtitle:
            text = asset_file(project, subtitle, 'voice').read_text(encoding='utf-8-sig')
            for block in re.split(r'\n\s*\n', text.replace('\r', '').strip()):
                lines = block.splitlines()
                timing = next((i for i, line in enumerate(lines) if ' --> ' in line), None)
                if timing is None:
                    continue
                left, right = lines[timing].split(' --> ')
                start, end = max(0, _seconds(left)), min(duration, _seconds(right.split()[0]))
                caption = '\n'.join(lines[timing+1:]).strip()
                if caption and start < end:
                    rows.append((start, end, caption))
        if not rows:
            # Explicitly estimated when no provider alignment exists; never certify lip/word sync.
            estimated.append(scene['scene_id'])
            text = scene['narration'].strip()
            parts = [text[i:i+72] for i in range(0, len(text), 72)]
            cursor = 0
            for part in parts:
                end = cursor + duration*len(part)/len(text)
                rows.append((cursor, end, part))
                cursor = end
        entries.extend((offset+a, offset+b, text) for a, b, text in rows)
    return '\n\n'.join(f'{i}\n{_clock(a)} --> {_clock(b)}\n{text}' for i, (a,b,text) in enumerate(entries, 1))+'\n', estimated


def technical_qa(path: Path, expected: dict) -> dict:
    info = probe(path)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    issues = []
    if not video or not audio:
        issues.append('Missing video or audio stream')
    if video and (video['width'], video['height']) != (expected['width'], expected['height']):
        issues.append('Unexpected resolution')
    if abs(info['duration_seconds']-expected['duration_seconds']) > max(.15, 2/expected['fps']):
        issues.append('Duration differs from measured timeline')
    if video and int(video.get('nb_frames', -1)) != expected['total_frames']:
        issues.append('Frame count differs from planned cuts')
    if video and audio:
        for stream in (video, audio):
            duration = float(stream.get('duration', 0))
            if abs(duration-expected['duration_seconds']) > max(.15, 2/expected['fps']):
                issues.append('Audio/video stream length differs from timeline')
        result = subprocess.run(_ffmpeg('-v', 'error', '-i', path, '-map', '0:v:0', '-map', '0:a:0',
                                        '-f', 'null', '-'), capture_output=True, text=True, timeout=3600)
        if result.returncode or result.stderr.strip():
            issues.append('Full-file decode found errors: '+result.stderr[-800:])
    return {'passed': not issues, 'issues': issues, 'duration_seconds': info['duration_seconds'],
            'sha256': digest(path)['sha256'], 'full_decode_checked': bool(video and audio),
            'editorial_review': 'PENDING', 'caption_alignment_review': 'PENDING',
            'scope': 'Technical stream/duration/frame/decode checks only; factual and visual relevance require editorial review.'}


def render_project(project, *, progress=None) -> dict:
    edit = EditSession(project)
    snapshot = edit.load()
    plan = edit.preflight(snapshot)
    if not plan['ready_to_render']:
        raise EditError('ยังเรนเดอร์ไม่ได้: ' + '; '.join(f"{x['scene_id'] or 'โปรเจกต์'}: {x['detail']}" for x in plan['issues']))
    root = project.root/'renders'/('render-'+uuid4().hex[:12])
    root.mkdir(parents=True)
    atomic_json(root/'edit.snapshot.json', snapshot)
    atomic_json(root/'timeline.json', plan)
    atomic_json(root/'script-review.json', plan['script_review'])
    if shutil.disk_usage(root).free < max(150_000_000, int(plan['duration_seconds']*2_000_000)):
        raise EditError('พื้นที่ว่างไม่พอสำหรับไฟล์ชั่วคราวและวิดีโอ กรุณาเพิ่มพื้นที่ก่อนเรนเดอร์')
    subtitles, estimated = _captions(project, plan['timeline'], plan['fps'])
    (root/'captions.srt').write_text(subtitles, encoding='utf-8')
    fps, width, height = plan['fps'], plan['width'], plan['height']
    report = progress or (lambda message: None)
    try:
        with tempfile.TemporaryDirectory(dir=root, prefix='.work-') as temporary:
            temp = Path(temporary)
            videos, voices, credits = [], [], []
            for index, scene in enumerate(plan['timeline']):
                report(f'กำลังเตรียมภาพและเสียงฉาก {index+1}/{len(plan["timeline"])}')
                for cut_index, cut in enumerate(scene['cuts']):
                    output = temp/f'cut-{index:04}-{cut_index:04}.mp4'
                    source = asset_file(project, cut, 'footage')
                    duration = float(cut['out_seconds'])-float(cut['in_seconds'])
                    vf = (f'trim=duration={duration:.9f},setpts=PTS-STARTPTS,'
                          f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
                          f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},'
                          f'tpad=stop_mode=clone:stop_duration={(cut["freeze_frames"]+1)/fps:.9f},format=yuv420p')
                    if scene['show_title'] and cut_index == 0:
                        # Source text stays in a text file, never interpolated into a filter expression.
                        (temp/'title.ass').write_text(_title_ass(scene['title'],width,height), encoding='utf-8')
                        vf += ',ass=title.ass'
                    _run(_ffmpeg('-ss', f'{cut["in_seconds"]:.9f}', '-i', source, '-map', '0:v:0',
                                 '-vf', vf, '-frames:v', cut['frames'], '-an', '-c:v', 'libx264',
                                 '-threads', '2', '-preset', 'veryfast', '-crf', '20', output), cwd=temp)
                    videos.append(output.name)
                    credits.append({'scene_id': scene['scene_id'], 'original_name': cut['original_name'],
                                    'source_url': cut.get('source_url', ''), 'source_sha256': cut['sha256'],
                                    'source_in': cut['in_seconds'], 'source_out': cut['out_seconds'],
                                    'used_frames': cut['frames'], 'freeze_frames': cut['freeze_frames'],
                                    'permission_status': 'PENDING_PERMISSION'})
                wave = temp/f'voice-{index:04}.wav'
                # Use sample counts derived from video frames to avoid cumulative AAC segment drift.
                samples = round(scene['frames']*48000/fps)
                _run(_ffmpeg('-i', asset_file(project, scene['voice'], 'voice'), '-map', '0:a:0',
                             '-af', f'aresample=48000,apad,atrim=end_sample={samples},asetpts=PTS-STARTPTS',
                             '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', wave))
                voices.append(wave.name)
            for name, files in (('video', videos), ('voice', voices)):
                (temp/(name+'.txt')).write_text(''.join(f"file '{p}'\n" for p in files), encoding='utf-8')
            report('กำลังรวมภาพ ผสมดนตรี และสร้างไฟล์ MP4')
            video, voice = temp/'video.mp4', temp/'voice.wav'
            _run(_ffmpeg('-f', 'concat', '-safe', '1', '-i', temp/'video.txt', '-c', 'copy', video))
            _run(_ffmpeg('-f', 'concat', '-safe', '1', '-i', temp/'voice.txt', '-c', 'copy', voice))
            master = root/'preview.mp4'
            args = ['-i', video, '-i', voice]
            output_args = []
            if snapshot.get('music'):
                args += ['-stream_loop', '-1', '-i', asset_file(project, snapshot['music'], 'music')]
                mix = (f'[1:a]asplit=2[voice][side];[2:a]volume={snapshot["music_gain"]}[music];'
                       '[music][side]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=300[duck];'
                       '[voice][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[a]')
                output_args += ['-filter_complex', mix, '-map', '0:v:0', '-map', '[a]']
                subtitle_index = 3
            else:
                output_args += ['-map', '0:v:0', '-map', '1:a:0']
                subtitle_index = 2
            args += ['-i', root/'captions.srt', *output_args, '-map', f'{subtitle_index}:s:0', '-c:s', 'mov_text',
                     '-metadata:s:s:0', 'language=tha', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                     '-ar', '48000', '-t', f'{plan["duration_seconds"]:.9f}', '-movflags', '+faststart', master]
            _run(_ffmpeg(*args))
        report('กำลังถอดรหัสตรวจวิดีโอทั้งไฟล์และเทียบระยะเวลา')
        qa = technical_qa(master, plan)
        # Refuse a render whose supposedly immutable input changed during encoding.
        for scene in plan['timeline']:
            asset_file(project, scene['voice'], 'voice')
            for cut in scene['cuts']:
                asset_file(project, cut, 'footage')
        if snapshot.get('music'):
            asset_file(project, snapshot['music'], 'music')
        atomic_json(root/'qa.json', qa)
        atomic_json(root/'credits.json', {'shots': credits, 'music': snapshot.get('music'),
                                        'music_gain': snapshot['music_gain']})
        atomic_json(root/'render.json', {'edit_sha256': plan['edit_sha256'], 'master_sha256': qa['sha256'],
                                        'research_manifest_sha256': plan['research_manifest_sha256'],
                                        'estimated_caption_scenes': estimated, 'technical_qa_passed': qa['passed'],
                                        'documentary_completed': False})
        # Freeze every output before registration; interrupted/failed work is retained in renders/.
        registered = {}
        for name in ('preview.mp4', 'captions.srt', 'timeline.json', 'edit.snapshot.json', 'qa.json', 'credits.json', 'render.json', 'script-review.json'):
            registered[name] = media_ref(project.add_file(root/name, 'exports' if name == 'preview.mp4' else 'timeline'))
        current = fingerprint(edit.load()) == plan['edit_sha256']
        result = {'render_directory': str(root), 'master_path': str(master), 'registered': registered,
                  'research_manifest_sha256': plan['research_manifest_sha256'],
                  'edit_sha256': plan['edit_sha256'], 'technical_qa': qa, 'matches_current_edit': current,
                  'estimated_caption_scenes': estimated, 'documentary_completed': False}
        result['script_review_ready'] = plan['script_review']['ready']
        atomic_json(project.root/'last_render.json', result)
        return result
    except Exception as exc:
        atomic_json(root/'failure.json', {'error': str(exc), 'edit_sha256': plan['edit_sha256']})
        raise


def approve_editorial_review(project, *, expected_master_sha256: str, checklist: dict | None = None) -> dict:
    """Called by an explicit full-film review decision, never automatically by rendering."""
    if checklist is not None:
        from .workflow import FILM_CHECKS
        if set(checklist) != set(FILM_CHECKS) or any(v is not True for v in checklist.values()):
            raise EditError('ตรวจสารคดีทั้งเรื่องและยืนยันรายการให้ครบก่อนบันทึก')
    with project._lock():
        render = json.loads((project.root/'last_render.json').read_text(encoding='utf-8'))
        if render['technical_qa']['sha256'] != expected_master_sha256:
            raise EditError('วิดีโอเปลี่ยนหลังเปิดตรวจ กรุณาตรวจรุ่นใหม่')
        if fingerprint(EditSession(project).load()) != render['edit_sha256']:
            raise EditError('บทหรือไทม์ไลน์เปลี่ยนแล้ว ต้องเรนเดอร์และตรวจใหม่')
        if ProductionProject(project).status()['manifest_sha256'] != render['research_manifest_sha256']:
            raise EditError('รีเสิร์ชหรือผลตรวจหลักฐานเปลี่ยนแล้ว ต้องเรนเดอร์และตรวจใหม่')
        asset_file(project, render['registered']['preview.mp4'], 'exports')
        if not render['technical_qa']['passed']:
            raise EditError('วิดีโอยังไม่ผ่านการตรวจทางเทคนิค')
        decision = {'master_sha256': expected_master_sha256, 'edit_sha256': render['edit_sha256'],
                    'research_manifest_sha256': render['research_manifest_sha256'],
                    'editorial_review': 'USER_APPROVED', 'scope': 'Local full-film picture, sound and caption review; canonical research/release gates are separate.'}
        if checklist is not None:
            decision['full_film_checklist'] = dict(checklist)
        atomic_json(project.root/'editorial_review.json', decision)
    return decision


def export_delivery(project) -> dict:
    from .delivery import current_reviewed_render
    render, decision, files, script = current_reviewed_render(project)
    destination = project.root/'deliveries'
    destination.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination,prefix='.package-') as folder:
        archive = Path(folder)/'documentary-delivery.zip'
        with ZipFile(archive, 'w') as bundle:
            for name, source in sorted(files.items()):
                info = ZipInfo('documentary.mp4' if name == 'preview.mp4' else name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_STORED if name.endswith('.mp4') else ZIP_DEFLATED
                with source.open('rb') as stream, bundle.open(info, 'w', force_zip64=True) as dest:
                    shutil.copyfileobj(stream, dest, length=1024*1024)
            bundle.writestr(ZipInfo('editorial-review.json', date_time=(1980, 1, 1, 0, 0, 0)),
                            json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
        asset = project.add_file(archive, 'exports')
    result = {'project_id': project.read()['project_id'],
              'package': media_ref(asset), 'master': render['registered']['preview.mp4'],
              'edit_sha256': render['edit_sha256'], 'drive_status': 'PENDING_UPLOAD',
              'research_manifest_sha256': render['research_manifest_sha256'],
              'registered': render['registered'], 'editorial_review': decision,
              'package_kind': 'REVIEWED_LOCAL_DRAFT',
              'script_review_ready': script.get('ready') is True,
              'documentary_completed': False}
    record_path = destination/('delivery-'+asset['sha256']+'.json')
    atomic_json(record_path, result)
    record = project.add_file(record_path, 'timeline')
    with project._lock():
        current, current_decision, _, _ = current_reviewed_render(project)
        if current['registered'] != render['registered'] or current_decision != decision:
            raise EditError('วิดีโอหรือผลตรวจเปลี่ยนระหว่างสร้างชุดส่งออก กรุณาสร้างชุดใหม่')
        data = project.read()
        data['active_delivery_asset'] = media_ref(record)
        data['storage_status'] = 'PENDING_UPLOAD'
        atomic_json(project.manifest, data)
    return result
