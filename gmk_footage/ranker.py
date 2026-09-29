from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import re

from .query_planner import BeatSearchIntent
from .youtube_provider import YouTubeCandidate


def _tokens(text: str) -> set[str]:
    vals = re.findall(r"[A-Za-z0-9][A-Za-z0-9._'-]*", str(text or "").casefold())
    stop = {"the","and","for","with","from","that","this","video","footage","archive","original","pt"}
    return {x.strip("._'-") for x in vals if len(x.strip("._'-")) >= 2 and x not in stop}


def _coverage(target: set[str], text: str) -> float:
    if not target:
        return 0.0
    got = _tokens(text)
    return len(target & got) / len(target)


@dataclass(frozen=True)
class RankedCandidate:
    candidate: YouTubeCandidate
    score: float
    score_breakdown: dict[str, float]
    matched_terms: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "matched_terms": list(self.matched_terms),
        }


class CandidateRanker:
    """Explainable metadata ranker used before transcript/timestamp inspection.

    It is deliberately conservative: metadata can nominate candidates, but never marks
    a clip production-ready. Timestamp/transcript inspection remains mandatory later.
    """

    FAMILY_BONUS = {
        "EXACT_ENTITY": 0.08,
        "EVENT_ARCHIVE": 0.06,
        "QUOTE_SOURCE": 0.05,
        "VISUAL_TARGET": 0.04,
    }

    @classmethod
    def rank(cls, intent: BeatSearchIntent, candidates: list[YouTubeCandidate] | tuple[YouTubeCandidate, ...]) -> tuple[RankedCandidate, ...]:
        entity_terms = {t.casefold() for t in intent.entity_terms if t.strip()}
        entity_tokens = _tokens(" ".join(intent.entity_terms))
        claim_tokens = _tokens(" ".join(intent.claim_texts))
        visual_tokens = _tokens(intent.viewer_must_see)
        ranked: list[RankedCandidate] = []
        for c in candidates:
            blob = " ".join([c.title, c.description, c.channel, c.query])
            title_blob = c.title
            entity_cov = _coverage(entity_tokens, blob)
            claim_cov = _coverage(claim_tokens, blob)
            visual_cov = _coverage(visual_tokens, blob)
            title_cov = _coverage(entity_tokens | claim_tokens, title_blob)
            family_bonus = cls.FAMILY_BONUS.get(c.query_family, 0.0)
            provider_bonus = max(0.0, 0.05 - (max(1, c.provider_rank)-1) * 0.005)
            views_bonus = 0.0
            if c.view_count and c.view_count > 0:
                views_bonus = min(0.04, math.log10(c.view_count + 1) / 200.0)
            duration_penalty = 0.0
            if c.duration_seconds is not None:
                if c.duration_seconds < 8:
                    duration_penalty = -0.10
                elif c.duration_seconds > 4 * 60 * 60:
                    duration_penalty = -0.03
            score = (
                entity_cov * 0.35
                + claim_cov * 0.18
                + visual_cov * 0.15
                + title_cov * 0.20
                + family_bonus
                + provider_bonus
                + views_bonus
                + duration_penalty
            )
            score = max(0.0, min(1.0, score))
            cand_tokens = _tokens(blob)
            matched = tuple(sorted((entity_tokens | claim_tokens | visual_tokens) & cand_tokens))
            ranked.append(RankedCandidate(
                candidate=c,
                score=round(score, 6),
                score_breakdown={
                    "entity_coverage": round(entity_cov, 6),
                    "claim_coverage": round(claim_cov, 6),
                    "visual_coverage": round(visual_cov, 6),
                    "title_coverage": round(title_cov, 6),
                    "query_family_bonus": round(family_bonus, 6),
                    "provider_rank_bonus": round(provider_bonus, 6),
                    "views_bonus": round(views_bonus, 6),
                    "duration_penalty": round(duration_penalty, 6),
                },
                matched_terms=matched,
            ))
        ranked.sort(key=lambda x: (-x.score, x.candidate.provider_rank, x.candidate.video_id))
        return tuple(ranked)
