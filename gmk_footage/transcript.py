from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import html
import re

from .query_planner import BeatSearchIntent


@dataclass(frozen=True)
class TranscriptCue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TimestampMatch:
    start: float
    end: float
    key_time: float
    score: float
    matched_terms: tuple[str, ...]
    transcript_excerpt: str
    cue_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "key_time": self.key_time,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "transcript_excerpt": self.transcript_excerpt,
            "cue_count": self.cue_count,
        }


def _ts(value: str) -> float:
    value=value.strip().replace(',', '.')
    parts=value.split(':')
    if len(parts)==3:
        h,m,s=parts
    elif len(parts)==2:
        h='0';m,s=parts
    else:
        raise ValueError(value)
    return int(h)*3600+int(m)*60+float(s)


def parse_vtt_text(raw: str) -> tuple[TranscriptCue, ...]:
    lines=raw.replace('\r\n','\n').replace('\r','\n').split('\n')
    cues=[];i=0
    while i<len(lines):
        line=lines[i].strip()
        if '-->' not in line:
            i+=1;continue
        left,right=line.split('-->',1)
        right=right.strip().split()[0]
        try:start,end=_ts(left),_ts(right)
        except ValueError:
            i+=1;continue
        i+=1;text=[]
        while i<len(lines) and lines[i].strip():
            t=re.sub(r'<[^>]+>','',lines[i]).strip()
            if t:text.append(html.unescape(t))
            i+=1
        joined=re.sub(r'\s+',' ',' '.join(text)).strip()
        if joined and end>start:
            cues.append(TranscriptCue(start,end,joined))
        i+=1
    return tuple(cues)


def parse_vtt(path: Path) -> tuple[TranscriptCue, ...]:
    return parse_vtt_text(Path(path).read_text(encoding='utf-8',errors='replace'))


def _tokens(text: str) -> set[str]:
    vals=re.findall(r"[A-Za-z0-9][A-Za-z0-9._'-]*",str(text or '').casefold())
    stop={'the','and','for','with','from','that','this','was','were','are','is','to','of','at','in','on','a','an','video','footage'}
    return {x.strip("._'-") for x in vals if len(x.strip("._'-"))>=2 and x not in stop}


class TranscriptTimestampFinder:
    """Find candidate time windows from caption text.

    This is evidence for inspection, not proof that the visuals match. Visual-only Beats
    must later pass frame inspection as a separate stage.
    """

    @classmethod
    def find(cls, intent: BeatSearchIntent, cues: tuple[TranscriptCue,...] | list[TranscriptCue], *, window_seconds: float=24.0, top_k: int=5) -> tuple[TimestampMatch,...]:
        if not cues:return tuple()
        target=_tokens(' '.join([*intent.entity_terms,*intent.claim_texts,intent.viewer_must_see,intent.viewer_takeaway]))
        if not target:return tuple()
        rows=[]
        cues=list(cues)
        for i,c in enumerate(cues):
            end_target=c.start+window_seconds
            j=i;bucket=[]
            while j<len(cues) and cues[j].start<=end_target:
                bucket.append(cues[j]);j+=1
            text=' '.join(x.text for x in bucket)
            got=_tokens(text);matched=target & got
            if not matched:continue
            coverage=len(matched)/len(target)
            entity=_tokens(' '.join(intent.entity_terms))
            entity_cov=len(entity & got)/len(entity) if entity else 0.0
            phrase_bonus=0.0
            low=text.casefold()
            for term in intent.entity_terms:
                if len(term)>=4 and term.casefold() in low:phrase_bonus+=0.04
            score=min(1.0,coverage*0.65+entity_cov*0.30+min(0.12,phrase_bonus))
            start=max(0.0,bucket[0].start-1.5);end=bucket[-1].end+1.5
            rows.append(TimestampMatch(
                start=round(start,3),end=round(end,3),key_time=round((bucket[0].start+bucket[-1].end)/2,3),
                score=round(score,6),matched_terms=tuple(sorted(matched)),
                transcript_excerpt=text[:800],cue_count=len(bucket)
            ))
        # suppress heavily-overlapping lower scores
        rows.sort(key=lambda x:(-x.score,x.start))
        kept=[]
        for row in rows:
            if any(max(0,min(row.end,k.end)-max(row.start,k.start)) / max(0.001,min(row.end-row.start,k.end-k.start)) > 0.7 for k in kept):
                continue
            kept.append(row)
            if len(kept)>=top_k:break
        return tuple(kept)
