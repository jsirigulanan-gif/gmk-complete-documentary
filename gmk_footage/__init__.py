from .query_planner import FootageQueryPlanner, FootageQueryPlan, BeatSearchIntent
from .youtube_provider import YouTubeDiscoveryProvider, YouTubeCandidate
from .ranker import CandidateRanker, RankedCandidate
from .subtitles import YouTubeSubtitleFetcher
from .transcript import TranscriptTimestampFinder, TranscriptCue, TimestampMatch
from .research import FootageResearchRuntime, FootageResearchReport
from .fallback_research import MaterialFallbackResearchRuntime, MaterialResearchReport
from .source_policy import SourcePriorityController, SourceDecision
from .acquire import YouTubeAcquirer, AcquiredFootage
from .segments import SegmentExtractor, ExtractedSegment
from .frames import FrameSampler, FrameInspectionBundle
from .assembly import DocumentaryAssembler, TimelineClip, AssemblyResult
from .auto_production import AutomaticFootageProductionRuntime, AutoProductionResult
from .web_sources import InternetArchiveProvider, NasaMediaProvider, WikimediaStillProvider, WebSourceCandidate
from .material_acquire import WebVideoAcquirer, StillImageAcquirer, StillClipRenderer, AcquiredMaterial
from .visual_matcher import VisualSemanticMatcher, VisualMatchReport, VisualTimestampMatch, VisualFrameScore, OllamaVisionProvider, SidecarVisionProvider

__all__ = [name for name in globals() if not name.startswith('_')]
