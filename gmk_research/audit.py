from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state.errors import StateEngineError


class ResearchAuditError(RuntimeError):
    pass


def _sha256_json(data: Any) -> str:
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _active_object(state, object_id: str) -> dict[str,Any]:
    for reg in state.registries.values():
        entry=reg.entries.get(object_id)
        if entry and entry.active_version is not None:
            return state.objects[(object_id,int(entry.active_version))]
    raise ResearchAuditError(f'ACTIVE_OBJECT_NOT_FOUND: {object_id}')


def _head_object(state, object_id: str) -> dict[str,Any]:
    for reg in state.registries.values():
        entry=reg.entries.get(object_id)
        if entry:
            return state.objects[(object_id,int(entry.head_version))]
    raise ResearchAuditError(f'OBJECT_NOT_FOUND: {object_id}')


def _source_group(source: dict[str,Any]) -> str:
    return str((source.get('independence') or {}).get('group_id') or source.get('id'))


def _source_authority(source: dict[str,Any]) -> str:
    return str(source.get('authority_class') or 'UNKNOWN')


def _derive_claim_state(claim_type: str, links: list[dict[str,Any]], evidence_by_ref: dict[tuple[str,int],dict[str,Any]], source_by_ref: dict[tuple[str,int],dict[str,Any]]) -> tuple[str,dict[str,Any],dict[str,Any]]:
    support=[]; contradict=[]
    for link in links:
        ref=link.get('evidence_ref') or {}; ev=evidence_by_ref.get((ref.get('id'),int(ref.get('version',0))))
        if not ev: continue
        sref=ev.get('source_ref') or {}; src=source_by_ref.get((sref.get('id'),int(sref.get('version',0))))
        if not src: continue
        row=(link,ev,src)
        if link.get('relation')=='SUPPORTS': support.append(row)
        elif link.get('relation')=='CONTRADICTS': contradict.append(row)

    groups={_source_group(src) for _,_,src in support}
    strong=[row for row in support if row[0].get('strength') in {'DIRECT','STRONG','CORROBORATIVE'}]
    strong_groups={_source_group(src) for _,_,src in strong}
    primaryish=any(_source_authority(src) in {'PRIMARY','OFFICIAL','DIRECT_WITNESS','TECHNICAL_RESEARCH'} for _,_,src in strong)

    if support and contradict:
        verification='CONTESTED'
    elif len(strong_groups)>=2:
        verification='CORROBORATED'
    elif strong:
        verification='SOURCE_VERIFIED'
    elif support:
        verification='SOURCE_FOUND'
    else:
        verification='INSUFFICIENT_EVIDENCE'

    if verification=='CORROBORATED':
        certainty={'level':'HIGH','basis':['TWO_INDEPENDENT_SOURCE_GROUPS','STRONG_EVIDENCE']}
    elif verification=='SOURCE_VERIFIED':
        certainty={'level':'HIGH' if primaryish else 'MEDIUM','basis':['ONE_VERIFIED_SOURCE_GROUP'] + (['PRIMARY_OR_OFFICIAL_SOURCE'] if primaryish else [])}
    elif verification=='SOURCE_FOUND':
        certainty={'level':'LOW','basis':['SOURCE_FOUND_WEAK_SUPPORT']}
    elif verification=='CONTESTED':
        certainty={'level':'LOW','basis':['CONFLICTING_EVIDENCE']}
    else:
        certainty={'level':'LOW','basis':['INSUFFICIENT_SUPPORT']}

    if verification in {'INSUFFICIENT_EVIDENCE','CONTESTED','SOURCE_FOUND'}:
        production={'narration_allowed':False,'language_mode':'PROHIBITED','reason':'Research Audit did not establish sufficient support for production narration.'}
    elif claim_type=='COMMUNITY_THEORY':
        production={'narration_allowed':True,'language_mode':'THEORY','reason':'Audit verifies the existence of the community theory, not the theory as fact.'}
    elif claim_type in {'RUMOR','INTERPRETATION'}:
        production={'narration_allowed':False,'language_mode':'PROHIBITED','reason':'Rumor/interpretation remains non-production by conservative v1 research policy unless explicitly re-scoped into a separately supported factual statement.'}
    elif claim_type in {'REPORTED_ASSERTION','PRIMARY_STATEMENT','TECHNICAL_FINDING'}:
        production={'narration_allowed':True,'language_mode':'ATTRIBUTED','reason':'Use attribution because the finding/statement is tied to an identified source or researcher.'}
    elif verification=='SOURCE_VERIFIED' and not primaryish:
        production={'narration_allowed':True,'language_mode':'QUALIFIED','reason':'Single verified non-primary source group; narrate with qualification.'}
    else:
        production={'narration_allowed':True,'language_mode':'DIRECT','reason':'Research Audit established sufficient factual support for direct narration.'}
    return verification,certainty,production


