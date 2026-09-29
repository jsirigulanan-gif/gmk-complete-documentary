from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib,json

from .query_planner import FootageQueryPlanner, BeatSearchIntent
from .youtube_provider import YouTubeDiscoveryProvider, YouTubeCandidate
from .ranker import CandidateRanker, RankedCandidate
from .subtitles import YouTubeSubtitleFetcher
from .transcript import TranscriptTimestampFinder, TimestampMatch


@dataclass(frozen=True)
class InspectedCandidate:
    ranked: RankedCandidate
    timestamp_matches: tuple[TimestampMatch,...]
    caption_available: bool

    def to_dict(self)->dict[str,Any]:
        return {'ranked':self.ranked.to_dict(),'caption_available':self.caption_available,'timestamp_matches':[x.to_dict() for x in self.timestamp_matches]}

@dataclass(frozen=True)
class BeatResearchResult:
    beat_key:str
    beat_ref:dict[str,Any]
    discovered_count:int
    inspected_count:int
    candidates:tuple[InspectedCandidate,...]
    fallback_status:str
    search_intent: BeatSearchIntent | None = None

    def to_dict(self)->dict[str,Any]:
        body={'beat_key':self.beat_key,'beat_ref':dict(self.beat_ref),'discovered_count':self.discovered_count,'inspected_count':self.inspected_count,'candidates':[x.to_dict() for x in self.candidates],'fallback_status':self.fallback_status}
        if self.search_intent is not None:
            body['search_intent']=self.search_intent.to_dict()
        return body

@dataclass(frozen=True)
class FootageResearchReport:
    plan_sha256:str
    beats:tuple[BeatResearchResult,...]
    report_sha256:str
    source_priority:tuple[str,...]

    def to_dict(self)->dict[str,Any]:
        return {'plan_sha256':self.plan_sha256,'source_priority':list(self.source_priority),'beats':[x.to_dict() for x in self.beats],'report_sha256':self.report_sha256}


class FootageResearchRuntime:
    """YouTube-first, read-only footage research orchestrator.

    It searches all query families, deduplicates, ranks metadata, and inspects captions for
    top candidates. It does not acquire video bytes and does not mutate the project workspace.
    """
    def __init__(self,schema_root:Path,workspace:Path,*,provider:YouTubeDiscoveryProvider|None=None,subtitle_fetcher:YouTubeSubtitleFetcher|None=None):
        self.schema_root=Path(schema_root);self.workspace=Path(workspace)
        self.provider=provider or YouTubeDiscoveryProvider()
        self.subtitle_fetcher=subtitle_fetcher or YouTubeSubtitleFetcher()

    @staticmethod
    def _merge_candidates(rows:list[YouTubeCandidate]) -> list[YouTubeCandidate]:
        # Keep the earliest provider result per video id; ranker sees originating family/query.
        best={}
        for c in rows:
            prior=best.get(c.video_id)
            if prior is None or c.provider_rank<prior.provider_rank:
                best[c.video_id]=c
        return list(best.values())

    def run(self,*,per_query:int=5,inspect_top:int=3,timestamp_top:int=3)->FootageResearchReport:
        plan=FootageQueryPlanner(self.schema_root,self.workspace).build()
        beat_results=[]
        for intent in plan.beat_intents:
            discovered=[]
            for q in intent.youtube_queries:
                discovered.extend(self.provider.search(q['query'],family=q['family'],limit=per_query))
            merged=self._merge_candidates(discovered)
            ranked=CandidateRanker.rank(intent,merged)
            inspected=[]
            for row in ranked[:inspect_top]:
                sub=self.subtitle_fetcher.fetch(row.candidate.webpage_url,row.candidate.video_id)
                matches=TranscriptTimestampFinder.find(intent,sub.cues,top_k=timestamp_top) if sub else tuple()
                inspected.append(InspectedCandidate(row,matches,sub is not None))
                if sub and sub.raw_vtt_path.exists():
                    sub.raw_vtt_path.unlink(missing_ok=True)
            has_timestamp=any(x.timestamp_matches for x in inspected)
            fallback='YOUTUBE_CANDIDATE_READY' if ranked and has_timestamp else ('YOUTUBE_VISUAL_INSPECTION_REQUIRED' if ranked else 'SEARCH_AGAIN_YOUTUBE')
            beat_results.append(BeatResearchResult(intent.beat_key,intent.beat_ref,len(merged),len(inspected),tuple(inspected),fallback,intent))
        body={'plan_sha256':plan.plan_sha256,'source_priority':list(plan.source_priority),'beats':[x.to_dict() for x in beat_results]}
        sha=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return FootageResearchReport(plan.plan_sha256,tuple(beat_results),sha,plan.source_priority)
