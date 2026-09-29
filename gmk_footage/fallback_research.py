from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib, json

from .query_planner import FootageQueryPlanner
from .research import FootageResearchReport
from .web_sources import InternetArchiveProvider, NasaMediaProvider, WikimediaStillProvider, WebSourceCandidate


@dataclass(frozen=True)
class BeatMaterialResult:
    beat_key: str
    selected_tier: str
    youtube_status: str
    web_video_candidates: tuple[WebSourceCandidate,...]
    still_candidates: tuple[WebSourceCandidate,...]
    ai_last_resort: bool
    search_rounds: dict[str,int]
    def to_dict(self)->dict[str,Any]:
        return {'beat_key':self.beat_key,'selected_tier':self.selected_tier,'youtube_status':self.youtube_status,
            'web_video_candidates':[x.to_dict() for x in self.web_video_candidates],
            'still_candidates':[x.to_dict() for x in self.still_candidates],
            'ai_last_resort':self.ai_last_resort,'search_rounds':dict(self.search_rounds)}

@dataclass(frozen=True)
class MaterialResearchReport:
    footage_report_sha256:str
    beats:tuple[BeatMaterialResult,...]
    report_sha256:str
    def to_dict(self)->dict[str,Any]:
        return {'footage_report_sha256':self.footage_report_sha256,'beats':[x.to_dict() for x in self.beats],'report_sha256':self.report_sha256}


class MaterialFallbackResearchRuntime:
    """Apply GMK material priority after YouTube research.

    Two distinct query families are tried for each real-material tier before falling lower.
    This does not download media; it only produces candidate evidence and tier decisions.
    """
    def __init__(self,schema_root:Path,workspace:Path,*,archive=None,nasa=None,wikimedia=None):
        self.schema_root=Path(schema_root);self.workspace=Path(workspace)
        self.archive=archive or InternetArchiveProvider();self.nasa=nasa or NasaMediaProvider();self.wikimedia=wikimedia or WikimediaStillProvider()

    @staticmethod
    def _dedupe(rows:list[WebSourceCandidate])->tuple[WebSourceCandidate,...]:
        out=[];seen=set()
        for x in rows:
            key=(x.provider,x.page_url,x.media_url)
            if key in seen:continue
            seen.add(key);out.append(x)
        return tuple(out)

    def run(self,youtube_report:FootageResearchReport,*,per_query:int=5)->MaterialResearchReport:
        plan=FootageQueryPlanner(self.schema_root,self.workspace).build()
        intents={x.beat_key:x for x in plan.beat_intents}
        yt={x.beat_key:x for x in youtube_report.beats}
        rows=[]
        for beat_key,intent in intents.items():
            y=yt.get(beat_key)
            ystatus=y.fallback_status if y else 'SEARCH_AGAIN_YOUTUBE'
            if ystatus=='YOUTUBE_CANDIDATE_READY':
                rows.append(BeatMaterialResult(beat_key,'YOUTUBE',ystatus,tuple(),tuple(),False,{'YOUTUBE':1,'WEB_VIDEO':0,'STILL_DOCUMENT':0}));continue
            # Search-again semantics: use two different query families before lowering tier.
            queries=[q['query'] for q in intent.youtube_queries[:2]]
            web=[]
            for q in queries:
                try:web.extend(self.archive.search(q,limit=per_query))
                except Exception:pass
                try:web.extend(self.nasa.search(q,media_type='video',limit=per_query))
                except Exception:pass
            web=self._dedupe(web)
            if web:
                rows.append(BeatMaterialResult(beat_key,'WEB_VIDEO',ystatus,web,tuple(),False,{'YOUTUBE':2,'WEB_VIDEO':2,'STILL_DOCUMENT':0}));continue
            still=[]
            for q in queries:
                try:still.extend(self.wikimedia.search(q,limit=per_query))
                except Exception:pass
                try:still.extend(self.nasa.search(q,media_type='image',limit=per_query))
                except Exception:pass
            still=self._dedupe(still)
            if still:
                rows.append(BeatMaterialResult(beat_key,'STILL_DOCUMENT',ystatus,tuple(),still,False,{'YOUTUBE':2,'WEB_VIDEO':2,'STILL_DOCUMENT':2}));continue
            rows.append(BeatMaterialResult(beat_key,'AI_GENERATED',ystatus,tuple(),tuple(),True,{'YOUTUBE':2,'WEB_VIDEO':2,'STILL_DOCUMENT':2}))
        body={'footage_report_sha256':youtube_report.report_sha256,'beats':[x.to_dict() for x in rows]}
        sha=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return MaterialResearchReport(youtube_report.report_sha256,tuple(rows),sha)
