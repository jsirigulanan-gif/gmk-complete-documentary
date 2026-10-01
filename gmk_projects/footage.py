"""Project footage search/acquisition, with retained candidates and truthful Drive status."""
from dataclasses import fields
from pathlib import Path
import json
from urllib.parse import urlparse, parse_qs

from gmk_footage.acquire import YouTubeAcquirer
from gmk_footage.youtube_provider import YouTubeCandidate, YouTubeDiscoveryProvider
from .edit import EditError, fingerprint, media_ref
from .storage import atomic_json


def search_footage(project, query: str, *, provider=None, limit=6) -> list[dict]:
    provider = provider or YouTubeDiscoveryProvider()
    results = [row.to_dict() for row in provider.search(query, family='DOCUMENTARY_VISUAL', limit=limit)]
    directory = project.root/'footage_research'
    directory.mkdir(exist_ok=True)
    record = {'query': query, 'candidates': results, 'selection_status': 'REQUIRES_CONTENT_INSPECTION'}
    path = directory/(fingerprint(record)+'.json')
    atomic_json(path, record)
    project.add_file(path, 'research')
    return results


def candidate_from_url(url: str) -> YouTubeCandidate:
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('https', 'http') or host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        raise EditError('รองรับลิงก์ YouTube สาธารณะเท่านั้น')
    video_id = parsed.path.strip('/') if host == 'youtu.be' else parse_qs(parsed.query).get('v', [''])[0]
    if not video_id and parsed.path.startswith(('/shorts/', '/embed/')):
        video_id = parsed.path.split('/')[2]
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise EditError('ลิงก์ต้องระบุวิดีโอ YouTube หนึ่งรายการ')
    return YouTubeCandidate(video_id, 'YouTube '+video_id, 'https://www.youtube.com/watch?v='+video_id,
                            '', None, None, '', None, None, None, '', 'USER_URL', 1)


def acquire_footage(project, candidate: dict | YouTubeCandidate, *, acquirer=None) -> dict:
    if isinstance(candidate, dict):
        candidate = YouTubeCandidate(**{field.name: candidate[field.name] for field in fields(YouTubeCandidate)})
    # Normalize identity before it is interpolated into filenames by the downloader.
    normalized = candidate_from_url(candidate.webpage_url)
    if normalized.video_id != candidate.video_id:
        raise EditError('รหัสวิดีโอไม่ตรงกับลิงก์')
    acquired = (acquirer or YouTubeAcquirer(max_height=720)).acquire(candidate, project.root/'acquired_candidates')
    asset = project.add_file(acquired.local_path, 'footage', source_url=candidate.webpage_url)
    receipt = project.add_file(acquired.receipt_path, 'research', source_url=candidate.webpage_url)
    # Network upload is a separate retryable action. Never discard rejected local candidates.
    return {'asset': asset, 'receipt': media_ref(receipt), 'duration_seconds': acquired.duration_seconds,
            'local_path': str(project.root/asset['path']), 'source_url': candidate.webpage_url,
            'drive_status': asset['upload_status'], 'selection_status': 'REQUIRES_CONTENT_INSPECTION'}


