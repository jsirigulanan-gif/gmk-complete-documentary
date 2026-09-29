from pathlib import Path
from gmk_footage.fallback_research import MaterialFallbackResearchRuntime
from gmk_footage.research import FootageResearchReport,BeatResearchResult
from gmk_footage.web_sources import WebSourceCandidate
ROOT=Path(__file__).resolve().parents[2];WS=ROOT/'pilot/PT_WORKSPACE'

class Archive:
 def __init__(self,yes):self.yes=yes
 def search(self,q,limit=5):return (WebSourceCandidate('ARCH','VIDEO','web', 'https://a',None,'c','d',None,'WEB_VIDEO',1),) if self.yes else ()
class Nasa:
 def __init__(self,video=False,image=False):self.video=video;self.image=image
 def search(self,q,media_type='video',limit=5):
  yes=self.video if media_type=='video' else self.image
  return (WebSourceCandidate('NASA',media_type.upper(),'nasa','https://n', 'https://media','NASA','d',None,'WEB_VIDEO' if media_type=='video' else 'STILL_DOCUMENT',1),) if yes else ()
class Wiki:
 def __init__(self,yes):self.yes=yes
 def search(self,q,limit=5):return (WebSourceCandidate('WIKI','IMAGE','still','https://w','https://img','c','d','CC','STILL_DOCUMENT',1),) if self.yes else ()

def _yt(status):
 beats=tuple(BeatResearchResult(f'BEAT_{i}',{'id':f'NB{i}','version':1},0,0,tuple(),status) for i in range(1,11))
 # Beat keys won't match P.T. plan; use actual keys in test below via generated lightweight report.
 return FootageResearchReport('p',beats,'r',('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED'))

def _report_for_plan():
 from gmk_footage.query_planner import FootageQueryPlanner
 plan=FootageQueryPlanner(ROOT,WS).build()
 beats=tuple(BeatResearchResult(x.beat_key,x.beat_ref,0,0,tuple(),'SEARCH_AGAIN_YOUTUBE') for x in plan.beat_intents)
 return FootageResearchReport(plan.plan_sha256,beats,'r',plan.source_priority)

def test_fallback_prefers_web_video_before_still():
 x=MaterialFallbackResearchRuntime(ROOT,WS,archive=Archive(True),nasa=Nasa(),wikimedia=Wiki(True)).run(_report_for_plan(),per_query=1)
 assert all(b.selected_tier=='WEB_VIDEO' for b in x.beats)

def test_fallback_uses_still_then_ai_last():
 s=MaterialFallbackResearchRuntime(ROOT,WS,archive=Archive(False),nasa=Nasa(),wikimedia=Wiki(True)).run(_report_for_plan(),per_query=1)
 assert all(b.selected_tier=='STILL_DOCUMENT' for b in s.beats)
 a=MaterialFallbackResearchRuntime(ROOT,WS,archive=Archive(False),nasa=Nasa(),wikimedia=Wiki(False)).run(_report_for_plan(),per_query=1)
 assert all(b.selected_tier=='AI_GENERATED' and b.ai_last_resort for b in a.beats)
