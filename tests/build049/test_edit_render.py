import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest

from gmk_projects.edit import EditError, EditSession, asset_file, fingerprint, media_ref
from gmk_projects.render import approve_editorial_review, export_delivery, render_project
from gmk_projects.storage import Project, atomic_json


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True, capture_output=True)


@pytest.fixture
def setup(tmp_path):
    project = Project.create(tmp_path, 'Render integration fixture')
    atomic_json(project.root/'script.json', {'scenes': [
        {'id': 'SHOT-001', 'heading': 'First', 'narration_th': 'ทดสอบฉากแรก'},
        {'id': 'SHOT-002', 'heading': 'Second', 'narration_th': 'ทดสอบฉากสอง'}]})
    video, voice, music = tmp_path/'video.mp4', tmp_path/'voice.wav', tmp_path/'music.wav'
    ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=4', '-an', '-c:v', 'libx264', '-threads', '2', video)
    ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=880:duration=1.23:sample_rate=48000', voice)
    ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=110:duration=0.9:sample_rate=48000', music)
    session = EditSession(project)
    data = session.load()
    data.update(width=640, height=360, fps=25)
    data = session.save(data, expected_revision=data['revision'])
    for scene in data['scenes']:
        data = session.attach_voice(scene['id'], voice, expected_revision=data['revision'])
        data = session.add_shot(scene['id'], video, .2, 2, expected_revision=data['revision'])
    return project, session, video, voice, music


def test_render_measured_voice_music_captions_qa_and_export(setup):
    project, session, video, voice, music = setup
    data = session.load()
    data['music'] = media_ref(project.add_file(music, 'music'))
    data['scenes'][0]['show_title'] = True
    data['scenes'][0]['title'] = 'ฉากแรก · First'
    session.save(data, expected_revision=data['revision'])
    plan = session.preflight()
    assert plan['ready_to_render']
    assert plan['total_frames'] == 62  # 1.23s speech rounded to 31 frames twice.
    result = render_project(project)
    assert result['technical_qa']['passed'], result['technical_qa']
    assert result['matches_current_edit'] and not result['documentary_completed']
    assert result['estimated_caption_scenes'] == ['SHOT-001', 'SHOT-002']
    approve_editorial_review(project, expected_master_sha256=result['technical_qa']['sha256'])
    delivery = export_delivery(project)
    with ZipFile(asset_file(project, delivery['package'])) as archive:
        assert {'documentary.mp4', 'captions.srt', 'timeline.json', 'credits.json', 'qa.json', 'edit.snapshot.json', 'editorial-review.json'}.issubset(archive.namelist())
    assert delivery['drive_status'] == 'PENDING_UPLOAD'
    assert not delivery['documentary_completed']


def test_editing_invalidates_voice_and_rejects_concurrent_saves(setup):
    project, session, *_ = setup
    old = session.load()
    data = session.load()
    data['scenes'][0]['narration'] = 'บทที่เปลี่ยนแล้ว'
    result = session.save(data, expected_revision=data['revision'])
    assert result['scenes'][0]['voice'] is None
    assert not session.preflight()['ready_to_render']
    with pytest.raises(EditError, match='หน้าต่างอื่น'):
        session.save(old, expected_revision=old['revision'])


def test_adjusting_cut_keeps_source_and_rejects_invalid_or_stale_ranges(setup):
    project, session, *_ = setup
    before = session.load()
    scene = before['scenes'][0]
    original = scene['shots'][0]
    changed = session.trim_shot(scene['id'], original['id'], .5, 2.5, expected_revision=before['revision'])
    cut = changed['scenes'][0]['shots'][0]
    assert cut['in_seconds'] == .5 and cut['out_seconds'] == 2.5
    assert cut['path'] == original['path'] and cut['sha256'] == original['sha256']
    assert asset_file(project, cut).is_file()
    with pytest.raises(EditError, match='ถูกแก้'):
        session.trim_shot(scene['id'], original['id'], 0, 1, expected_revision=before['revision'])
    with pytest.raises(EditError, match='ภายใน'):
        session.trim_shot(scene['id'], original['id'], 0, 100, expected_revision=changed['revision'])
    assert session.load() == changed


