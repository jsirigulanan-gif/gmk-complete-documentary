from pathlib import Path
import stat,tempfile

from gmk_footage.subtitles import YouTubeSubtitleFetcher


def _fake(tmp:Path,write=True,rc=0):
 p=tmp/'yt-dlp'
 code='''#!/usr/bin/env python3
import pathlib,sys
args=sys.argv[1:]
out=args[args.index('-o')+1]
vid='abc123'
path=pathlib.Path(out.replace('%(id)s',vid).replace('%(ext)s','en.vtt'))
path.parent.mkdir(parents=True,exist_ok=True)
WRITE
raise SystemExit(RC)
'''.replace('WRITE',"path.write_text('WEBVTT\\n\\n00:00:01.000 --> 00:00:03.000\\nHideo Kojima\\n',encoding='utf-8')" if write else '').replace('RC',str(rc))
 p.write_text(code,encoding='utf-8');p.chmod(p.stat().st_mode|stat.S_IXUSR);return p


def test_fetcher_gets_vtt_without_video_bytes():
 with tempfile.TemporaryDirectory() as td:
  exe=_fake(Path(td))
  r=YouTubeSubtitleFetcher(exe).fetch('https://youtube.com/watch?v=abc123','abc123')
  assert r is not None
  assert len(r.cues)==1
  assert r.cues[0].text=='Hideo Kojima'
  assert r.raw_vtt_path.exists()
  r.raw_vtt_path.unlink()


def test_no_caption_returns_none():
 with tempfile.TemporaryDirectory() as td:
  exe=_fake(Path(td),write=False,rc=0)
  assert YouTubeSubtitleFetcher(exe).fetch('https://youtube.com/watch?v=abc123','abc123') is None
