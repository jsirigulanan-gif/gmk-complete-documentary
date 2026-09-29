from gmk_footage.source_policy import SourcePriorityController

def test_never_falls_back_before_search_again_exhausted():
 x=SourcePriorityController.decide(youtube_ready=False,youtube_search_rounds=1,web_video_ready=True,web_search_rounds=0,still_ready=True,still_search_rounds=0)
 assert x.selected_source=='YOUTUBE' and x.action=='SEARCH_AGAIN'

def test_web_then_still_then_ai_last():
 x=SourcePriorityController.decide(youtube_ready=False,youtube_search_rounds=2,web_video_ready=True,web_search_rounds=0,still_ready=True,still_search_rounds=0)
 assert x.selected_source=='WEB_VIDEO'
 y=SourcePriorityController.decide(youtube_ready=False,youtube_search_rounds=2,web_video_ready=False,web_search_rounds=2,still_ready=True,still_search_rounds=0)
 assert y.selected_source=='STILL_DOCUMENT'
 z=SourcePriorityController.decide(youtube_ready=False,youtube_search_rounds=2,web_video_ready=False,web_search_rounds=2,still_ready=False,still_search_rounds=2)
 assert z.selected_source=='AI_GENERATED' and z.ai_last_resort
