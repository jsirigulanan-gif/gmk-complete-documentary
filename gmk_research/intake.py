from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state.errors import StateEngineError

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class ResearchIntakeError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _strip_md(text: str) -> str:
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = text.replace('*', '')
    return re.sub(r'\s+', ' ', text).strip()


def _source_hint_from_claim(text: str) -> tuple[str, str | None]:
    clean = _strip_md(text)
    m = re.search(r'\s*\(Source:\s*(.*?)\)\s*$', clean, flags=re.I)
    if not m:
        return clean, None
    return clean[:m.start()].strip(), m.group(1).strip()


@dataclass(frozen=True)
class ParsedItem:
    declared_id: str
    paragraph: int
    section: str
    raw_text: str
    text: str
    source_hint: str | None = None
    claim_type: str | None = None


@dataclass(frozen=True)
class ParsedSourceLead:
    declared_id: str
    paragraph: int
    title: str
    publisher: str
    published_at: str
    url: str
    declared_authority: str
    declared_confidence: str
    summary: str


@dataclass(frozen=True)
class ParsedGap:
    paragraph: int
    title: str
    question: str


@dataclass(frozen=True)
class ParsedQuote:
    paragraph: int
    speaker: str
    context: str
    quote: str
    source_hint: str | None


@dataclass(frozen=True)
class ResearchPackParseResult:
    title: str
    paragraphs: tuple[str, ...]
    claims: tuple[ParsedItem, ...]
    source_leads: tuple[ParsedSourceLead, ...]
    gaps: tuple[ParsedGap, ...]
    quotes: tuple[ParsedQuote, ...]
    explicit_contradictions: tuple[str, ...]

    def counts(self) -> dict[str, int]:
        return {
            'claims': len(self.claims),
            'source_leads': len(self.source_leads),
            'unresolved_questions': len(self.gaps),
            'quotes': len(self.quotes),
            'explicit_contradictions': len(self.explicit_contradictions),
        }


