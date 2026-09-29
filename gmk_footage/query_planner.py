from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re

from gmk_runtime.cold_start import ColdStartLoader


SOURCE_PRIORITY = ("YOUTUBE", "WEB_VIDEO", "STILL_DOCUMENT", "AI_GENERATED")
QUERY_FAMILIES = ("EXACT_ENTITY", "EVENT_ARCHIVE", "QUOTE_SOURCE", "VISUAL_TARGET")


def _sha256_json(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: (int(x.get("order", 999999)), x["id"]))


def _beat_key(beat: dict[str, Any]) -> str:
    return str((((beat.get("extensions") or {}).get("rough_narrative") or {}).get("key")) or beat["id"])


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ascii_entities(*values: str) -> list[str]:
    """Extract searchable Latin-script/numeric terms without pretending to translate Thai.

    We deliberately avoid machine translation at this deterministic planning layer. English
    names, products, event names, dates and quoted tokens are retained; Thai visual text is
    preserved separately as a full visual-target query.
    """
    joined = " ".join(_clean_spaces(v) for v in values if v)
    chunks = re.findall(r"[A-Za-z][A-Za-z0-9.+'’&:/_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9.+'’&:/_-]*){0,5}|\b\d{3,8}\b", joined)
    seen: set[str] = set()
    out: list[str] = []
    stop = {"the", "and", "for", "with", "from", "that", "this", "when", "into", "before", "after", "studio"}
    for chunk in chunks:
        c = _clean_spaces(chunk).strip(" ,.;:()[]{}\"'")
        if not c or c.casefold() in stop:
            continue
        key = c.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _query(base: str, extras: list[str], suffix: str | None = None, *, limit: int = 180) -> str:
    parts = [_clean_spaces(base)] + [_clean_spaces(x) for x in extras if _clean_spaces(x)]
    if suffix:
        parts.append(_clean_spaces(suffix))
    q = " ".join(dict.fromkeys(x for x in parts if x))
    return q[:limit].rstrip()


@dataclass(frozen=True)
class BeatSearchIntent:
    beat_key: str
    beat_ref: dict[str, Any]
    priority: str
    viewer_must_see: str
    viewer_takeaway: str
    claim_refs: tuple[dict[str, Any], ...]
    claim_texts: tuple[str, ...]
    source_hints: tuple[str, ...]
    entity_terms: tuple[str, ...]
    youtube_queries: tuple[dict[str, str], ...]
    source_priority: tuple[str, ...]
    search_again_before_fallback: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "beat_key": self.beat_key,
            "beat_ref": dict(self.beat_ref),
            "priority": self.priority,
            "viewer_must_see": self.viewer_must_see,
            "viewer_takeaway": self.viewer_takeaway,
            "claim_refs": [dict(x) for x in self.claim_refs],
            "claim_texts": list(self.claim_texts),
            "source_hints": list(self.source_hints),
            "entity_terms": list(self.entity_terms),
            "youtube_queries": [dict(x) for x in self.youtube_queries],
            "source_priority": list(self.source_priority),
            "search_again_before_fallback": self.search_again_before_fallback,
        }


@dataclass(frozen=True)
class FootageQueryPlan:
    project_ref: dict[str, Any]
    project_title: str
    plan_sha256: str
    beat_intents: tuple[BeatSearchIntent, ...]
    source_priority: tuple[str, ...] = SOURCE_PRIORITY

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "project_ref": dict(self.project_ref),
            "project_title": self.project_title,
            "source_priority": list(self.source_priority),
            "beat_intents": [x.to_dict() for x in self.beat_intents],
        }
        return {**payload, "plan_sha256": self.plan_sha256}


