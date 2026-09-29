from pathlib import Path
import json
import shutil
import zipfile

from gmk_research import ResearchIntakeRuntime, ResearchAuditRuntime
from gmk_research.audit import _derive_claim_state, ResearchAuditError
from gmk_runtime.cold_start import ColdStartLoader
from gmk_workspace import WorkspaceBootstrapper

ROOT=Path(__file__).resolve().parents[2]


def make_pack(path:Path, *, claims=2):
    paras=[
        'RESEARCH PACK: TEST AUDIT',
        '02_Verified_Facts',
        '- `[FACT-001]` **[VERIFIED FACT]** Claim one. (Source: Pack Source)',
    ]
    if claims > 1:
        paras.append('- `[FACT-002]` **[VERIFIED FACT]** Claim two. (Source: Pack Source)')
    paras += [
        '07_Source_Library',
        '- `[SRC-001]` **Pack Source** | Pack Publisher | 1 January 2020 | https://example.com/pack | Secondary | Medium | Pack lead',
        '11_Unresolved_Questions',
        '1. **Unknown detail:** What remains unknown?',
    ]
    ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    def esc(x): return x.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    body=''.join(f'<w:p><w:r><w:t xml:space="preserve">{esc(p)}</w:t></w:r></w:p>' for p in paras)
    xml=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('word/document.xml',xml)


def bootstrap(tmp_path:Path, *, claims=2):
    pack=tmp_path/'pack.docx'; make_pack(pack,claims=claims)
    ws=tmp_path/'ws'
    WorkspaceBootstrapper(ROOT).init(ws,title='Audit Test',research_pack=pack)
    intake=ResearchIntakeRuntime(ROOT,ws).run()
    assert intake.project_state=='RESEARCH_INTAKE'
    return ws


def source(key, group):
    return {
        'key':key,'source_type':'WEB_PAGE','title':key,'publisher':'Example',
        'url':f'https://example.com/{key.lower()}','published_at':'2020-01-01',
        'authority_class':'REPUTABLE_SECONDARY','independence_group':group,
        'independence_relationship':'ORIGINAL','language':'en',
    }


def evidence(key, skey):
    return {'key':key,'source_key':skey,'evidence_kind':'DOCUMENT_EXCERPT','content_summary':key,'locator':{'type':'FULL_SOURCE'}}


def batch(batch_id='TEST_AUDIT', *, claim_ids=('CLM_000001','CLM_000002'), same_group=False):
    grp2='SRCGRP_G1' if same_group else 'SRCGRP_G2'
    sources=[source('S1','SRCGRP_G1'),source('S2',grp2),source('S3','SRCGRP_G3')]
    evs=[evidence('E1','S1'),evidence('E2','S2'),evidence('E3','S3')]
    decisions=[]
    if 'CLM_000001' in claim_ids:
        decisions.append({'claim_id':'CLM_000001','evidence_links':[{'evidence_key':'E1','relation':'SUPPORTS','strength':'STRONG','scope':['EVENT']},{'evidence_key':'E2','relation':'SUPPORTS','strength':'STRONG','scope':['EVENT']}]})
    if 'CLM_000002' in claim_ids:
        decisions.append({'claim_id':'CLM_000002','force_prohibit':True,'prohibit_reason':'No support established.','evidence_links':[{'evidence_key':'E3','relation':'QUALIFIES','strength':'WEAK','scope':['EVENT']}]})
    return {'batch_id':batch_id,'provider':'TEST','query':'test audit','strategy':'test','sources':sources,'evidence':evs,'claims':decisions,'new_claims':[],'gaps':[],'limitations':[]}


def test_independence_groups_control_corroboration():
    sources_same={('SRC1',1):{'id':'SRC1','authority_class':'REPUTABLE_SECONDARY','independence':{'group_id':'G1'}},('SRC2',1):{'id':'SRC2','authority_class':'REPUTABLE_SECONDARY','independence':{'group_id':'G1'}}}
    evidence_map={('E1',1):{'id':'E1','source_ref':{'id':'SRC1','version':1}},('E2',1):{'id':'E2','source_ref':{'id':'SRC2','version':1}}}
    links=[{'evidence_ref':{'id':'E1','version':1},'relation':'SUPPORTS','strength':'STRONG'},{'evidence_ref':{'id':'E2','version':1},'relation':'SUPPORTS','strength':'STRONG'}]
    state,_,_= _derive_claim_state('FACTUAL_ASSERTION',links,evidence_map,sources_same)
    assert state=='SOURCE_VERIFIED'
    sources_ind=dict(sources_same);sources_ind[('SRC2',1)]={'id':'SRC2','authority_class':'REPUTABLE_SECONDARY','independence':{'group_id':'G2'}}
    state,_,_= _derive_claim_state('FACTUAL_ASSERTION',links,evidence_map,sources_ind)
    assert state=='CORROBORATED'