@dataclass(frozen=True)
class ResearchAuditResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    claim_refs: tuple[dict[str,Any],...]
    source_refs: tuple[dict[str,Any],...]
    evidence_refs: tuple[dict[str,Any],...]
    created_claim_refs: tuple[dict[str,Any],...]
    gap_refs: tuple[dict[str,Any],...]
    attempt_ref: dict[str,Any]
    gate_result: str
    disposition_counts: dict[str,int]
    idempotent_replay: bool=False

    def to_dict(self)->dict[str,Any]:
        return {
            'workspace':str(self.workspace),'batch_id':self.batch_id,'project_state':self.project_state,
            'manifest_version':self.manifest_version,'claim_refs':list(self.claim_refs),'source_refs':list(self.source_refs),
            'evidence_refs':list(self.evidence_refs),'created_claim_refs':list(self.created_claim_refs),'gap_refs':list(self.gap_refs),
            'attempt_ref':self.attempt_ref,'gate_result':self.gate_result,'disposition_counts':dict(self.disposition_counts),
            'idempotent_replay':self.idempotent_replay,
        }


class ResearchAuditRuntime:
    """Apply an externally researched verification batch to the frozen GMK v1 research graph.

    This runtime never treats the batch's requested conclusion as authority. It creates exact
    SOURCE/EVIDENCE records and derives Claim verification from actual evidence relations,
    evidence strength and independent-source groups. The batch may narrow wording/type, but
    cannot force CORROBORATED merely by naming that state.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root=Path(schema_root); self.workspace=Path(workspace)

    def _replay(self,state,batch_id:str,batch_sha256:str) -> ResearchAuditResult|None:
        attempts=[]
        for art in state.artifacts.values():
            if art.get('artifact_type')!='RESEARCH_ATTEMPT_LOG':continue
            audit=(art.get('extensions') or {}).get('research_audit') or {}
            if audit.get('batch_id')==batch_id:attempts.append(art)
        if not attempts:return None
        exact=[a for a in attempts if ((a.get('extensions') or {}).get('research_audit') or {}).get('batch_sha256')==batch_sha256]
        if not exact:
            raise ResearchAuditError(f'RESEARCH_AUDIT_BATCH_ID_COLLISION: {batch_id} already exists with different verification content.')
        art=max(exact,key=lambda x:int(x['version']))
        summary=((art.get('extensions') or {}).get('research_audit') or {}).get('summary') or {}
        gate=self._gate_result_from_state(state)
        return ResearchAuditResult(
            self.workspace,batch_id,state.project_state,state.manifest_version,
            tuple(summary.get('claim_refs') or ()),tuple(summary.get('source_refs') or ()),tuple(summary.get('evidence_refs') or ()),
            tuple(summary.get('created_claim_refs') or ()),tuple(summary.get('gap_refs') or ()),
            {'artifact_id':art['artifact_id'],'artifact_type':art['artifact_type'],'version':art['version'],'sha256':art['sha256']},
            gate,dict(summary.get('disposition_counts') or {}),True,
        )

    @staticmethod
    def _gate_result_from_state(state)->str:
        # A persisted historical gate is not enough; this is filled after runtime evaluation in run().
        return 'UNKNOWN'

    def run(self, verification_batch: dict[str,Any], *, transition_if_ready: bool=True,
            reopen_early_stage: bool=False, reopen_editor_recon: bool=False) -> ResearchAuditResult:
        batch=deepcopy(verification_batch)
        batch_id=str(batch.get('batch_id') or ('AUDIT_'+_sha256_json(batch)[:16].upper()))
        batch_sha256=_sha256_json(batch)
        loaded=ColdStartLoader(self.root,self.workspace).load(); engine=loaded.engine; state=engine.snapshot()
        replay=self._replay(state,batch_id,batch_sha256)
        if replay:
            gate=engine.gates.evaluate_gate(state,'RESEARCH_AUDIT',engine.now()).result
            return ResearchAuditResult(replay.workspace,replay.batch_id,engine.project_state,engine.manifest_version,replay.claim_refs,replay.source_refs,replay.evidence_refs,replay.created_claim_refs,replay.gap_refs,replay.attempt_ref,gate,replay.disposition_counts,True)
        if reopen_early_stage and (engine.project_state in {'RESEARCH_AUDITED','ROUGH_NARRATIVE_READY','VISUAL_REQUIREMENTS_READY'}
                                   or (reopen_editor_recon and engine.project_state == 'ASSET_RECON')):
            # Explicit operator re-review: keep history and let claim promotion
            # invalidate dependent narrative objects. Never reopen locked production.
            reopening=engine.begin()
            reopening.reenter_stage('RESEARCH_INTAKE',actor_type='HUMAN')
            reopening.commit()
        if engine.project_state!='RESEARCH_INTAKE':
            raise ResearchAuditError(f'RESEARCH_AUDIT_STATE_INVALID: expected RESEARCH_INTAKE, found {engine.project_state}')

        tx=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
        source_refs=[]; source_ref_by_key={}; source_by_ref={}
        for spec in batch.get('sources') or []:
            key=str(spec['key'])
            payload={
                'source_type':spec.get('source_type','WEB_PAGE'),'title':spec['title'],'publisher':spec.get('publisher',''),
                'author':spec.get('author',''),'platform':spec.get('platform','Web'),'url':spec.get('url'),
                'published_at':spec.get('published_at',''),'accessed_at':engine.now(),'authority_class':spec.get('authority_class','REPUTABLE_SECONDARY'),
                'independence':{'group_id':spec['independence_group'],'relationship':spec.get('independence_relationship','ORIGINAL')},
                'language':spec.get('language','en'),'availability':{'state':spec.get('availability','AVAILABLE')},
                'notes':spec.get('notes',''),
                'extensions':{'research_audit':{'batch_id':batch_id,'source_key':key,'verification_role':spec.get('verification_role','EXTERNAL_VERIFICATION')}},
            }
            if not payload.get('url'):payload.pop('url',None)
            ref=tx.create_object('SOURCE',payload);source_refs.append(ref);source_ref_by_key[key]=ref
            source_by_ref[(ref['id'],ref['version'])]=tx.staged.objects[(ref['id'],ref['version'])]

        evidence_refs=[]; ev_ref_by_key={}; evidence_by_ref={}
        for spec in batch.get('evidence') or []:
            key=str(spec['key']);sref=source_ref_by_key[spec['source_key']]
            payload={
                'source_ref':sref,'locator':deepcopy(spec.get('locator') or {'type':'FULL_SOURCE'}),
                'evidence_kind':spec.get('evidence_kind','DOCUMENT_EXCERPT'),'content_summary':spec['content_summary'],
                'extensions':{'research_audit':{'batch_id':batch_id,'evidence_key':key,'source_key':spec['source_key']}},
            }
            if spec.get('technical'):payload['technical']=deepcopy(spec['technical'])
            ref=tx.create_object('EVIDENCE',payload);evidence_refs.append(ref);ev_ref_by_key[key]=ref
            evidence_by_ref[(ref['id'],ref['version'])]=tx.staged.objects[(ref['id'],ref['version'])]

        attempt_ref=tx.create_artifact('RESEARCH_ATTEMPT_LOG',{
            'query':batch.get('query','Independent verification of Research Pack claim candidates.'),
            'provider':batch.get('provider','GMK_EXTERNAL_RESEARCH_AUDIT'),
            'strategy':batch.get('strategy','Verify claims with identified external sources; track source independence; narrow unsupported precision; preserve unresolved gaps.'),
            'sources_inspected':source_refs,
            'result':json.dumps({'batch_id':batch_id,'claim_decisions':len(batch.get('claims') or []),'source_count':len(source_refs),'evidence_count':len(evidence_refs)},ensure_ascii=False,sort_keys=True),
            'limitations':list(batch.get('limitations') or []),
            'extensions':{'research_audit':{'batch_id':batch_id,'batch_sha256':batch_sha256,'phase':'APPLIED'}},
        },origin_refs=source_refs)

        claim_refs=[]; dispositions={}
        audited_ids=set()
        for dec in batch.get('claims') or []:
            oid=str(dec['claim_id']); before=_head_object(tx.staged,oid); links=deepcopy(before.get('evidence_links') or [])
            if dec.get('replace_external_evidence_links'):
                # A changed assertion must not inherit support for the old wording.
                # Old links remain in immutable prior claim versions.
                links=[link for link in links if link.get('relation')=='CONTEXTUALIZES' and link.get('strength')=='CONTEXT_ONLY']
            for l in dec.get('evidence_links') or []:
                eref=ev_ref_by_key[l['evidence_key']]
                links.append({'evidence_ref':eref,'relation':l.get('relation','SUPPORTS'),'scope':list(l.get('scope') or ['EVENT']),'strength':l.get('strength','STRONG')})
            ctype=dec.get('claim_type',before['claim_type']); ctext=dec.get('claim_text',before['claim_text'])
            verification,certainty,production=_derive_claim_state(ctype,links,evidence_by_ref|{k:v for k,v in tx.staged.objects.items() if v.get('object_type')=='EVIDENCE'},source_by_ref|{k:v for k,v in tx.staged.objects.items() if v.get('object_type')=='SOURCE'})
            if dec.get('force_prohibit'):
                production={'narration_allowed':False,'language_mode':'PROHIBITED','reason':str(dec.get('prohibit_reason') or 'Research Audit explicitly keeps this claim out of production use.')}
            patch={'claim_text':ctext,'claim_type':ctype,'verification_state':verification,'evidence_links':links,'certainty':certainty,'production_use':production,
                   'extensions':deepcopy(before.get('extensions') or {})}
            ext=patch['extensions']; ext['research_audit']={'batch_id':batch_id,'audited':True,'note':dec.get('audit_note',''),'original_version':before['version']}
            nr=tx.create_version(oid,base_version=before['version'],patch=patch);tx.promote_active_version(oid,nr['version']);claim_refs.append(nr);audited_ids.add(oid)
            dispositions[verification]=dispositions.get(verification,0)+1

        # Optional newly discovered, independently supported claims that were not intake claims.
        created_claim_refs=[]
        for dec in batch.get('new_claims') or []:
            links=[]
            for l in dec.get('evidence_links') or []:
                eref=ev_ref_by_key[l['evidence_key']]
                links.append({'evidence_ref':eref,'relation':l.get('relation','SUPPORTS'),'scope':list(l.get('scope') or ['EVENT']),'strength':l.get('strength','STRONG')})
            ctype=dec.get('claim_type','FACTUAL_ASSERTION')
            verification,certainty,production=_derive_claim_state(ctype,links,{k:v for k,v in tx.staged.objects.items() if v.get('object_type')=='EVIDENCE'},{k:v for k,v in tx.staged.objects.items() if v.get('object_type')=='SOURCE'})
            ref=tx.create_object('CLAIM',{
                'claim_text':dec['claim_text'],'claim_type':ctype,'verification_state':verification,'evidence_links':links,'certainty':certainty,'production_use':production,'contradiction_refs':[],
                'extensions':{'research_audit':{'batch_id':batch_id,'audited':True,'new_finding':True,'finding_key':dec.get('key')}}
            });created_claim_refs.append(ref);dispositions[verification]=dispositions.get(verification,0)+1

        gap_refs=[]
        # Preserve the original unresolved questions. Add explicit audit discoveries instead of silently correcting the pack.
        for spec in batch.get('gaps') or []:
            resolution=None
            if spec.get('state')=='RESOLVED':
                resolution={'summary':spec['resolution_summary'],'evidence_refs':[ev_ref_by_key[k] for k in spec.get('resolution_evidence_keys') or []],'resolved_at':engine.now()}
            payload={'question':spec['question'],'importance':spec.get('importance','STANDARD'),'state':spec.get('state','OPEN'),'blocked_targets':[],
                     'blocked_gates':list(spec.get('blocked_gates') or []),'research_attempt_refs':[attempt_ref],
                     'extensions':{'research_audit':{'batch_id':batch_id,'finding_key':spec.get('key')}}}
            if resolution:payload['resolution']=resolution
            gap_refs.append(tx.create_object('RESEARCH_GAP',payload))

        # Close the intake guard only when every intake claim has a non-UNREVIEWED audit disposition.
        intake_claims=[]
        for reg in tx.staged.registries.values():
            for oid,entry in reg.entries.items():
                if entry.object_type!='CLAIM' or entry.active_version is None:continue
                obj=tx.staged.objects[(oid,int(entry.active_version))]
                intake=(obj.get('extensions') or {}).get('intake') or {}
                if intake.get('batch_id'):intake_claims.append(obj)
        all_audited=bool(intake_claims) and all(c.get('verification_state')!='UNREVIEWED' and ((c.get('extensions') or {}).get('research_audit') or {}).get('audited') for c in intake_claims)
        guards=[]
        for reg in tx.staged.registries.values():
            for oid,entry in reg.entries.items():
                if entry.object_type!='RESEARCH_GAP' or entry.active_version is None:continue
                g=tx.staged.objects[(oid,int(entry.active_version))]
                if ((g.get('extensions') or {}).get('intake') or {}).get('system_guard'):guards.append(g)
        if all_audited:
            for guard in guards:
                current_refs=[{'id':c['id'],'version':c['version']} for c in intake_claims]
                ext=deepcopy(guard.get('extensions') or {});ext['research_audit']={'batch_id':batch_id,'guard_closed':True}
                nr=tx.create_version(guard['id'],base_version=guard['version'],patch={
                    'state':'RESOLVED','blocked_targets':current_refs,'resolution':{'summary':'Every Research Pack intake claim received an explicit independent Research Audit disposition; unsupported claims remain prohibited rather than silently accepted.','evidence_refs':evidence_refs,'resolved_at':engine.now()},'extensions':ext,
                });tx.promote_active_version(guard['id'],nr['version']);gap_refs.append(nr)

        # Store exact result references on a new immutable attempt-log version for idempotent replay.
        attempt_ref_v2=tx.create_artifact_version(attempt_ref['artifact_id'],base_version=attempt_ref['version'],payload_patch={
            'extensions':{'research_audit':{'batch_id':batch_id,'batch_sha256':batch_sha256,'phase':'COMPLETE','summary':{
                'claim_refs':claim_refs,'source_refs':source_refs,'evidence_refs':evidence_refs,'created_claim_refs':created_claim_refs,'gap_refs':gap_refs,'disposition_counts':dispositions,
            }}}
        },origin_refs=source_refs)
        tx.commit()

        # Evaluate and, when legal, enter RESEARCH_AUDITED in a separate transaction so the gate sees committed exact state.
        gate=engine.gates.evaluate_gate(engine.snapshot(),'RESEARCH_AUDIT',engine.now()).result
        if transition_if_ready and gate in {'PASS','WARN'} and engine.project_state=='RESEARCH_INTAKE':
            t2=engine.begin(expected_manifest_version=engine.manifest_version,expected_registry_versions=engine.registry_versions())
            try:
                t2.transition_project_state('RESEARCH_AUDITED',actor_type='AI',human_confirmed=False);t2.commit()
            except StateEngineError:
                t2.discard();raise
        manifest=RuntimeStore(self.root,self.workspace).persist(engine)
        return ResearchAuditResult(self.workspace,batch_id,engine.project_state,manifest['manifest_version'],tuple(claim_refs),tuple(source_refs),tuple(evidence_refs),tuple(created_claim_refs),tuple(gap_refs),attempt_ref_v2,gate,dispositions,False)