class ResearchPackParser:
    """Deterministic intake parser for the supplied P.T. Research Pack.

    Parsing is intentionally not factual verification. Labels such as VERIFIED FACT
    are preserved as declared metadata but imported Claim objects stay UNREVIEWED.
    """

    def read_paragraphs(self, path: Path) -> list[str]:
        path = Path(path)
        if not path.is_file():
            raise ResearchIntakeError(f'RESEARCH_PACK_NOT_FOUND: {path}')
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read('word/document.xml')
        except Exception as exc:
            raise ResearchIntakeError(f'RESEARCH_PACK_DOCX_INVALID: {exc}') from exc
        root = ET.fromstring(xml)
        out: list[str] = []
        for p in root.iter(f'{{{W_NS}}}p'):
            parts: list[str] = []
            for node in p.iter():
                if node.tag == f'{{{W_NS}}}t' and node.text:
                    parts.append(node.text)
                elif node.tag == f'{{{W_NS}}}tab':
                    parts.append('\t')
                elif node.tag == f'{{{W_NS}}}br':
                    parts.append('\n')
            out.append(''.join(parts).strip())
        return out

    @staticmethod
    def _sections(paragraphs: list[str]) -> dict[str, list[tuple[int, str]]]:
        sections: dict[str, list[tuple[int, str]]] = {}
        current = 'ROOT'
        heading = re.compile(r'^\d{2}_[A-Za-z0-9_]+$')
        for idx, text in enumerate(paragraphs, start=1):
            if heading.match(text):
                current = text
                sections.setdefault(current, [])
                continue
            sections.setdefault(current, []).append((idx, text))
        return sections

    def parse(self, path: Path) -> ResearchPackParseResult:
        paragraphs = self.read_paragraphs(path)
        sections = self._sections(paragraphs)
        title = next((p for p in paragraphs if p.upper().startswith('RESEARCH PACK:')), Path(path).stem)

        claims: list[ParsedItem] = []
        claim_re = re.compile(r'^-\s*`\[(FACT-\d+)\]`\s*\*\*\[VERIFIED FACT\]\*\*\s*(.*)$')
        for para, text in sections.get('02_Verified_Facts', []):
            m = claim_re.match(text)
            if not m:
                continue
            assertion, source_hint = _source_hint_from_claim(m.group(2))
            claims.append(ParsedItem(m.group(1), para, '02_Verified_Facts', text, assertion, source_hint, 'FACTUAL_ASSERTION'))

        theory_re = re.compile(r'^-\s*`\[((?:THEORY|RUMOR|INTERPRETATION)-\d+)\]`\s*\*\*\[([^\]]+)\]\*\*\s*(.*)$')
        for para, text in sections.get('05_Community_Theories_and_Rumors', []):
            m = theory_re.match(text)
            if not m:
                continue
            prefix = m.group(1).split('-', 1)[0]
            ctype = {'THEORY': 'COMMUNITY_THEORY', 'RUMOR': 'RUMOR', 'INTERPRETATION': 'INTERPRETATION'}[prefix]
            assertion, source_hint = _source_hint_from_claim(m.group(3))
            claims.append(ParsedItem(m.group(1), para, '05_Community_Theories_and_Rumors', text, assertion, source_hint, ctype))

        source_leads: list[ParsedSourceLead] = []
        source_re = re.compile(
            r'^-\s*`\[(SRC-\d+)\]`\s*\*\*(.*?)\*\*\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(https?://\S+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*)$'
        )
        for para, text in sections.get('07_Source_Library', []):
            m = source_re.match(text)
            if not m:
                continue
            source_leads.append(ParsedSourceLead(
                declared_id=m.group(1), paragraph=para, title=_strip_md(m.group(2)), publisher=_strip_md(m.group(3)),
                published_at=_strip_md(m.group(4)), url=m.group(5).strip(), declared_authority=_strip_md(m.group(6)),
                declared_confidence=_strip_md(m.group(7)), summary=_strip_md(m.group(8)),
            ))

        gaps: list[ParsedGap] = []
        gap_re = re.compile(r'^\d+\.\s*\*\*(.*?):\*\*\s*(.*)$')
        for para, text in sections.get('11_Unresolved_Questions', []):
            m = gap_re.match(text)
            if m:
                gaps.append(ParsedGap(para, _strip_md(m.group(1)), _strip_md(m.group(2))))

        quotes: list[ParsedQuote] = []
        quote_header = re.compile(r'^\d+\.\s*\*\*(.*?)\s*\((.*?)\):\*\*$')
        qsec = sections.get('10_Quotes', [])
        i = 0
        while i < len(qsec):
            para, text = qsec[i]
            m = quote_header.match(text)
            if not m:
                i += 1
                continue
            quote = ''
            source_hint = None
            if i + 1 < len(qsec):
                quote = _strip_md(qsec[i + 1][1]).strip('"')
            if i + 2 < len(qsec):
                sm = re.search(r'Direct Quote\s*-\s*(.*?)\)?$', _strip_md(qsec[i + 2][1]), flags=re.I)
                if sm:
                    source_hint = sm.group(1).strip()
            if quote:
                quotes.append(ParsedQuote(para, _strip_md(m.group(1)), _strip_md(m.group(2)), quote, source_hint))
            i += 3

        # The supplied pack has no explicit contradiction registry/section. Do not invent one.
        contradictions: tuple[str, ...] = ()
        return ResearchPackParseResult(title, tuple(paragraphs), tuple(claims), tuple(source_leads), tuple(gaps), tuple(quotes), contradictions)


def _evidence_scope(item: ParsedItem) -> list[str]:
    t = item.text.lower()
    if item.claim_type in {'COMMUNITY_THEORY', 'INTERPRETATION'}:
        return ['INTERPRETATION']
    if item.claim_type == 'RUMOR':
        return ['MOTIVE']
    if 'lisa' in t or 'กล้อง' in t:
        return ['TECHNICAL_BEHAVIOR']
    if 'ยอด' in t or 'ราคา' in t or '1 ล้าน' in t:
        return ['QUANTITY']
    if 'สัญญา' in t or 'วันที่' in t or 'เมื่อวันที่' in t:
        return ['TIMELINE']
    if 'รหัส' in t or 'หมายถึง' in t:
        return ['INTERPRETATION']
    return ['EVENT']