class FootageQueryPlanner:
    """Deterministic query planner for the Complete Documentary Maker.

    Milestone 1 is intentionally network-free and non-mutating. It converts current
    Narration Beats + audited Claims into YouTube-first search intents. Providers,
    acquisition and editing are separate later layers.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.schema_root = Path(schema_root)
        self.workspace = Path(workspace)

    @staticmethod
    def _claim_map(state) -> dict[tuple[str, int], dict[str, Any]]:
        out: dict[tuple[str, int], dict[str, Any]] = {}
        for claim in _active_objects(state, "CLAIM"):
            out[(claim["id"], int(claim["version"]))] = claim
        return out

    @staticmethod
    def _project(state) -> dict[str, Any]:
        projects = _active_objects(state, "PROJECT")
        if len(projects) != 1:
            raise RuntimeError(f"FOOTAGE_QUERY_PROJECT_COUNT_INVALID: {len(projects)}")
        return projects[0]

    @classmethod
    def from_state(cls, state) -> FootageQueryPlan:
        project = cls._project(state)
        project_title = _clean_spaces(project.get("working_title") or project.get("title") or "")
        if not project_title:
            raise RuntimeError("FOOTAGE_QUERY_PROJECT_TITLE_REQUIRED")
        claims = cls._claim_map(state)
        intents: list[BeatSearchIntent] = []

        for beat in _active_objects(state, "NARRATION_BEAT"):
            vr = beat.get("visual_requirement") or {}
            must_see = _clean_spaces(vr.get("viewer_must_see") or "")
            if not must_see:
                raise RuntimeError(f"FOOTAGE_QUERY_VISUAL_REQUIREMENT_MISSING: {_beat_key(beat)}")
            priority = str(vr.get("priority") or "STANDARD")
            bindings = beat.get("claim_bindings") or []
            claim_refs: list[dict[str, Any]] = []
            claim_texts: list[str] = []
            source_hints: list[str] = []
            for binding in bindings:
                ref = binding.get("claim_ref") or {}
                key = (str(ref.get("id") or ""), int(ref.get("version") or 0))
                claim = claims.get(key)
                if not claim:
                    raise RuntimeError(f"FOOTAGE_QUERY_CLAIM_REF_UNRESOLVED: {_beat_key(beat)}:{key[0]}@{key[1]}")
                claim_refs.append({"id": claim["id"], "version": int(claim["version"])})
                text = _clean_spaces(claim.get("claim_text") or "")
                if text:
                    claim_texts.append(text)
                hint = _clean_spaces((((claim.get("extensions") or {}).get("intake") or {}).get("source_hint")) or "")
                if hint:
                    source_hints.append(hint)

            entities = _ascii_entities(project_title, must_see, beat.get("viewer_takeaway") or "", *claim_texts, *source_hints)
            core_entities = entities[:8]
            base = project_title
            # Keep four families distinct so provider/ranker can learn which strategy won.
            q_exact = _query(base, core_entities[:5])
            q_event = _query(base, core_entities[:7], "original footage archive")
            q_quote = _query(base, list(dict.fromkeys(source_hints))[:2] + core_entities[:4], "video")
            # Preserve the actual visual target, even if Thai; providers may still return useful results.
            q_visual = _query(base, [must_see], "footage")
            queries = (
                {"family": "EXACT_ENTITY", "query": q_exact},
                {"family": "EVENT_ARCHIVE", "query": q_event},
                {"family": "QUOTE_SOURCE", "query": q_quote},
                {"family": "VISUAL_TARGET", "query": q_visual},
            )
            if any(not x["query"] for x in queries):
                raise RuntimeError(f"FOOTAGE_QUERY_EMPTY: {_beat_key(beat)}")

            intents.append(BeatSearchIntent(
                beat_key=_beat_key(beat),
                beat_ref={"id": beat["id"], "version": int(beat["version"])},
                priority=priority,
                viewer_must_see=must_see,
                viewer_takeaway=_clean_spaces(beat.get("viewer_takeaway") or ""),
                claim_refs=tuple(claim_refs),
                claim_texts=tuple(claim_texts),
                source_hints=tuple(dict.fromkeys(source_hints)),
                entity_terms=tuple(core_entities),
                youtube_queries=queries,
                source_priority=SOURCE_PRIORITY,
                search_again_before_fallback=True,
            ))

        if not intents:
            raise RuntimeError("FOOTAGE_QUERY_NO_NARRATION_BEATS")
        body = {
            "project_ref": {"id": project["id"], "version": int(project["version"])},
            "project_title": project_title,
            "source_priority": list(SOURCE_PRIORITY),
            "beat_intents": [x.to_dict() for x in intents],
        }
        return FootageQueryPlan(
            project_ref=body["project_ref"],
            project_title=project_title,
            plan_sha256=_sha256_json(body),
            beat_intents=tuple(intents),
        )

    def build(self) -> FootageQueryPlan:
        cold = ColdStartLoader(self.schema_root, self.workspace).load()
        return self.from_state(cold.engine.snapshot())
