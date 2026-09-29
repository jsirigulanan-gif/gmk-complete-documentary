"""Preserve research text and links; parse the observed LEMiNO Script format.

Document labels such as VERIFIED and shot durations are source claims, not validation.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .storage import Project, atomic_json


def read_source(path: Path) -> tuple[str, list[dict]]:
    if path.suffix.lower() == '.docx':
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
              'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
        with ZipFile(path) as archive:
            # Only read XML; never extract arbitrary archive paths or execute embedded objects.
            names = ['word/document.xml', 'word/_rels/document.xml.rels']
            for name in names:
                if name in archive.namelist() and archive.getinfo(name).file_size > 20_000_000:
                    raise ValueError('Research document XML is too large')
            root = ET.fromstring(archive.read(names[0]))
            rels = ET.fromstring(archive.read(names[1])) if names[1] in archive.namelist() else []
            targets = {r.get('Id'): r.get('Target') for r in rels if r.get('TargetMode') == 'External'}
            text = '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns))
                             for p in root.findall('.//w:p', ns))
            links = [{'text': ''.join(t.text or '' for t in h.findall('.//w:t', ns)),
                      'url': targets.get(h.get('{'+ns['r']+'}id'), '')} for h in root.findall('.//w:hyperlink', ns)]
    elif path.suffix.lower() == '.json':
        doc = json.loads(path.read_text(encoding='utf-8'))
        parts, links = [], []

        def walk(node):
            if isinstance(node, list):
                for child in node:
                    walk(child)
            elif isinstance(node, dict):
                run = node.get('textRun')
                if run:
                    parts.append(run.get('content', ''))
                    url = run.get('textStyle', {}).get('link', {}).get('url')
                    if url:
                        links.append({'text': run.get('content', ''), 'url': url})
                for key, child in node.items():
                    if key != 'textRun':
                        walk(child)

        walk(doc.get('tabs') or doc.get('body') or doc)
        text = ''.join(parts)
    else:
        text, links = path.read_text(encoding='utf-8-sig'), []
    links = [l for l in links if l['url'].startswith(('https://', 'http://'))]
    for url in re.findall(r'https?://[^\s<>]+', text):
        if not any(l['url'] == url for l in links):
            links.append({'text': url, 'url': url})
    if not text.strip():
        raise ValueError('No readable research text in the selected document')
    return text, links


def parse_script(text: str, links: list[dict]) -> dict:
    headings = list(re.finditer(r'^\s*(SHOT-\d+)\s*\|\s*([^\r\n]+)', text, re.M))
    scenes, seen = [], set()
    for i, heading in enumerate(headings):
        key = heading[1]
        if key in seen:
            raise ValueError(f'Duplicate scene ID: {key}')
        seen.add(key)
        body = text[heading.end():headings[i+1].start() if i+1 < len(headings) else len(text)]
        body = re.split(r'\n\s*(?:ACT [IVX]+:|Master Media Asset Library)', body)[0].strip()
        cues = {}
        for label in ('VISUAL', 'AUDIO'):
            match = re.search(r'^\s*'+label+r':\s*(.+)$', body, re.M)
            cues[label.lower()] = match[1].strip() if match else ''
        narration = [line.strip() for line in body.splitlines()
                     if line.strip() and not re.match(r'\s*(?:VISUAL:|AUDIO:|_+$)', line)]
        scenes.append({'id': key, 'heading': heading[2], 'source_text': body, 'cues': cues,
                       'narration_th': '\n'.join(l for l in narration if re.search('[\u0e00-\u0e7f]', l)),
                       'narration_en': '\n'.join(l for l in narration if not re.search('[\u0e00-\u0e7f]', l)),
                       'timing_status': 'PLANNED_ONLY', 'footage_status': 'NOT_MATCHED'})
    return {'title': text.strip().splitlines()[0], 'source_text': text, 'source_links': links,
            'scenes': scenes, 'fact_check_status': 'NOT_CHECKED',
            'warnings': ['Source VERIFIED labels are not independent fact checks.',
                         'Planned timestamps must be replaced with measured narration timing.',
                         'Visual/audio descriptions are requests, not available media.']}


def import_research(project: Project, source: Path) -> dict:
    text, links = read_source(source)
    parsed = parse_script(text, links)
    source_asset = project.add_file(source, 'research', source_url=project.read()['source_url'])
    from .production import ProductionProject
    production = ProductionProject(project)
    production.initialize()
    production.register_research(source_asset['path'])
    # Stored source is immutable; this human-readable working derivative can be edited.
    working = project.root / 'script.json'
    atomic_json(working, parsed)
    project.add_file(working, 'research', source_url=project.read()['source_url'])
    return parsed
