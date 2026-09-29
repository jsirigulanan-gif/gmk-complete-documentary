from __future__ import annotations
from dataclasses import dataclass
from typing import Any

SOURCE_ORDER=('YOUTUBE','WEB_VIDEO','STILL_DOCUMENT','AI_GENERATED')

@dataclass(frozen=True)
class SourceDecision:
    selected_source:str
    action:str
    reason:str
    search_again_required:bool
    ai_last_resort:bool
    def to_dict(self)->dict[str,Any]:
        return {'selected_source':self.selected_source,'action':self.action,'reason':self.reason,'search_again_required':self.search_again_required,'ai_last_resort':self.ai_last_resort}

class SourcePriorityController:
    """Enforce the documentary material hierarchy agreed for GMK.

    AI is never chosen while a higher-priority source has not exhausted its configured
    search-again attempt. This controller is policy only; providers stay separate.
    """
    @staticmethod
    def decide(*,youtube_ready:bool,youtube_search_rounds:int,web_video_ready:bool,web_search_rounds:int,still_ready:bool,still_search_rounds:int,max_search_rounds:int=2)->SourceDecision:
        if youtube_ready:return SourceDecision('YOUTUBE','USE_SOURCE','YouTube candidate passed inspection.',False,False)
        if youtube_search_rounds<max_search_rounds:return SourceDecision('YOUTUBE','SEARCH_AGAIN','YouTube remains highest-priority and has not exhausted search rounds.',True,False)
        if web_video_ready:return SourceDecision('WEB_VIDEO','USE_SOURCE','YouTube exhausted; web/archive video candidate is ready.',False,False)
        if web_search_rounds<max_search_rounds:return SourceDecision('WEB_VIDEO','SEARCH_AGAIN','Web/archive video remains available before still-image fallback.',True,False)
        if still_ready:return SourceDecision('STILL_DOCUMENT','USE_SOURCE','Video sources exhausted; real still/document evidence is ready.',False,False)
        if still_search_rounds<max_search_rounds:return SourceDecision('STILL_DOCUMENT','SEARCH_AGAIN','Real still/document search must be exhausted before AI.',True,False)
        return SourceDecision('AI_GENERATED','GENERATE_LAST_RESORT','All real-material tiers exhausted configured search rounds.',False,True)
