from pathlib import Path
from types import SimpleNamespace
from gmk_footage.research import FootageResearchRuntime
from gmk_footage.youtube_provider import YouTubeCandidate
from gmk_footage.transcript import TranscriptCue

ROOT=Path(__file__).resolve().parents[2];WS=ROOT/'pilot/PT_WORKSPACE'

class FakeProvider:
 def search(self,q,*,family,limit):
  key=abs(hash(q))%999999
  return (
   YouTubeCandidate(f'v{key}',f'P.T. Hideo Kojima 7780 Game Awards Lisa {q[:40]}','https://www.youtube.com/watch?v=x','Archive',None,120,'P.T. Hideo Kojima Game Awards 2015 Lisa 7780',None,1000,None,q,family,1),
  )
class FakeSubs:
 def fetch(self,url,video_id):
  return SimpleNamespace(cues=(TranscriptCue(10,15,'Hideo Kojima P.T. Game Awards 2015 7780 Lisa'),),raw_vtt_path=Path('/definitely/not/there'))

def test_research_runtime_covers_all_pt_beats_read_only():
 before=(WS/'CURRENT_MANIFEST.json').read_bytes()
 r=FootageResearchRuntime(ROOT,WS,provider=FakeProvider(),subtitle_fetcher=FakeSubs()).run(per_query=1,inspect_top=2)
 after=(WS/'CURRENT_MANIFEST.json').read_bytes()
 assert before==after
 assert len(r.beats)==10
 assert all(x.discovered_count>=1 for x in r.beats)
 assert all(x.inspected_count<=2 for x in r.beats)
 assert r.source_priority[0]=='YOUTUBE'
 assert len(r.report_sha256)==64
