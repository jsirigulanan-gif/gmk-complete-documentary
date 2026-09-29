from pathlib import Path
import hashlib

from gmk_footage.query_planner import FootageQueryPlanner, SOURCE_PRIORITY

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / "pilot" / "PT_WORKSPACE"


def _pointer_hash() -> str:
    return hashlib.sha256((WS / "CURRENT_MANIFEST.json").read_bytes()).hexdigest()


def test_pt_query_plan_covers_every_current_beat_and_is_non_mutating():
    before = _pointer_hash()
    plan = FootageQueryPlanner(ROOT, WS).build()
    after = _pointer_hash()
    assert before == after
    assert len(plan.beat_intents) == 10
    assert plan.source_priority == SOURCE_PRIORITY
    assert len(plan.plan_sha256) == 64
    assert all(x.youtube_queries and len(x.youtube_queries) == 4 for x in plan.beat_intents)
    assert all(x.source_priority[0] == "YOUTUBE" for x in plan.beat_intents)
    assert all(x.search_again_before_fallback for x in plan.beat_intents)


def test_pt_queries_are_distinct_traceable_and_nonempty():
    plan = FootageQueryPlanner(ROOT, WS).build()
    keys = [x.beat_key for x in plan.beat_intents]
    assert len(keys) == len(set(keys)) == 10
    for intent in plan.beat_intents:
        families = [q["family"] for q in intent.youtube_queries]
        assert families == ["EXACT_ENTITY", "EVENT_ARCHIVE", "QUOTE_SOURCE", "VISUAL_TARGET"]
        assert all(q["query"].strip() for q in intent.youtube_queries)
        assert intent.viewer_must_see.strip()
        assert intent.claim_refs


def test_pt_plan_contains_expected_searchable_entities():
    plan = FootageQueryPlanner(ROOT, WS).build()
    text = "\n".join(q["query"] for i in plan.beat_intents for q in i.youtube_queries)
    assert "P.T." in text
    assert "Hideo Kojima" in text
    assert "7780" in text