def test_short_picture_requires_explicit_hold_and_measures_freeze(setup):
    _, session, *_ = setup
    data = session.load()
    data['scenes'][0]['shots'][0]['out_seconds'] = .7
    data = session.save(data, expected_revision=data['revision'])
    assert not session.preflight()['ready_to_render']
    data['scenes'][0]['hold_last_frame'] = True
    session.save(data, expected_revision=data['revision'])
    plan = session.preflight()
    assert plan['ready_to_render']
    assert plan['timeline'][0]['cuts'][0]['freeze_frames'] == 19
    assert plan['warnings']


def test_corrupt_media_and_out_of_bounds_cuts_block_render(setup):
    project, session, *_ = setup
    data = session.load()
    data['scenes'][0]['shots'][0]['out_seconds'] = 100
    session.save(data, expected_revision=data['revision'])
    assert not session.preflight()['ready_to_render']
    asset_file(project, data['scenes'][1]['voice']).write_bytes(b'corrupt')
    assert len(session.preflight()['issues']) == 2


def test_old_render_cannot_be_approved_or_exported_after_edit(setup):
    project, session, *_ = setup
    result = render_project(project)
    approve_editorial_review(project, expected_master_sha256=result['technical_qa']['sha256'])
    data = session.load()
    data['scenes'].reverse()
    session.save(data, expected_revision=data['revision'])
    with pytest.raises(EditError, match='เรนเดอร์'):
        approve_editorial_review(project, expected_master_sha256=result['technical_qa']['sha256'])
    with pytest.raises(EditError, match='ปัจจุบัน'):
        export_delivery(project)


def test_source_revision_invalidates_export_even_without_edit_changes(setup, tmp_path):
    from gmk_projects.intake import import_research
    project, session, *_ = setup
    result=render_project(project)
    approve_editorial_review(project,expected_master_sha256=result['technical_qa']['sha256'])
    source=tmp_path/'new-research.txt';source.write_text('New research\nCLAIM: A newly discovered assertion.')
    import_research(project,source)
    with pytest.raises(EditError,match='รีเสิร์ช'):
        export_delivery(project)


def test_auto_footage_uses_caption_windows_and_retains_source(setup, tmp_path):
    from types import SimpleNamespace
    from gmk_projects.footage import candidate_from_url,prepare_scene_footage
    from gmk_footage.transcript import TranscriptCue
    p,session,video,*_=setup
    data=session.load();scene=data['scenes'][0];scene['shots']=[];scene['visual']='Arcade history';scene['search_queries']=['Arcade history']
    session.save(data,expected_revision=data['revision'])
    class Provider:
        def search(self,*args,**kwargs):return [candidate_from_url('https://youtu.be/abcdefghijk')]
    class Subtitles:
        def fetch(self,*args):
            path=tmp_path/'captions.vtt';path.write_text('WEBVTT\n\n00:00.000 --> 00:03.000\nArcade history\n')
            return SimpleNamespace(raw_vtt_path=path,cues=(TranscriptCue(0,3,'Arcade history'),))
    class Acquirer:
        def acquire(self,*args):
            receipt=tmp_path/'receipt.json';receipt.write_text('{}')
            return SimpleNamespace(local_path=video,receipt_path=receipt,duration_seconds=4)
    result=prepare_scene_footage(p,scene['id'],provider=Provider(),subtitle_fetcher=Subtitles(),acquirer=Acquirer())
    assert result['prepared'] and result['visual_review']=='PENDING'
    assert session.load()['scenes'][0]['shots'][0]['selection']=='CAPTION_NOMINATION_UNREVIEWED'
    assert any('คำบรรยาย' not in warning and 'ภาพจริง' in warning for warning in session.preflight()['warnings'])
    assert any(a['role']=='footage' and 'https://www.youtube.com/watch?v=abcdefghijk' in a['source_urls'] for a in p.read()['assets'])


def test_metadata_alone_never_selects_automatic_footage(setup):
    from gmk_projects.footage import candidate_from_url,prepare_scene_footage
    p,session,*_=setup
    data=session.load();data['scenes'][0]['shots']=[];session.save(data,expected_revision=data['revision'])
    class Provider:
        def search(self,*args,**kwargs):return [candidate_from_url('https://youtu.be/abcdefghijk')]
    class Subtitles:
        def fetch(self,*args):return None
    class Acquirer:
        def acquire(self,*args):pytest.fail('No caption evidence: must not automatically select/download')
    result=prepare_scene_footage(p,'SHOT-001',provider=Provider(),subtitle_fetcher=Subtitles(),acquirer=Acquirer())
    assert not result['prepared']
    assert session.load()['scenes'][0]['shots']==[]