def test_no_support_is_insufficient_and_prohibited():
    sources={('SRC1',1):{'id':'SRC1','authority_class':'REPUTABLE_SECONDARY','independence':{'group_id':'G1'}}}
    ev={('E1',1):{'id':'E1','source_ref':{'id':'SRC1','version':1}}}
    links=[{'evidence_ref':{'id':'E1','version':1},'relation':'QUALIFIES','strength':'WEAK'}]
    state,_,prod=_derive_claim_state('FACTUAL_ASSERTION',links,ev,sources)
    assert state=='INSUFFICIENT_EVIDENCE'
    assert prod['narration_allowed'] is False and prod['language_mode']=='PROHIBITED'


def test_partial_audit_keeps_intake_guard_and_state(tmp_path):
    ws=bootstrap(tmp_path)
    result=ResearchAuditRuntime(ROOT,ws).run(batch('PARTIAL',claim_ids=('CLM_000001',)),transition_if_ready=True)
    assert result.project_state=='RESEARCH_INTAKE'
    loaded=ColdStartLoader(ROOT,ws).load(); st=loaded.engine.snapshot()
    guard=[]
    for reg in st.registries.values():
        for oid,entry in reg.entries.items():
            if entry.object_type=='RESEARCH_GAP' and entry.active_version is not None:
                g=st.objects[(oid,int(entry.active_version))]
                if ((g.get('extensions') or {}).get('intake') or {}).get('system_guard'): guard.append(g)
    assert len(guard)==1 and guard[0]['state']=='OPEN'
    assert loaded.engine.evaluate_gate('RESEARCH_AUDIT').result=='FAIL'
    # The active guard's decision version is unchanged, but its LIVE derived stale
    # envelope changed after CLM_000001 promotion. Persistence stores that exact
    # record content-addressed without overwriting the immutable v1 decision file.
    gap_reg=next(reg for reg in st.registries.values() if 'GAP_000002' in reg.entries)
    loc=gap_reg.entries['GAP_000002'].versions[1]
    exact=ws/'objects'/'GAP_000002'/'records'/'v1'/f'{loc.record_sha256}.json'
    assert exact.is_file()
    assert loaded.dependency_summary['changed_objects']==0


def test_full_audit_resolves_guard_transitions_and_cold_start_is_stable(tmp_path):
    ws=bootstrap(tmp_path)
    result=ResearchAuditRuntime(ROOT,ws).run(batch('FULL'))
    assert result.project_state=='RESEARCH_AUDITED' and result.gate_result=='PASS'
    assert result.disposition_counts=={'CORROBORATED':1,'INSUFFICIENT_EVIDENCE':1}
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.engine.project_state=='RESEARCH_AUDITED'
    assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
    st=loaded.engine.snapshot()
    c1=st.objects[('CLM_000001',2)]; c2=st.objects[('CLM_000002',2)]
    assert c1['verification_state']=='CORROBORATED' and c1['stale']['is_stale'] is False
    assert c2['verification_state']=='INSUFFICIENT_EVIDENCE' and c2['production_use']['language_mode']=='PROHIBITED'
    guard=st.objects[('GAP_000002',2)] if ('GAP_000002',2) in st.objects else None
    assert guard is not None and guard['state']=='RESOLVED' and guard['stale']['is_stale'] is False


def test_audit_replay_is_idempotent(tmp_path):
    ws=bootstrap(tmp_path)
    runtime=ResearchAuditRuntime(ROOT,ws); first=runtime.run(batch('REPLAY')); second=runtime.run(batch('REPLAY'))
    assert first.idempotent_replay is False and second.idempotent_replay is True
    assert first.claim_refs==second.claim_refs and first.source_refs==second.source_refs and first.evidence_refs==second.evidence_refs
    loaded=ColdStartLoader(ROOT,ws).load(); st=loaded.engine.snapshot()
    assert len([o for o in st.objects.values() if o.get('object_type')=='SOURCE' and ((o.get('extensions') or {}).get('research_audit') or {}).get('batch_id')=='REPLAY'])==3


def test_real_pt_audit_workspace_cold_starts_without_registry_drift(tmp_path):
    baseline=ROOT/'..'/'gmk-schema-v1-build-011'/'pilot'/'PT_WORKSPACE'
    # The build test remains self-contained when the predecessor directory is unavailable.
    if not baseline.exists():
        return
    ws=tmp_path/'pt';shutil.copytree(baseline,ws)
    data=json.loads((ROOT/'pilot'/'PT_RESEARCH_AUDIT_INPUT.json').read_text(encoding='utf-8'))
    result=ResearchAuditRuntime(ROOT,ws).run(data)
    assert result.project_state=='RESEARCH_AUDITED' and result.gate_result=='PASS'
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}


def test_batch_id_collision_with_changed_content_fails_closed(tmp_path):
    ws=bootstrap(tmp_path)
    runtime=ResearchAuditRuntime(ROOT,ws); original=batch('COLLISION')
    runtime.run(original)
    changed=json.loads(json.dumps(original));changed['limitations']=['changed verification input']
    try:
        runtime.run(changed)
    except ResearchAuditError as exc:
        assert 'RESEARCH_AUDIT_BATCH_ID_COLLISION' in str(exc)
    else:
        raise AssertionError('changed audit content reused an existing batch id')
