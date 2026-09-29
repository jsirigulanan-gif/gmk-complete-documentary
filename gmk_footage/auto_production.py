from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from .research import FootageResearchReport, InspectedCandidate, BeatResearchResult
from .acquire import YouTubeAcquirer
from .segments import SegmentExtractor
from .assembly import DocumentaryAssembler, TimelineClip, AssemblyResult
from .visual_matcher import VisualSemanticMatcher, VisualTimestampMatch, VisualSemanticError


class AutoProductionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProducedBeat:
    beat_key: str
    selected_video_id: str
    source_url: str
    timestamp: dict[str, float]
    acquired_path: Path
    segment_path: Path
    permission_status: str
    selection_mode: str = "TRANSCRIPT_TIMESTAMP"
    visual_match_manifest: Path | None = None

    def to_dict(self)->dict[str,Any]:
        body={
            'beat_key':self.beat_key,'selected_video_id':self.selected_video_id,'source_url':self.source_url,
            'timestamp':dict(self.timestamp),'acquired_path':str(self.acquired_path),'segment_path':str(self.segment_path),
            'permission_status':self.permission_status,'selection_mode':self.selection_mode,
        }
        if self.visual_match_manifest is not None:
            body['visual_match_manifest']=str(self.visual_match_manifest)
        return body


@dataclass(frozen=True)
class AutoProductionResult:
    beats: tuple[ProducedBeat,...]
    assembly: AssemblyResult
    production_manifest: Path


@dataclass(frozen=True)
class _VisualPick:
    inspected: InspectedCandidate
    acquired: Any
    match: VisualTimestampMatch
    manifest: Path


