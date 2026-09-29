from pathlib import Path
import shutil

import pytest

import gmk_assets.media_handoff as mh
from gmk_assets import MediaHandoffRuntime, MediaHandoffError

ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'pilot'/'PT_WORKSPACE'


def _fake_probe(duration=200.0):
    return {
        'format': {'duration': str(duration), 'format_name':'mov,mp4,m4a,3gp,3g2,mj2'},
        'streams': [
            {'codec_type':'video','codec_name':'h264','width':1920,'height':1080},
            {'codec_type':'audio','codec_name':'aac'},
        ]
    }


def _base_item(candidate_key, local_path, source_url, end=1.0):
    return {
        'candidate_key':candidate_key,
        'local_path':str(local_path),
        'source_url':source_url,
        'acquisition_method':'AUTHORIZED_MANUAL_EXPORT',
        'segment':{
            'selector':{'type':'VIDEO_TIME_RANGE','start_seconds':0.0,'end_seconds':end,'key_seconds':0.5},
            'source_locator':{'type':'FULL_SOURCE'},
            'visual_content':'Verified source-locked audiovisual evidence.',
            'match_type':'DIRECT',
            'match_reason':'The supplied local bytes correspond to the selected source and depict the required moment.'
        }
    }


def test_requirements_expose_immutable_source_locks():
    reqs={r.candidate_key:r for r in MediaHandoffRuntime(ROOT,PILOT).requirements()}
    lisa=reqs['LISA_X_DIRECT_VERIFIED']
    tga=reqs['TGA_VIDEO']
    assert lisa.canonical_source_url=='https://twitter.com/manfightdragon/status/1170860592233472001'
    assert lisa.source_family=='ORIGINAL_CREATOR'
    assert lisa.source_result_id=='SR_000031' and lisa.source_result_version==2
    assert tga.canonical_source_url=='https://www.youtube.com/watch?v=PKl5rYdwM6c'
    assert tga.source_family=='REUPLOAD'
    assert tga.candidate_locator['type']=='VIDEO_TIME_RANGE'
    assert tga.candidate_locator['start_seconds']==0
    assert tga.candidate_locator['end_seconds']==135


def test_handoff_rejects_source_substitution_before_acquisition(tmp_path, monkeypatch):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    f=tmp_path/'video.mp4'; f.write_bytes(b'opaque-video-placeholder')
    monkeypatch.setattr(mh, '_ffprobe', lambda p: _fake_probe())
    runtime=MediaHandoffRuntime(ROOT,ws)
    allowed={r.candidate_key:r for r in runtime.requirements()}
    item=_base_item('TGA_VIDEO',f,'https://www.youtube.com/watch?v=n4VAzkK_Wmc')
    with pytest.raises(MediaHandoffError, match='SOURCE_LOCK_MISMATCH'):
        runtime._compile_item(item,allowed)


def test_handoff_rejects_segment_beyond_inspected_candidate_range(tmp_path, monkeypatch):
    ws=tmp_path/'PT_WORKSPACE'; shutil.copytree(PILOT,ws)
    f=tmp_path/'video.mp4'; f.write_bytes(b'opaque-video-placeholder')
    monkeypatch.setattr(mh, '_ffprobe', lambda p: _fake_probe())
    runtime=MediaHandoffRuntime(ROOT,ws)
    allowed={r.candidate_key:r for r in runtime.requirements()}
    item=_base_item('TGA_VIDEO',f,'https://www.youtube.com/watch?v=PKl5rYdwM6c',end=136.0)
    item['segment']['selector']['key_seconds']=55.0
    with pytest.raises(MediaHandoffError, match='SOURCE_LOCK_RANGE_EXCEEDED'):
        runtime._compile_item(item,allowed)