def prepare_scene_footage(project, scene_id: str, *, provider=None, subtitle_fetcher=None, acquirer=None, progress=None) -> dict:
    """Propose draft cuts from captions, never claim that text matches prove visual relevance."""
    from .edit import EditSession, asset_file, probe
    from gmk_footage.query_planner import BeatSearchIntent
    from gmk_footage.transcript import TranscriptTimestampFinder
    from gmk_footage.subtitles import YouTubeSubtitleFetcher
    session=EditSession(project);edit=session.load()
    scene=next(s for s in edit['scenes'] if s['id']==scene_id)
    if scene['shots']:
        raise EditError('ฉากนี้มีช็อตอยู่แล้ว ระบบจะไม่แทนที่การตัดต่อเดิม กรุณาเลือกฉากว่าง')
    voice=scene.get('voice')
    if not voice or voice.get('text_sha256')!=fingerprint(scene['narration']):
        raise EditError('สร้างหรือนำเข้าเสียงที่ตรงบทก่อน เพื่อให้ระบบเตรียมช่วงภาพตามระยะเสียงจริง')
    needed=probe(asset_file(project,voice,'voice'))['duration_seconds']
    queries=(scene.get('search_queries') or [scene['visual'] or scene['title']])[:2]
    provider=provider or YouTubeDiscoveryProvider()
    subtitle_fetcher=subtitle_fetcher or YouTubeSubtitleFetcher()
    progress=progress or (lambda _:None)
    candidates={}
    for query in queries:
        progress('กำลังค้น: '+query[:100])
        for row in provider.search(query,family='DRAFT_SCENE',limit=4):
            candidates.setdefault(row.video_id,row)
    intent=BeatSearchIntent(scene_id,{},'STANDARD',scene['visual'],scene['narration'],
                            tuple(scene.get('claim_refs',[])),(),(),tuple(queries),(),('YOUTUBE',),True)
    inspected=[];nominations=[]
    for candidate in list(candidates.values())[:3]:
        # Normalize before subtitle filenames or URLs are passed to external tools.
        if candidate_from_url(candidate.webpage_url).video_id!=candidate.video_id:
            raise EditError('รหัสวิดีโอจากผลค้นหาไม่ตรงลิงก์')
        progress('กำลังตรวจคำบรรยาย: '+candidate.title[:100])
        try:
            subtitles=subtitle_fetcher.fetch(candidate.webpage_url,candidate.video_id)
            matches=()
            if subtitles:
                try:
                    caption_asset=project.add_file(subtitles.raw_vtt_path,'research',source_url=candidate.webpage_url,scenes=[scene_id])
                    matches=TranscriptTimestampFinder.find(intent,subtitles.cues,window_seconds=24,top_k=3)
                finally:
                    subtitles.raw_vtt_path.unlink(missing_ok=True)
            inspected.append({'candidate':candidate.to_dict(),'matches':[m.to_dict() for m in matches],
                              'caption_asset':media_ref(caption_asset) if subtitles else None})
            for match in matches:
                if match.score>=.45:
                    nominations.append((match.score,candidate,match))
        except Exception as exc:
            # A failed candidate does not invent a match or discard other candidates.
            inspected.append({'candidate':candidate.to_dict(),'error':str(exc)[:500],'matches':[]})
    report={'scene_id':scene_id,'base_edit_sha256':fingerprint(edit),'queries':queries,
            'inspected':inspected,'visual_review':'PENDING','selection_basis':'CAPTION_NOMINATION_ONLY'}
    directory=project.root/'footage_research';directory.mkdir(exist_ok=True)
    path=directory/(fingerprint(report)+'.json');atomic_json(path,report)
    report_asset=project.add_file(path,'research',scenes=[scene_id])
    if not nominations:
        return {'prepared':False,'reason':'ไม่มีช่วงคำบรรยายที่มีความเกี่ยวข้องเพียงพอ ต้องค้นเพิ่มหรือตรวจภาพเอง',
                'report':media_ref(report_asset),'visual_review':'PENDING'}
    nominations.sort(key=lambda item:-item[0])
    _,chosen,_=nominations[0]
    progress('กำลังเก็บวิดีโอที่มีช่วงเสนอเข้าคลังโปรเจกต์')
    acquired=acquire_footage(project,chosen,acquirer=acquirer)
    duration=probe(Path(acquired['local_path']))['duration_seconds']
    cuts=[];remaining=needed;used=[]
    for _,candidate,match in nominations:
        if candidate.video_id!=chosen.video_id or remaining<=0:continue
        start,end=max(0,match.start),min(duration,match.end)
        if any(max(a,start)<min(b,end) for a,b in used):continue
        end=min(end,start+remaining+.05)
        if end-start<1/edit['fps']:continue
        cuts.append({**media_ref(acquired['asset']),'id':'CUT-'+fingerprint({'scene':scene_id,'start':start,'video':candidate.video_id})[:12],
                     'in_seconds':start,'out_seconds':end,'original_name':candidate.title,
                     'source_url':candidate.webpage_url,'selection':'CAPTION_NOMINATION_UNREVIEWED',
                     'nomination_report':media_ref(report_asset)})
        used.append((start,end));remaining-=end-start
    if not cuts:
        return {'prepared':False,'reason':'ช่วงที่เสนออยู่นอกไฟล์วิดีโอที่ได้รับ','report':media_ref(report_asset)}
    scene['shots']=cuts
    session.save(edit,expected_revision=edit['revision'])
    return {'prepared':True,'scene_id':scene_id,'cuts':len(cuts),'uncovered_seconds':max(0,remaining),
            'visual_review':'PENDING','drive_status':'PENDING_UPLOAD','report':media_ref(report_asset)}


def prepare_project_footage(project, *, progress=None) -> dict:
    """Resume missing scenes; keep every completed scene and downloaded candidate on failures."""
    from .edit import EditSession
    session=EditSession(project);results=[]
    selected=[s for s in session.load()['scenes'] if s['included'] and not s['shots']]
    progress=progress or (lambda _:None)
    for index,scene in enumerate(selected,1):
        progress(f'เตรียมภาพฉาก {index}/{len(selected)} · '+scene['title'])
        try:
            result=prepare_scene_footage(project,scene['id'],progress=progress)
        except Exception as exc:
            result={'prepared':False,'scene_id':scene['id'],'reason':str(exc)}
        results.append(result)
        atomic_json(project.root/'footage_progress.json',{'scenes':results,'total_requested':len(selected)})
    return {'scenes':results,'preflight':session.preflight()}