@dataclass(frozen=True)
class ResearchIntakeResult:
    workspace: Path
    project_state: str
    manifest_version: int
    batch_id: str
    research_pack_sha256: str
    source_ref: dict[str, Any]
    attempt_ref: dict[str, Any]
    claim_refs: tuple[dict[str, Any], ...]
    evidence_refs: tuple[dict[str, Any], ...]
    gap_refs: tuple[dict[str, Any], ...]
    source_leads: tuple[ParsedSourceLead, ...]
    quotes: tuple[ParsedQuote, ...]
    explicit_contradictions: int
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'workspace': str(self.workspace),
            'project_state': self.project_state,
            'manifest_version': self.manifest_version,
            'batch_id': self.batch_id,
            'research_pack_sha256': self.research_pack_sha256,
            'source_ref': self.source_ref,
            'attempt_ref': self.attempt_ref,
            'claims_created': len(self.claim_refs),
            'evidence_created': len(self.evidence_refs),
            'research_gaps_created': len(self.gap_refs),
            'source_leads_parsed': len(self.source_leads),
            'quotes_parsed': len(self.quotes),
            'explicit_contradictions_parsed': self.explicit_contradictions,
            'idempotent_replay': self.idempotent_replay,
            'research_audit_status': 'NOT_PASSED',
            'scope_note': 'Intake records preserve Research Pack assertions as UNREVIEWED/PROHIBITED. External sources and quoted originals have not been independently verified by this runtime step.',
        }


