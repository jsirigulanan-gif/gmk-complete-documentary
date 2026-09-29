from __future__ import annotations
from copy import deepcopy
from gmk_state.errors import StateEngineError
from gmk_semantics.model import sha256_json

class QARuntime:
    def __init__(self,engine):self.engine=engine
    def evaluate(self, *, report_type, scope, observed_artifact=None, qa_profile=None, findings=()):
        qa_profile=qa_profile or {'config_id':f'GMK_{report_type}_PROFILE','version':'1.0.0','sha256':'d'*64}
        tx=self.engine.begin();refs=[];counts={'CRITICAL':0,'MAJOR':0,'MINOR':0}
        for f in findings:
            sev=f.get('severity','MINOR').upper();counts[sev]=counts.get(sev,0)+1
            root=deepcopy(f.get('root_cause') or {'state':'UNIDENTIFIED'})
            payload={'qa_domain':f.get('qa_domain',report_type.replace('_QA','')),'severity':sev,'code':f['code'],'target':deepcopy(f.get('target') or scope),'description':f.get('description',f['code']),'root_cause':root,'workflow_state':f.get('workflow_state','OPEN')}
            if observed_artifact:payload['observed_on']=deepcopy(observed_artifact)
            if f.get('expected') is not None:payload['expected']=f['expected']
            if f.get('location') is not None:payload['location']=deepcopy(f['location'])
            refs.append(tx.create_object('QA_ISSUE',payload,activate=True))
        blocking=counts.get('CRITICAL',0)+counts.get('MAJOR',0)
        result='FAIL' if blocking else ('WARN' if counts.get('MINOR',0) else 'PASS')
        rp={'report_type':report_type,'scope':deepcopy(scope),'qa_profile':deepcopy(qa_profile),'issue_refs':refs,'result':result,'summary':{'critical':counts.get('CRITICAL',0),'major':counts.get('MAJOR',0),'minor':counts.get('MINOR',0)},'evaluated_at':self.engine.now()}
        if observed_artifact:rp['observed_artifact']=deepcopy(observed_artifact)
        rr=tx.create_object('QA_REPORT',rp,activate=True);tx.commit();return {'report_ref':rr,'issue_refs':refs,'result':result}
    def plan_repair(self, issue_ref, *, proposed_changes, affected_scope='LOCAL', required_retests=(), auto=False):
        s=self.engine.snapshot();issue=s.objects.get((issue_ref['id'],int(issue_ref['version'])))
        if not issue or issue.get('object_type')!='QA_ISSUE':raise StateEngineError('QA_ISSUE_NOT_FOUND','Repair plan requires exact QA_ISSUE.')
        if (issue.get('root_cause') or {}).get('state') not in {'IDENTIFIED','BOUNDED_UNKNOWN'}:raise StateEngineError('REPAIR_WITHOUT_ROOT_CAUSE','Root cause must be identified/bounded first.')
        attempt=1
        if auto:
            existing=[a for a in s.artifacts.values() if a.get('artifact_type')=='REPAIR_PLAN' and a.get('qa_issue_ref')==issue_ref and (a.get('extensions') or {}).get('auto_repair')]
            attempt=len(existing)+1
            if attempt>2:raise StateEngineError('AUTO_REPAIR_LIMIT_EXCEEDED','Automatic repair is capped at 2 cycles.')
        tx=self.engine.begin();ref=tx.create_artifact('REPAIR_PLAN',{'qa_issue_ref':deepcopy(issue_ref),'root_cause':deepcopy(issue['root_cause']),'proposed_changes':deepcopy(list(proposed_changes)),'affected_scope':affected_scope,'required_retests':list(required_retests),'extensions':{'auto_repair':bool(auto),'auto_repair_attempt':attempt} if auto else {}},origin_refs=[issue_ref]);tx.commit();return ref
    def resolve_issue(self, issue_ref, verification_report_ref):
        s=self.engine.snapshot();issue=s.objects.get((issue_ref['id'],int(issue_ref['version'])));report=s.objects.get((verification_report_ref['id'],int(verification_report_ref['version'])))
        if not issue or issue.get('object_type')!='QA_ISSUE':raise StateEngineError('QA_ISSUE_NOT_FOUND','Issue missing.')
        if not report or report.get('object_type')!='QA_REPORT' or report.get('result') not in {'PASS','WARN'}:raise StateEngineError('QA_RETEST_NOT_ACCEPTABLE','Verification report must be PASS/WARN.')
        tx=self.engine.begin();nr=tx.create_version(issue['id'],base_version=issue['version'],patch={'workflow_state':'RESOLVED','verification_report_ref':deepcopy(verification_report_ref)});tx.promote_active_version(issue['id'],nr['version'],confirm_locked_impact=True);tx.commit();return nr
    def create_baseline(self, *, scope, production_lock, render_manifest_ref, qa_report_refs, output_refs):
        payload={'scope':deepcopy(scope),'production_lock':deepcopy(production_lock),'render_manifest_ref':deepcopy(render_manifest_ref),'qa_report_refs':deepcopy(list(qa_report_refs)),'output_refs':deepcopy(list(output_refs))}
        payload['baseline_sha256']=sha256_json(payload)
        tx=self.engine.begin();ref=tx.create_artifact('QA_BASELINE',payload,origin_refs=[production_lock,render_manifest_ref,*qa_report_refs,*output_refs]);tx.commit();return ref
    def regression_compare(self, *, baseline_ref, candidate_output_ref, expected_changed_scope=(), observed_changed_scope=()):
        unexpected=sorted(set(observed_changed_scope)-set(expected_changed_scope));result='FAIL' if unexpected else 'PASS'
        tx=self.engine.begin();ref=tx.create_artifact('REGRESSION_COMPARE',{'baseline':deepcopy(baseline_ref),'candidate_output':deepcopy(candidate_output_ref),'expected_changed_scope':list(expected_changed_scope),'observed_changed_scope':list(observed_changed_scope),'unexpected_changes':unexpected,'result':result},origin_refs=[baseline_ref,candidate_output_ref]);tx.commit();return ref
    def evaluate_full_film(self, *, production_lock, master_output, viewer_findings=(), production_findings=(), delivery_integrity_findings=(), qa_profiles=None):
        """Run the three required Full Film QA passes and persist an aggregate report/package.

        ``qa_profiles`` is optional and preserves the original Build 009 API. Build 032
        uses it to pin each explicit human review payload into the immutable QA report.
        """
        qa_profiles=qa_profiles or {}
        viewer=self.evaluate(report_type='VIEWER_EXPERIENCE_QA',scope=production_lock,observed_artifact=master_output,qa_profile=qa_profiles.get('viewer'),findings=viewer_findings)
        prod=self.evaluate(report_type='PRODUCTION_INTEGRITY_QA',scope=production_lock,observed_artifact=master_output,qa_profile=qa_profiles.get('production'),findings=production_findings)
        delivery=self.evaluate(report_type='DELIVERY_INTEGRITY_QA',scope=production_lock,observed_artifact=master_output,qa_profile=qa_profiles.get('delivery_integrity'),findings=delivery_integrity_findings)
        state=self.engine.snapshot(); refs=[viewer['report_ref'],prod['report_ref'],delivery['report_ref']]
        reports=[state.objects[(r['id'],int(r['version']))] for r in refs]
        results=[r['result'] for r in reports]; result='FAIL' if 'FAIL' in results else ('WARN' if 'WARN' in results else 'PASS')
        issue_refs=[]; counts={'critical':0,'major':0,'minor':0}
        for r in reports:
            issue_refs.extend(deepcopy(r.get('issue_refs') or []))
            for k in counts: counts[k]+=int((r.get('summary') or {}).get(k,0))
        tx=self.engine.begin()
        aggregate_profile=deepcopy(qa_profiles.get('aggregate') or {'config_id':'GMK_FULL_FILM_QA','version':'1.0.0','sha256':'e'*64})
        aggregate=tx.create_object('QA_REPORT',{'report_type':'FULL_FILM_QA','scope':deepcopy(production_lock),'observed_artifact':deepcopy(master_output),'qa_profile':aggregate_profile,'issue_refs':issue_refs,'result':result,'summary':counts,'evaluated_at':self.engine.now()},activate=True)
        package=tx.create_artifact('FULL_FILM_QA_PACKAGE',{'production_lock':deepcopy(production_lock),'master_output':deepcopy(master_output),'viewer_experience_report':viewer['report_ref'],'production_integrity_report':prod['report_ref'],'delivery_integrity_report':delivery['report_ref']},origin_refs=[production_lock,master_output,*refs,aggregate])
        tx.commit()
        return {'result':result,'report_ref':aggregate,'package_ref':package,'pass_reports':{'viewer':viewer['report_ref'],'production':prod['report_ref'],'delivery_integrity':delivery['report_ref']}}

