"""General document intake and a local review view over canonical research records."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re

from gmk_research.intake import (
    ParsedGap, ParsedItem, ParsedSourceLead, ResearchIntakeRuntime,
    ResearchPackParseResult,
)
from .intake import read_source
from .production import ProductionProject, RUNTIME_ROOT
from .storage import StorageError, atomic_json, digest, relative_path


class DocumentaryParser:
    """Extract review units, not verified or necessarily atomic factual claims.

    In bilingual shots Thai is the selected narration; English is an alternative,
    not independent corroboration. Unstructured briefs remain source material.
    """
    def parse(self, path: Path) -> ResearchPackParseResult:
        text, links = read_source(path)
        lines = text.splitlines()
        shots, explicit, gaps = [], [], []
        current = None
        for number, raw in enumerate(lines, 1):
            line = raw.strip()
            shot = re.match(r'^(SHOT-\d+)\s*\|', line)
            if shot:
                if any(s[0] == shot[1] for s in shots):
                    raise ValueError('Duplicate scene ID: ' + shot[1])
                current = (shot[1], [])
                shots.append(current)
                continue
            if re.match(r'^(?:ACT\s+[IVX\d]+\s*:|Master Media Asset Library|(?:Sources|References|แหล่งอ้างอิง)\s*:?)', line, re.I):
                current = None
            claim = re.match(r'^(?:[-*]\s*)?(?:CLAIM|FACT|ข้อกล่าวอ้าง|ข้อเท็จจริง)\s*:\s*(.+)', line, re.I)
            question = re.match(r'^(?:[-*]\s*)?(?:QUESTION|GAP|คำถาม|ประเด็นที่ต้องตรวจสอบ)\s*:\s*(.+)', line, re.I)
            if claim:
                explicit.append((number, raw, claim[1], current[0] if current else 'EXPLICIT_CLAIMS'))
            elif question:
                gaps.append(ParsedGap(number, 'Imported question', question[1]))
            elif current and line and not re.match(
                r'^(?:VISUAL|AUDIO|MUSIC|SFX|SOURCE|DURATION|หมายเหตุ)\s*:|^[_=\-]{3,}$|^https?://', line, re.I
            ):
                current[1].append((number, raw))
        claims = [ParsedItem(f'CLAIM-L{n:05}', n, section, raw, body,
                             claim_type='REPORTED_ASSERTION') for n, raw, body, section in explicit]
        for shot_id, paragraphs in shots:
            thai = [(n, raw) for n, raw in paragraphs if re.search('[\u0e00-\u0e7f]', raw)]
            for n, raw in thai or paragraphs:
                claims.append(ParsedItem(f'{shot_id}-L{n:05}', n, shot_id, raw, raw.strip(),
                                         claim_type='REPORTED_ASSERTION'))
        claims.sort(key=lambda c: c.paragraph)
        if not claims:
            gaps.append(ParsedGap(1, 'Claim extraction required',
                'No supported narration or explicit CLAIM:/FACT: entries found. Review the preserved brief and identify factual assertions before scripting.'))
        leads, seen = [], set()
        for link in links:
            url = link['url']
            if url in seen:
                continue
            seen.add(url)
            leads.append(ParsedSourceLead(f'LINK-{len(leads)+1:03}', 0, link['text'].strip() or url,
                '', '', url, 'UNKNOWN', 'UNKNOWN',
                'Unfetched document link; no claim-to-source association has been established.'))
        title = next(line.strip() for line in lines if line.strip())
        return ResearchPackParseResult(title, tuple(lines), tuple(claims),
            tuple(leads), tuple(gaps), (), ())


class DocumentaryIntakeRuntime(ResearchIntakeRuntime):
    batch_prefix = 'DOCUMENT_INTAKE_V1_'
    source_relationship = 'UNKNOWN'
    query = 'Extract general documentary narration and explicit assertions for research review.'
    strategy = 'Local DOCX, Google Docs JSON or text extraction. Selected-language narration paragraphs are review units; source links remain unfetched leads.'

    def __init__(self, workspace: Path, artifact_id: str):
        super().__init__(RUNTIME_ROOT, workspace)
        self.parser = DocumentaryParser()
        self.artifact_id = artifact_id
        self.imported_source_group = 'SRCGRP_IMPORTED_RESEARCH'

    def _research_pack_artifact(self, state):
        # Retain the first imported pack's group across tool upgrades as well.
        sources = sorted((o for o in state.objects.values() if o.get('object_type') == 'SOURCE'
                          and o.get('extensions', {}).get('intake', {}).get('batch_id', '').startswith('DOCUMENT_INTAKE_')),
                         key=lambda o: (o['id'], o['version']))
        if sources:
            self.imported_source_group = sources[0]['independence']['group_id']
        hits = [a for a in state.artifacts.values() if a.get('artifact_type') == 'RESEARCH_PACK'
                and a['artifact_id'] == self.artifact_id]
        if not hits:
            raise StorageError('Registered research pack not found')
        return max(hits, key=lambda a: int(a['version']))

    def evidence_scope(self, item):
        # Context only: do not infer technical/causal meaning from keywords.
        return ['INTERPRETATION']

    def declared_label(self, item):
        return 'IMPORTED_REVIEW_UNIT'

    def source_group(self, batch_id):
        # Different uploaded drafts do not establish independent corroboration.
        return self.imported_source_group


def analyze_research(project) -> dict:
    """Repeat safely for every registered pack, holding the same project writer lock."""
    production = ProductionProject(project)
    results = []
    with project._lock():
        loaded = production._load()
        packs = {}
        for artifact in loaded.engine.snapshot().artifacts.values():
            if artifact.get('artifact_type') == 'RESEARCH_PACK':
                previous = packs.get(artifact['artifact_id'])
                if previous is None or artifact['version'] > previous['version']:
                    packs[artifact['artifact_id']] = artifact
        if not packs:
            raise StorageError('Import a research document first')
        # Validate every input before creating any records, including on replay.
        for pack in packs.values():
            notes = dict(n.split('=', 1) for n in pack.get('notes', []) if '=' in n)
            path = production.workspace / relative_path(notes.get('input_path', ''))
            if (path.is_symlink() or not path.resolve().is_relative_to(production.workspace)
                    or not path.is_file() or digest(path)['sha256'] != notes.get('input_sha256')):
                raise StorageError('Research input checksum mismatch; restore the registered source')
        for pack in packs.values():
            result = DocumentaryIntakeRuntime(production.workspace, pack['artifact_id']).run()
            results.append(result.to_dict())
        data = project.read()
        data['storage_status'] = 'PENDING_UPLOAD'
        atomic_json(project.manifest, data)
    report = research_review(project)
    return {'intakes': results, 'review_path': report['review_path'],
            'claims_for_review': len(report['claims']), 'source_leads': len(report['source_leads']),
            'research_audit_status': 'NOT_PASSED'}


def research_review(project) -> dict:
    """Rebuild a local read-only report from exact core versions, with no web requests."""
    with project._lock():
        return _research_review(project)


def _research_review(project) -> dict:
    loaded = ProductionProject(project)._load()
    state = loaded.engine.snapshot()
    heads = {}
    for obj in state.objects.values():
        if obj['id'] not in heads or obj['version'] > heads[obj['id']]['version']:
            heads[obj['id']] = obj
    claims = []
    for obj in heads.values():
        intake = obj.get('extensions', {}).get('intake', {})
        if obj.get('object_type') != 'CLAIM' or not intake.get('batch_id', '').startswith('DOCUMENT_INTAKE_'):
            continue
        evidence = [state.objects[(link['evidence_ref']['id'], link['evidence_ref']['version'])]
                    for link in obj['evidence_links']]
        claims.append({'id': obj['id'], 'version': obj['version'], 'text': obj['claim_text'],
                       'verification_state': obj['verification_state'],
                       'narration_allowed': obj['production_use']['narration_allowed'],
                       'evidence': [{'id': ev['id'], 'version': ev['version'], 'source_ref': ev['source_ref'],
                                     'locator': ev['locator'], 'summary': ev['content_summary']} for ev in evidence]})
    leads = {}
    for artifact in state.artifacts.values():
        if artifact.get('artifact_type') == 'RESEARCH_ATTEMPT_LOG' and artifact.get('extensions', {}).get('intake_batch_id', '').startswith('DOCUMENT_INTAKE_'):
            for lead in json.loads(artifact['result']).get('source_leads', []):
                leads[lead['url']] = lead
    gaps = [{'id': o['id'], 'question': o['question'], 'state': o['state']} for o in heads.values()
            if o.get('object_type') == 'RESEARCH_GAP'
            and o.get('extensions', {}).get('intake', {}).get('batch_id', '').startswith('DOCUMENT_INTAKE_')]
    report = {'manifest_sha256': loaded.manifest_sha256, 'production_state': loaded.engine.project_state,
              'claims': claims, 'source_leads': list(leads.values()),
              'research_gaps': gaps,
              'limitations': ['Imported paragraphs may contain multiple assertions or narrative devices; editorial splitting and source verification remain required.',
                             'Document links have not been fetched or established as evidence for individual claims.']}
    rows = []
    for claim in claims:
        locations = '; '.join(f"{e['locator'].get('section', '')} · บรรทัด {e['locator'].get('paragraph', '?')} · {e['source_ref']['id']}" for e in claim['evidence'])
        rows.append('<tr><td>'+escape(claim['id'])+'</td><td>'+escape(claim['text'])+'</td><td>'+escape(locations)+'</td><td>'+escape(claim['verification_state'])+'</td></tr>')
    source_rows = ''.join('<li>'+escape(lead['title'])+'<br><a rel="noreferrer noopener" href="'+escape(url, quote=True)+'">'+escape(url)+'</a> — ยังไม่ได้ตรวจ</li>'
                          for url, lead in leads.items() if url.startswith(('https://', 'http://')))
    html = '''<!doctype html><html lang="th"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>GMK · ตรวจรีเสิร์ช</title><style>body{font:17px sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;background:#f7f7fa;color:#19202b}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border:1px solid #d5d8df;text-align:left;vertical-align:top}td:nth-child(2){white-space:pre-wrap}li{margin:16px 0;overflow-wrap:anywhere}</style>
<h1>ตรวจรีเสิร์ช</h1><p>รายการนี้เก็บข้อความที่นำเข้าเพื่อให้ตรวจข้อกล่าวอ้าง บางย่อหน้าอาจมีหลายประเด็นหรือเป็นคำถามเชิงเล่าเรื่อง จึงยังต้องแยกและตรวจหลักฐานก่อนใช้ในบทฉบับจริง</p>
<p>ลิงก์ท้ายเอกสารยังไม่ได้เปิดตรวจ และยังไม่ได้จับคู่เป็นหลักฐานของแต่ละข้อความ</p>'''
    html += '<p>โปรเจกต์: '+escape(project.read()['title'])+' · สถานะ: '+escape(loaded.engine.project_state)+'</p>'
    html += '<table><thead><tr><th>รายการ</th><th>ข้อความรอตรวจ</th><th>ตำแหน่งต้นฉบับที่แยกเป็นข้อความ</th><th>สถานะ</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><h2>แหล่งอ้างอิงที่ต้องตรวจ</h2><ul>'+source_rows+'</ul>'
    html += '<h2>คำถามและงานวิจัยที่ยังค้าง</h2><ul>'+''.join('<li>'+escape(g['question'])+' · '+escape(g['state'])+'</li>' for g in gaps)+'</ul></html>'
    directory = project.root/'review'
    directory.mkdir(exist_ok=True)
    atomic_json(directory/'research.json', report)
    temporary = directory/'research.html.tmp'
    temporary.write_text(html, encoding='utf-8')
    temporary.replace(directory/'research.html')
    return {**report, 'review_path': str(directory/'research.html')}