class ResearchIntakeRuntime:
    """Convert an immutable Research Pack into safe research-intake records.

    It never upgrades pack labels into verified truth. Every imported assertion is
    UNREVIEWED and prohibited from narration until a later Research Audit revision.
    """

    def __init__(self, runtime_root: Path, workspace: Path):
        self.root = Path(runtime_root)
        self.workspace = Path(workspace)
        self.parser = ResearchPackParser()

    def _research_pack_artifact(self, state) -> dict[str, Any]:
        candidates = [a for a in state.artifacts.values() if a.get('artifact_type') == 'RESEARCH_PACK']
        if not candidates:
            raise ResearchIntakeError('RESEARCH_PACK_MISSING')
        return max(candidates, key=lambda a: (a['artifact_id'], int(a['version'])))

    def _research_pack_path(self, artifact: dict[str, Any]) -> Path:
        for note in artifact.get('notes', []):
            if note.startswith('input_path='):
                p = self.workspace / note.split('=', 1)[1]
                if p.is_file():
                    return p
        inputs = sorted((self.workspace / 'inputs' / 'research').glob('*.docx')) if (self.workspace / 'inputs' / 'research').exists() else []
        if len(inputs) == 1:
            return inputs[0]
        raise ResearchIntakeError('RESEARCH_PACK_INPUT_PATH_UNRESOLVED')

    @staticmethod
    def _find_existing_attempt(state, batch_id: str) -> dict[str, Any] | None:
        hits = []
        for a in state.artifacts.values():
            if a.get('artifact_type') != 'RESEARCH_ATTEMPT_LOG':
                continue
            if (a.get('extensions') or {}).get('intake_batch_id') == batch_id:
                hits.append(a)
        return max(hits, key=lambda a: int(a['version'])) if hits else None

    def run(self) -> ResearchIntakeResult:
        loaded = ColdStartLoader(self.root, self.workspace).load()
        engine = loaded.engine
        state = engine.snapshot()
        pack_art = self._research_pack_artifact(state)
        pack_path = self._research_pack_path(pack_art)
        pack_sha = _sha256_file(pack_path)
        batch_id = 'PT_INTAKE_' + pack_sha[:16].upper()
        parsed = self.parser.parse(pack_path)

        existing = self._find_existing_attempt(state, batch_id)
        if existing:
            intake = (existing.get('extensions') or {}).get('intake_summary') or {}
            return ResearchIntakeResult(
                self.workspace, engine.project_state, engine.manifest_version, batch_id, pack_sha,
                intake.get('pack_source_ref') or {},
                {'artifact_id': existing['artifact_id'], 'artifact_type': existing['artifact_type'], 'version': int(existing['version']), 'sha256': existing['sha256']},
                tuple(intake.get('claim_refs') or ()), tuple(intake.get('evidence_refs') or ()), tuple(intake.get('gap_refs') or ()),
                parsed.source_leads, parsed.quotes, len(parsed.explicit_contradictions), True,
            )

        if engine.project_state not in {'BOOTSTRAPPED', 'RESEARCH_INTAKE'}:
            raise ResearchIntakeError(f'RESEARCH_INTAKE_STATE_INVALID: {engine.project_state}')

        tx = engine.begin()
        if engine.project_state == 'BOOTSTRAPPED':
            tx.transition_project_state('RESEARCH_INTAKE', actor_type='AI')

        pack_source_ref = tx.create_object('SOURCE', {
            'source_type': 'DOCUMENT',
            'title': parsed.title,
            'publisher': 'User-supplied Research Pack',
            'platform': 'GMK Workspace',
            'authority_class': 'UNKNOWN',
            'independence': {'group_id': 'SRCGRP_RESEARCH_PACK_PT', 'relationship': 'ORIGINAL'},
            'language': 'th-TH',
            'availability': {'state': 'ARCHIVED'},
            'accessed_at': engine.now(),
            'notes': f'Immutable Research Pack intake copy. sha256={pack_sha}. This SOURCE proves what the pack says, not whether external claims are true.',
            'extensions': {
                'intake': {
                    'batch_id': batch_id,
                    'research_pack_artifact_ref': pack_art and {'artifact_id': pack_art['artifact_id'], 'artifact_type': pack_art['artifact_type'], 'version': int(pack_art['version']), 'sha256': pack_art['sha256']},
                    'input_sha256': pack_sha,
                    'verification_scope': 'PACK_CONTENT_ONLY',
                }
            },
        })

        source_lead_payload = [
            {
                'declared_id': s.declared_id, 'paragraph': s.paragraph, 'title': s.title, 'publisher': s.publisher,
                'published_at': s.published_at, 'url': s.url, 'declared_authority': s.declared_authority,
                'declared_confidence': s.declared_confidence, 'summary': s.summary,
            }
            for s in parsed.source_leads
        ]
        quote_payload = [
            {'paragraph': q.paragraph, 'speaker': q.speaker, 'context': q.context, 'quote': q.quote, 'source_hint': q.source_hint}
            for q in parsed.quotes
        ]
        attempt_ref = tx.create_artifact('RESEARCH_ATTEMPT_LOG', {
            'query': 'Parse supplied P.T. Research Pack into safe GMK research-intake candidates.',
            'provider': 'GMK_LOCAL_RESEARCH_PACK_PARSER',
            'strategy': 'Deterministic DOCX paragraph extraction. Preserve declared labels as intake metadata; do not perform external verification.',
            'sources_inspected': [pack_source_ref],
            'result': json.dumps({'parsed_counts': parsed.counts(), 'source_leads': source_lead_payload, 'quotes': quote_payload}, ensure_ascii=False, sort_keys=True),
            'limitations': [
                'No external URLs were fetched during intake.',
                'Research Pack labels such as VERIFIED FACT are not accepted as GMK verification states.',
                'Declared source authority/confidence and quote authenticity remain unverified.',
                'No contradiction is created unless the pack explicitly supplies conflicting evidence; absence of a contradiction object is not proof of consistency.',
            ],
            'extensions': {'intake_batch_id': batch_id},
        }, origin_refs=[pack_source_ref])

        claim_refs: list[dict[str, Any]] = []
        evidence_refs: list[dict[str, Any]] = []
        for item in parsed.claims:
            ev = tx.create_object('EVIDENCE', {
                'source_ref': pack_source_ref,
                'locator': {'type': 'TEXT_RANGE', 'section': item.section, 'paragraph': item.paragraph, 'quote_anchor': item.declared_id},
                'evidence_kind': 'DOCUMENT_EXCERPT',
                'content_summary': f'Research Pack declares [{item.declared_id}]: {item.text}',
                'extensions': {
                    'intake': {
                        'batch_id': batch_id,
                        'declared_id': item.declared_id,
                        'scope': 'PACK_ASSERTION_ONLY',
                        'external_source_hint': item.source_hint,
                    }
                },
            })
            evidence_refs.append(ev)
            cl = tx.create_object('CLAIM', {
                'claim_text': item.text,
                'claim_type': item.claim_type,
                'verification_state': 'UNREVIEWED',
                'evidence_links': [{
                    'evidence_ref': ev,
                    'relation': 'CONTEXTUALIZES',
                    'scope': _evidence_scope(item),
                    'strength': 'CONTEXT_ONLY',
                }],
                'certainty': {'level': 'UNKNOWN', 'basis': ['INTAKE_ONLY']},
                'production_use': {
                    'narration_allowed': False,
                    'language_mode': 'PROHIBITED',
                    'reason': 'Imported from Research Pack only; independent Research Audit has not verified the underlying claim.',
                },
                'contradiction_refs': [],
                'extensions': {
                    'intake': {
                        'batch_id': batch_id,
                        'declared_id': item.declared_id,
                        'declared_label': 'VERIFIED FACT' if item.declared_id.startswith('FACT-') else item.declared_id.split('-', 1)[0],
                        'source_hint': item.source_hint,
                    }
                },
            })
            claim_refs.append(cl)

        gap_refs: list[dict[str, Any]] = []
        for gap in parsed.gaps:
            gap_refs.append(tx.create_object('RESEARCH_GAP', {
                'question': f'{gap.title}: {gap.question}',
                'importance': 'STANDARD',
                'state': 'OPEN',
                'blocked_targets': [],
                'blocked_gates': [],
                'research_attempt_refs': [attempt_ref],
                'extensions': {'intake': {'batch_id': batch_id, 'paragraph': gap.paragraph, 'source': 'RESEARCH_PACK_UNRESOLVED_QUESTIONS'}},
            }))

        # A system-created critical gap is the explicit safety latch that prevents
        # Research Pack ingestion from being mistaken for completed Research Audit.
        audit_gap = tx.create_object('RESEARCH_GAP', {
            'question': 'Research Pack intake candidates require independent source/evidence verification before RESEARCH_AUDIT may pass.',
            'importance': 'CRITICAL',
            'state': 'OPEN',
            'blocked_targets': claim_refs,
            'blocked_gates': ['RESEARCH_AUDIT'],
            'research_attempt_refs': [attempt_ref],
            'extensions': {'intake': {'batch_id': batch_id, 'system_guard': True}},
        })
        gap_refs.append(audit_gap)

        # Stamp replay summary on a new immutable attempt-log version after refs exist.
        attempt_ref_v2 = tx.create_artifact_version(
            attempt_ref['artifact_id'], base_version=attempt_ref['version'], payload_patch={
                'extensions': {
                    'intake_batch_id': batch_id,
                    'intake_summary': {
                        'pack_source_ref': pack_source_ref,
                        'claim_refs': claim_refs,
                        'evidence_refs': evidence_refs,
                        'gap_refs': gap_refs,
                        'source_leads': len(parsed.source_leads),
                        'quotes': len(parsed.quotes),
                        'explicit_contradictions': len(parsed.explicit_contradictions),
                    },
                }
            }, origin_refs=[pack_source_ref],
        )
        tx.commit()
        manifest = RuntimeStore(self.root, self.workspace).persist(engine)
        return ResearchIntakeResult(
            self.workspace, engine.project_state, manifest['manifest_version'], batch_id, pack_sha, pack_source_ref,
            attempt_ref_v2, tuple(claim_refs), tuple(evidence_refs), tuple(gap_refs), parsed.source_leads, parsed.quotes,
            len(parsed.explicit_contradictions), False,
        )
