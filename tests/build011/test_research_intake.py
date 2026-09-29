from pathlib import Path
import json, subprocess, sys, zipfile

from gmk_research import ResearchPackParser
from gmk_runtime.cold_start import ColdStartLoader

ROOT=Path(__file__).resolve().parents[2]


def make_pack(path:Path):
    paras=[
        'RESEARCH PACK: THE GHOST OF P.T. & THE ERASURE OF HIDEO KOJIMA',
        '02_Verified_Facts',
        '- `[FACT-001]` **[VERIFIED FACT]** P.T. launched at Gamescom. (Source: Example Source)',
        '05_Community_Theories_and_Rumors',
        '- `[THEORY-001]` **[COMMUNITY THEORY]** A symbolic theory.',
        '07_Source_Library',
        '- `[SRC-001]` **Example Source** | Example Publisher | 12 August 2014 | https://example.com/source | Primary | High | Example source lead',
        '10_Quotes',
        '1. **Speaker (Event):**',
        '*"Example quote."*',
        '*(Direct Quote - [SRC-001])*',
        '11_Unresolved_Questions',
        '1. **Unknown detail:** What remains unknown?',
    ]
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body=''.join(f'<w:p><w:r><w:t xml:space="preserve">{p.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</w:t></w:r></w:p>' for p in paras)
    xml=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('word/document.xml',xml)


def run(*args,check=True):
    return subprocess.run([sys.executable,'-m','gmk_cli',*map(str,args)],cwd=ROOT,text=True,capture_output=True,check=check)


def test_parser_preserves_pack_labels_as_intake_candidates(tmp_path):
    p=tmp_path/'pack.docx';make_pack(p);r=ResearchPackParser().parse(p)
    assert r.counts()=={'claims':2,'source_leads':1,'unresolved_questions':1,'quotes':1,'explicit_contradictions':0}
    assert r.claims[0].declared_id=='FACT-001' and r.claims[0].claim_type=='FACTUAL_ASSERTION'
    assert r.claims[1].claim_type=='COMMUNITY_THEORY'


def test_pilot_bootstrap_enters_research_intake_but_cannot_pass_audit(tmp_path):
    p=tmp_path/'The Ghost of P.T. Research Pack.docx';make_pack(p);ws=tmp_path/'ws'
    out=json.loads(run('pilot-bootstrap','--workspace',ws,'--research-pack',p,'--json').stdout)
    assert out['intake']['project_state']=='RESEARCH_INTAKE'
    assert out['intake']['research_audit_status']=='NOT_PASSED'
    loaded=ColdStartLoader(ROOT,ws).load();state=loaded.engine.snapshot()
    claims=[o for o in state.objects.values() if o.get('object_type')=='CLAIM']
    assert len(claims)==2
    assert all(c['verification_state']=='UNREVIEWED' for c in claims)
    assert all(c['production_use']['narration_allowed'] is False and c['production_use']['language_mode']=='PROHIBITED' for c in claims)
    nxt=loaded.engine.next_legal_action(actor_type='AI').to_dict()
    assert nxt['action']=='RESOLVE_BLOCKER' and nxt['target_state']=='RESEARCH_AUDITED'
    gaps=[o for o in state.objects.values() if o.get('object_type')=='RESEARCH_GAP']
    guard=[g for g in gaps if (g.get('extensions') or {}).get('intake',{}).get('system_guard')]
    assert len(guard)==1 and guard[0]['importance']=='CRITICAL' and 'RESEARCH_AUDIT' in guard[0]['blocked_gates']


def test_research_intake_is_idempotent(tmp_path):
    p=tmp_path/'The Ghost of P.T. Research Pack.docx';make_pack(p);ws=tmp_path/'ws'
    first=json.loads(run('pilot-bootstrap','--workspace',ws,'--research-pack',p,'--json').stdout)['intake']
    second=json.loads(run('research-intake','--workspace',ws,'--json').stdout)
    assert first['batch_id']==second['batch_id']
    assert second['idempotent_replay'] is True
    loaded=ColdStartLoader(ROOT,ws).load();state=loaded.engine.snapshot()
    assert len([o for o in state.objects.values() if o.get('object_type')=='CLAIM'])==2