class AutomaticFootageProductionRuntime:
    """Turn inspected YouTube research into an automatic rough-cut documentary.

    Selection order is evidence-driven:
    1) transcript/caption timestamp matches;
    2) when configured, pixel-grounded visual semantic matching on acquired candidates;
    3) unresolved (never metadata-only guessing).

    Rights remain non-blocking production metadata and acquisition preserves attribution.
    """
    def __init__(self,*,acquirer:YouTubeAcquirer|None=None,extractor:SegmentExtractor|None=None,assembler:DocumentaryAssembler|None=None,visual_matcher:VisualSemanticMatcher|None=None):
        self.acquirer=acquirer or YouTubeAcquirer();self.extractor=extractor or SegmentExtractor();self.assembler=assembler or DocumentaryAssembler();self.visual_matcher=visual_matcher

    @staticmethod
    def _select(candidates:tuple[InspectedCandidate,...])->InspectedCandidate|None:
        valid=[x for x in candidates if x.timestamp_matches]
        if not valid:return None
        return sorted(valid,key=lambda x:(-x.timestamp_matches[0].score,-x.ranked.score,x.ranked.candidate.provider_rank))[0]

    def _visual_pick(self,beat:BeatResearchResult,acq_dir:Path,visual_dir:Path,*,visual_candidates:int,visual_interval:float,visual_threshold:float)->_VisualPick|None:
        if self.visual_matcher is None or beat.search_intent is None:
            return None
        rows=[x for x in beat.candidates if not x.timestamp_matches][:max(0,int(visual_candidates))]
        picks:list[_VisualPick]=[]
        for idx,row in enumerate(rows,1):
            c=row.ranked.candidate
            acquired=self.acquirer.acquire(c,acq_dir)
            try:
                rep=self.visual_matcher.match(
                    beat.search_intent,
                    acquired.local_path,
                    visual_dir/f'{beat.beat_key}_{idx}_{c.video_id}',
                    interval=visual_interval,
                    threshold=visual_threshold,
                )
            except VisualSemanticError:
                continue
            if rep.matches:
                picks.append(_VisualPick(row,acquired,rep.matches[0],rep.match_manifest))
        if not picks:
            return None
        # Visual evidence dominates; metadata rank breaks near-ties, never substitutes for pixels.
        return sorted(picks,key=lambda x:(-x.match.score,-x.inspected.ranked.score,x.inspected.ranked.candidate.provider_rank))[0]

    def run(self,report:FootageResearchReport,output_dir:Path,*,voice_path:Path|None=None,require_all_beats:bool=True,visual_candidates:int=2,visual_interval:float=5.0,visual_threshold:float=0.28)->AutoProductionResult:
        out=Path(output_dir);acq_dir=out/'acquired';seg_dir=out/'segments';visual_dir=out/'visual_inspection';out.mkdir(parents=True,exist_ok=True)
        produced=[];clips=[];unresolved=[]
        for beat in report.beats:
            picked=self._select(beat.candidates)
            if picked:
                c=picked.ranked.candidate;tm=picked.timestamp_matches[0]
                acquired=self.acquirer.acquire(c,acq_dir)
                seg=self.extractor.extract(acquired.local_path,seg_dir/f'{beat.beat_key}.mp4',start=tm.start,end=tm.end,key_time=tm.key_time,metadata={'beat_key':beat.beat_key,'source_url':c.webpage_url,'rank_score':picked.ranked.score,'timestamp_score':tm.score,'selection_mode':'TRANSCRIPT_TIMESTAMP'})
                produced.append(ProducedBeat(beat.beat_key,c.video_id,c.webpage_url,{'start':tm.start,'end':tm.end,'key_time':tm.key_time},acquired.local_path,seg.segment_path,acquired.permission_status,'TRANSCRIPT_TIMESTAMP',None))
                clips.append(TimelineClip(beat.beat_key,seg.segment_path,acquired.attribution,c.webpage_url,acquired.permission_status))
                continue

            visual=self._visual_pick(beat,acq_dir,visual_dir,visual_candidates=visual_candidates,visual_interval=visual_interval,visual_threshold=visual_threshold)
            if visual:
                c=visual.inspected.ranked.candidate;tm=visual.match;acquired=visual.acquired
                seg=self.extractor.extract(acquired.local_path,seg_dir/f'{beat.beat_key}.mp4',start=tm.start,end=tm.end,key_time=tm.key_time,metadata={'beat_key':beat.beat_key,'source_url':c.webpage_url,'rank_score':visual.inspected.ranked.score,'visual_score':tm.score,'selection_mode':'VISUAL_SEMANTIC','visual_match_manifest':str(visual.manifest)})
                produced.append(ProducedBeat(beat.beat_key,c.video_id,c.webpage_url,{'start':tm.start,'end':tm.end,'key_time':tm.key_time},acquired.local_path,seg.segment_path,acquired.permission_status,'VISUAL_SEMANTIC',visual.manifest))
                clips.append(TimelineClip(beat.beat_key,seg.segment_path,acquired.attribution,c.webpage_url,acquired.permission_status))
                continue

            unresolved.append(beat.beat_key)
        if require_all_beats and unresolved:
            raise AutoProductionError('AUTO_PRODUCTION_UNRESOLVED_BEATS: '+','.join(unresolved))
        if not clips:raise AutoProductionError('AUTO_PRODUCTION_NO_CLIPS')
        assembly=self.assembler.assemble(clips,out/'AUTO_ROUGH_CUT.mp4',voice_path=voice_path)
        manifest=out/'AUTO_PRODUCTION_MANIFEST.json'
        body={'report_sha256':report.report_sha256,'unresolved_beats':unresolved,'visual_matcher':None if self.visual_matcher is None else getattr(self.visual_matcher.provider,'name',type(self.visual_matcher.provider).__name__),'produced_beats':[x.to_dict() for x in produced],'assembly':{'output_path':str(assembly.output_path),'duration_seconds':assembly.duration_seconds,'sha256':assembly.sha256,'timeline_manifest':str(assembly.timeline_manifest),'credits_path':str(assembly.credits_path)}}
        manifest.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return AutoProductionResult(tuple(produced),assembly,manifest)
