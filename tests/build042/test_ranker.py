from gmk_footage.query_planner import BeatSearchIntent
from gmk_footage.youtube_provider import YouTubeCandidate
from gmk_footage.ranker import CandidateRanker


def _intent():
    return BeatSearchIntent(
        beat_key="BEAT_TGA",
        beat_ref={"id":"NB_1","version":1},
        priority="CRITICAL",
        viewer_must_see="Geoff Keighley speaking at The Game Awards 2015 about Hideo Kojima",
        viewer_takeaway="Kojima was absent from the stage",
        claim_refs=({"id":"CLM_1","version":1},),
        claim_texts=("Geoff Keighley said Hideo Kojima was not allowed to attend The Game Awards 2015",),
        source_hints=("The Game Awards 2015",),
        entity_terms=("Geoff Keighley","Hideo Kojima","Game Awards","2015"),
        youtube_queries=({"family":"EXACT_ENTITY","query":"Geoff Keighley Hideo Kojima Game Awards 2015"},),
        source_priority=("YOUTUBE","WEB_VIDEO","STILL_DOCUMENT","AI_GENERATED"),
        search_again_before_fallback=True,
    )


def _c(vid,title,desc="",channel="",rank=1,views=0,dur=60,fam="EXACT_ENTITY"):
    return YouTubeCandidate(vid,title,f"https://youtube.com/watch?v={vid}",channel,None,dur,desc,None,views,None,"q",fam,rank)


def test_ranker_prefers_semantically_matching_metadata():
    intent=_intent()
    rows=CandidateRanker.rank(intent,[
        _c("noise","Random gaming montage",rank=1,views=900000),
        _c("match","Geoff Keighley Says Hideo Kojima Wasn't Allowed to Come to The Game Awards 2015",rank=3,views=1000),
    ])
    assert rows[0].candidate.video_id=="match"
    assert rows[0].score>rows[1].score
    assert "kojima" in rows[0].matched_terms
    assert rows[0].score_breakdown["title_coverage"]>0


def test_ranker_penalizes_tiny_clip_and_is_deterministic():
    intent=_intent()
    rows=CandidateRanker.rank(intent,[
        _c("short","Geoff Keighley Hideo Kojima Game Awards 2015",dur=2),
        _c("normal","Geoff Keighley Hideo Kojima Game Awards 2015",dur=60),
    ])
    assert rows[0].candidate.video_id=="normal"
    assert rows[1].score_breakdown["duration_penalty"]<0
    assert CandidateRanker.rank(intent,[rows[1].candidate,rows[0].candidate])[0].candidate.video_id=="normal"
