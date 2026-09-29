from __future__ import annotations
from copy import deepcopy
from typing import Any, Iterable
from .constants import SYSTEM_MANAGED_FIELDS,DERIVED_REFRESH_FIELDS,PROMOTION_ALLOWED_APPROVAL_STATES,PROMOTION_BLOCKING_STATUSES,PROJECT_STATES
from .errors import StateEngineError
from .models import ActionAudit, RegistryEntry
from .registry import ensure_registry,global_index,locator_for,registry_id_for_type
from .artifact_registry import artifact_payload_sha256, artifact_uri, locator_for_artifact, ArtifactRegistryEntry
from gmk_semantics.model import sha256_json
from gmk_dependency import NodeKey, NodeKind, ImpactDisposition

def _merge_patch(target:dict[str,Any],patch:dict[str,Any])->dict[str,Any]:
    out=deepcopy(target)
    for k,v in patch.items():
        if v is None:out.pop(k,None)
        elif isinstance(v,dict) and isinstance(out.get(k),dict):out[k]=_merge_patch(out[k],v)
        else:out[k]=deepcopy(v)
    return out

def _pointer_get(doc:Any,pointer:str):
    if pointer in {'','/'}:return deepcopy(doc)
    if not pointer.startswith('/'):raise StateEngineError('HUMAN_CONSTRAINT_PATH_INVALID',f'Constraint path must be JSON Pointer-like: {pointer}')
    cur=doc
    for raw in pointer.split('/')[1:]:
        key=raw.replace('~1','/').replace('~0','~')
        if isinstance(cur,list):
            try:cur=cur[int(key)]
            except (ValueError,IndexError):return None
        elif isinstance(cur,dict):
            if key not in cur:return None
            cur=cur[key]
        else:return None
    return deepcopy(cur)

class StateTransaction:
    def __init__(self,engine,staged):
        self.engine=engine; self.staged=staged; self.transaction_id=engine.next_transaction_id(); self.base_manifest_version=staged.manifest_version
        self.base_registry_versions={rid:r.version for rid,r in staged.registries.items()}; self.base_artifact_registry_version=staged.artifact_registry.version; self.dirty_registries=set(); self.dirty_artifact_registry=False; self.changed_keys=set(); self.changed_artifact_keys=set(); self.actions=[]; self.transition_checks=[]; self._closed=False; self._artifact_counter=0
    def _assert_open(self):
        if self._closed:raise StateEngineError('TRANSACTION_CLOSED','Transaction is already committed or discarded.')
    def _occupied_ids(self):return set(global_index(self.staged.registries))
    def _schema_id(self,object_type):
        s=self.engine.semantic.catalog.schema_for_object_type(object_type)
        if not s:raise StateEngineError('UNKNOWN_OBJECT_TYPE',f'No Core Object schema exists for {object_type}.')
        return s['$id']
    def _artifact_schema_id(self,artifact_type):
        s=self.engine.semantic.catalog.schema_for_artifact_type(artifact_type)
        if not s:raise StateEngineError('UNKNOWN_ARTIFACT_TYPE',f'No Artifact schema exists for {artifact_type}.')
        return s['$id']
    def _allocate_artifact_id(self,artifact_type):
        prefix=''.join(ch if ch.isalnum() else '_' for ch in artifact_type.upper()).strip('_')+'_'
        occupied=set(self.staged.artifact_registry.entries)
        n=1
        while f'{prefix}{n:06d}' in occupied:n+=1
        return f'{prefix}{n:06d}'
    @staticmethod
    def _reject_artifact_managed_fields(payload):
        managed={'schema_header','artifact_id','artifact_type','version','supersedes_version','uri','sha256','created_at'}
        bad=sorted(managed.intersection(payload))
        if bad:raise StateEngineError('ARTIFACT_SYSTEM_MANAGED_FIELD_OVERRIDE',f"State Engine owns these Artifact fields and callers may not set them: {', '.join(bad)}.",details=bad)
    def _write_artifact_record(self,artifact,*,new_identity):
        key=(artifact['artifact_id'],int(artifact['version']))
        if key in self.staged.artifacts:raise StateEngineError('ARTIFACT_VERSION_ALREADY_EXISTS',f"{artifact['artifact_id']}@{artifact['version']} already exists.")
        reg=self.staged.artifact_registry; aid=artifact['artifact_id']; loc=locator_for_artifact(artifact); entry=reg.entries.get(aid)
        if new_identity:
            if entry is not None:raise StateEngineError('ARTIFACT_ID_COLLISION',f'Artifact ID {aid} already exists.')
            reg.entries[aid]=ArtifactRegistryEntry(aid,artifact['artifact_type'],int(artifact['version']),{int(artifact['version']):loc})
        else:
            if entry is None:raise StateEngineError('ARTIFACT_REGISTRY_ENTRY_MISSING',f'No Artifact Registry entry exists for {aid}.')
            entry.head_version=int(artifact['version']);entry.versions[int(artifact['version'])]=loc
        self.staged.artifacts[key]=deepcopy(artifact);self.changed_artifact_keys.add(key);self.dirty_artifact_registry=True
        return {'artifact_id':aid,'artifact_type':artifact['artifact_type'],'version':int(artifact['version']),'sha256':artifact['sha256']}
    def create_artifact(self,artifact_type,payload,*,origin_refs=(),compiler=None):
        self._assert_open();artifact_type=artifact_type.upper();self._reject_artifact_managed_fields(payload)
        aid=self._allocate_artifact_id(artifact_type);now=self.engine.now()
        artifact={'schema_header':{'schema_id':self._artifact_schema_id(artifact_type),'schema_version':'1.0.0'},'artifact_id':aid,'artifact_type':artifact_type,'version':1,'uri':artifact_uri(aid,1),'sha256':'0'*64,'created_at':now,'origin_refs':deepcopy(list(origin_refs)),'extensions':{},**deepcopy(payload)}
        if compiler is not None:artifact['compiler']=deepcopy(compiler)
        artifact['sha256']=artifact_payload_sha256(artifact)
        ref=self._write_artifact_record(artifact,new_identity=True)
        self.actions.append(ActionAudit('CREATE_ARTIFACT',(f'{aid}@1',),{'artifact_type':artifact_type}));return ref
    def create_artifact_version(self,artifact_id,*,base_version,payload_patch,origin_refs=None,compiler=None):
        self._assert_open();self._reject_artifact_managed_fields(payload_patch);entry=self.staged.artifact_registry.entries.get(artifact_id)
        if entry is None:raise StateEngineError('ARTIFACT_NOT_FOUND',f'Artifact {artifact_id} does not exist.')
        if int(base_version)!=entry.head_version:raise StateEngineError('ARTIFACT_REVISION_BASE_VERSION_MISMATCH',f'Artifact revision must branch from HEAD {artifact_id}@{entry.head_version}.')
        before=deepcopy(self.staged.artifacts[(artifact_id,entry.head_version)]);after=_merge_patch(before,payload_patch);new_version=entry.head_version+1
        after.update({'artifact_id':artifact_id,'artifact_type':before['artifact_type'],'version':new_version,'supersedes_version':entry.head_version,'schema_header':deepcopy(before['schema_header']),'uri':artifact_uri(artifact_id,new_version),'created_at':self.engine.now()})
        if origin_refs is not None:after['origin_refs']=deepcopy(list(origin_refs))
        if compiler is not None:after['compiler']=deepcopy(compiler)
        after['sha256']=artifact_payload_sha256(after)
        ref=self._write_artifact_record(after,new_identity=False)
        self.actions.append(ActionAudit('CREATE_ARTIFACT_VERSION',(f'{artifact_id}@{new_version}',),{'base_version':base_version}));return ref
    def _new_envelope(self,object_type,object_id,payload):
        now=self.engine.now(); constraints=deepcopy(payload.get('human_constraints',[])); extensions=deepcopy(payload.get('extensions',{})); domain={k:deepcopy(v) for k,v in payload.items() if k not in {'human_constraints','extensions'}}
        obj={'schema_header':{'schema_id':self._schema_id(object_type),'schema_version':'1.0.0'},'id':object_id,'object_type':object_type,'version':1,'status':'CURRENT','lock_state':'HUMAN_LOCKED' if constraints else 'UNLOCKED','created_at':now,'updated_at':now,'dependencies':[],'stale':{'is_stale':False,'reasons':[]},'approval_summary':{'state':'NOT_REQUIRED','approval_refs':[]},'human_constraints':constraints,'extensions':extensions,**domain}
        obj['dependencies']=self.engine.dependency.compile_object_projection(obj)
        return obj
    @staticmethod
    def _reject_managed_fields(payload):
        bad=sorted(SYSTEM_MANAGED_FIELDS.intersection(payload))
        if bad:raise StateEngineError('SYSTEM_MANAGED_FIELD_OVERRIDE',f"State Engine owns these fields and callers may not set them: {', '.join(bad)}.",details=bad)
    def _write_object(self,obj,*,new_identity,activate=None):
        key=(obj['id'],int(obj['version']))
        if key in self.staged.objects:raise StateEngineError('OBJECT_VERSION_ALREADY_EXISTS',f"{obj['id']}@{obj['version']} already exists.")
        rid=registry_id_for_type(obj['object_type']); reg=ensure_registry(self.staged.registries,rid)
        if rid not in self.base_registry_versions:self.base_registry_versions[rid]=0
        entry=reg.entries.get(obj['id']); loc=locator_for(obj,self.engine.semantic.decision_hash(obj))
        if new_identity:
            if entry is not None:raise StateEngineError('GLOBAL_ID_COLLISION',f"Stable object ID {obj['id']} already exists.")
            reg.entries[obj['id']]=RegistryEntry(obj['id'],obj['object_type'],int(obj['version']),int(obj['version']) if activate else None,{int(obj['version']):loc})
        else:
            if entry is None:raise StateEngineError('REGISTRY_ENTRY_MISSING',f"No registry entry exists for {obj['id']}.")
            entry.head_version=int(obj['version']); entry.versions[int(obj['version'])]=loc
        self.staged.objects[key]=deepcopy(obj); self.dirty_registries.add(rid); self.changed_keys.add(key); return {'id':obj['id'],'version':int(obj['version'])}
    def _create_object(self,object_type,payload,*,activate=True,action_type='CREATE_OBJECT',audit_detail=None):
        self._assert_open(); object_type=object_type.upper(); self._reject_managed_fields(payload); oid=self.engine.allocate_id(object_type,self._occupied_ids()); obj=self._new_envelope(object_type,oid,payload); ref=self._write_object(obj,new_identity=True,activate=activate); self.actions.append(ActionAudit(action_type,(f'{oid}@1',),audit_detail or {'activate':activate})); return ref
    def create_object(self,object_type,payload,*,activate=True):return self._create_object(object_type,payload,activate=activate)
    def _authorized_release_ids(self,refs):
        out=set()
        for ref in refs:
            obj=self.staged.objects.get((ref.get('id'),int(ref.get('version',0))))
            if not obj or obj.get('object_type')!='EDIT_REQUEST':raise StateEngineError('HUMAN_CONSTRAINT_RELEASE_UNAUTHORIZED','Constraint release requires an exact EDIT_REQUEST reference.')
            d=obj.get('directive',{})
            if d.get('type')!='RELEASE_CONSTRAINT' or not d.get('constraint_id'):raise StateEngineError('HUMAN_CONSTRAINT_RELEASE_UNAUTHORIZED','Referenced Edit Request is not an explicit RELEASE_CONSTRAINT directive.')
            out.add(d['constraint_id'])
        return out
    def _check_human_locks(self,before,after,released):
        after_constraints={c.get('constraint_id'):c for c in after.get('human_constraints',[])}
        for c in before.get('human_constraints',[]):
            cid=c.get('constraint_id')
            if not cid or cid in released:continue
            if cid not in after_constraints:raise StateEngineError('HUMAN_CONSTRAINT_NOT_PRESERVED',f'Constraint {cid} cannot be removed without explicit Human release.')
            path=(c.get('scope') or {}).get('path')
            if path and _pointer_get(before,path)!=_pointer_get(after,path):raise StateEngineError('HUMAN_LOCK_CONFLICT',f'Revision changes Human-locked path {path} under constraint {cid}.')
    def create_version(self,object_id,*,base_version,patch,release_edit_request_refs=()):
        self._assert_open(); self._reject_managed_fields(patch); rid=global_index(self.staged.registries).get(object_id)
        if not rid:raise StateEngineError('OBJECT_NOT_FOUND',f'Object {object_id} does not exist.')
        entry=self.staged.registries[rid].entries[object_id]
        if int(base_version)!=entry.head_version:raise StateEngineError('REVISION_BASE_VERSION_MISMATCH',f'CREATE_VERSION must branch from current HEAD {object_id}@{entry.head_version}, not @{base_version}.')
        before=deepcopy(self.staged.objects[(object_id,entry.head_version)])
        if before.get('object_type')=='RELEASE' and before.get('state')=='RELEASED':
            raise StateEngineError('RELEASED_OBJECT_MUTATION_FORBIDDEN',f'{object_id}@{entry.head_version} is an immutable RELEASED Release; create a new RELEASE object instead.')
        if before.get('lock_state')=='SYSTEM_FROZEN':raise StateEngineError('SYSTEM_FROZEN_MUTATION_FORBIDDEN',f'{object_id}@{entry.head_version} is SYSTEM_FROZEN.')
        after=_merge_patch(before,patch); released=self._authorized_release_ids(release_edit_request_refs); self._check_human_locks(before,after,released)
        if released:
            ext=deepcopy(after.get('extensions',{})); prior=set(ext.get('released_human_constraints',[])); ext['released_human_constraints']=sorted(prior|released); after['extensions']=ext
        now=self.engine.now(); new_version=entry.head_version+1
        after.update({'id':object_id,'object_type':before['object_type'],'version':new_version,'supersedes':{'id':object_id,'version':entry.head_version},'schema_header':deepcopy(before['schema_header']),'created_at':now,'updated_at':now,'status':'CURRENT','stale':{'is_stale':False,'reasons':[]}})
        prev=(before.get('approval_summary') or {}).get('state','NOT_REQUIRED'); after['approval_summary']={'state':'NOT_REQUIRED' if prev=='NOT_REQUIRED' else ('REQUIRED' if prev=='REQUIRED' else 'INVALIDATED'),'approval_refs':[]}; after['lock_state']='HUMAN_LOCKED' if after.get('human_constraints') else 'UNLOCKED'
        after['dependencies']=self.engine.dependency.compile_object_projection(after)
        ref=self._write_object(after,new_identity=False); self.actions.append(ActionAudit('CREATE_VERSION',(f'{object_id}@{new_version}',),{'base_version':base_version})); return ref
    def preview_promotion_impact(self,object_id,version):
        self._assert_open(); rid=global_index(self.staged.registries).get(object_id)
        if not rid:raise StateEngineError('OBJECT_NOT_FOUND',f'Object {object_id} does not exist.')
        entry=self.staged.registries[rid].entries[object_id]; version=int(version)
        if version not in entry.versions:raise StateEngineError('OBJECT_VERSION_NOT_FOUND',f'{object_id}@{version} does not exist.')
        return self.engine.dependency.analyze_promotion(self.staged,object_id,version,self.engine.semantic)

    def _write_dependency_impact_report(self,report):
        self._artifact_counter+=1
        aid=f"DEP_IMPACT_{self.transaction_id}_{self._artifact_counter:03d}"
        payload=report.to_payload();now=self.engine.now()
        # Persisted ArtifactRefs carry type + payload checksum. The dependency engine
        # deliberately uses lighter internal NodeKeys, so enrich Artifact node
        # descriptors at the persistence boundary.
        def enrich(desc):
            if not isinstance(desc,dict) or desc.get('kind')!='ARTIFACT':return
            ref=desc.get('ref') or {}; art=self.staged.artifacts.get((ref.get('artifact_id'),int(ref.get('version',0))))
            if art:
                ref['artifact_type']=art['artifact_type'];ref['sha256']=art['sha256'];desc['ref']=ref
        for d in (payload.get('root_change') or {}).values():enrich(d)
        for imp in payload.get('impacts') or []:
            for k in ('node','immediate_dependency','root_previous','root_new'):enrich(imp.get(k))
        for d in payload.get('frozen_stops') or []:enrich(d)
        artifact={
            'schema_header':{'schema_id':'gmk://schema/v1/artifact/dependency-impact-report','schema_version':'1.0.0'},
            'artifact_id':aid,'artifact_type':'DEPENDENCY_IMPACT_REPORT','version':1,
            'uri':artifact_uri(aid,1),'sha256':'0'*64,'created_at':now,
            'origin_refs':[report.root_previous.to_ref(),report.root_new.to_ref()],
            'extensions':{},**payload,
        }
        artifact['sha256']=artifact_payload_sha256(artifact)
        return self._write_artifact_record(artifact,new_identity=True)

    def promote_active_version(self,object_id,version,*,confirm_locked_impact=False):
        self._assert_open(); rid=global_index(self.staged.registries).get(object_id)
        if not rid:raise StateEngineError('OBJECT_NOT_FOUND',f'Object {object_id} does not exist.')
        entry=self.staged.registries[rid].entries[object_id]; version=int(version)
        if version not in entry.versions:raise StateEngineError('OBJECT_VERSION_NOT_FOUND',f'{object_id}@{version} does not exist.')
        c=self.staged.objects[(object_id,version)]
        if c.get('status') in PROMOTION_BLOCKING_STATUSES or (c.get('stale') or {}).get('is_stale'):raise StateEngineError('PROMOTION_TARGET_INELIGIBLE',f'{object_id}@{version} is stale/blocked/archived/rejected.')
        if NodeKey(NodeKind.OBJECT,object_id,version) in getattr(self.staged,'dependency_invalidations',{}):raise StateEngineError('PROMOTION_TARGET_REVALIDATION_REQUIRED',f'{object_id}@{version} has an unresolved dependency invalidation.')
        if c.get('lock_state')=='SYSTEM_FROZEN':raise StateEngineError('PROMOTION_TARGET_SYSTEM_FROZEN',f'{object_id}@{version} is SYSTEM_FROZEN.')
        a=(c.get('approval_summary') or {}).get('state','NOT_REQUIRED')
        if a not in PROMOTION_ALLOWED_APPROVAL_STATES:raise StateEngineError('PROMOTION_APPROVAL_UNSATISFIED',f'{object_id}@{version} approval summary is {a}.')
        previous=entry.active_version
        report=self.engine.dependency.analyze_promotion(self.staged,object_id,version,self.engine.semantic)
        critical=set(report.change_set.impact_tags)&{'FACTUAL','RIGHTS','SAFETY'}
        locked=[]
        for impact in report.impacts:
            if impact.disposition==ImpactDisposition.UNAFFECTED:continue
            if impact.node.kind!=NodeKind.OBJECT:continue
            dep=self.staged.objects.get((impact.node.node_id,impact.node.version))
            if dep and dep.get('lock_state')=='HUMAN_LOCKED':locked.append(impact.node.label())
        if locked and not critical and not confirm_locked_impact:
            raise StateEngineError('PROMOTION_LOCKED_IMPACT_CONFIRMATION_REQUIRED','Promotion affects Human-locked downstream decisions; review the dry-run impact and confirm explicitly.',details={'locked_targets':locked,'impact':report.to_payload()})
        entry.active_version=version; self.dirty_registries.add(rid)
        applied=self.engine.dependency.apply_report(self.staged,report,self.engine.now())
        for key in applied['changed_objects']:
            obj=self.staged.objects[key]; rrid=global_index(self.staged.registries).get(obj['id'])
            if rrid:
                dec=self.engine.semantic.decision_hash(obj)
                self.staged.registries[rrid].entries[obj['id']].versions[int(obj['version'])]=locator_for(obj,dec)
                self.dirty_registries.add(rrid); self.changed_keys.add(key)
        impact_ref=None
        if previous is not None and int(previous)!=version:
            impact_ref=self._write_dependency_impact_report(report)
        detail={'previous_active_version':previous,'changed_paths':list(report.change_set.changed_paths),'impact_tags':list(report.change_set.impact_tags),'blast_radius':report.blast_radius,'impacted_nodes':len(report.impacts)}
        if impact_ref:detail['dependency_impact_report']=impact_ref
        self.actions.append(ActionAudit('PROMOTE_ACTIVE_VERSION',(f'{object_id}@{version}',),detail)); return {'id':object_id,'version':version,'dependency_impact_report':impact_ref}

    def _refresh_exact(self,object_id,version,updates):
        bad=sorted(set(updates)-DERIVED_REFRESH_FIELDS)
        if bad:raise StateEngineError('DERIVED_REFRESH_FIELD_FORBIDDEN',f"Only live-derived fields may be refreshed without a new decision version: {', '.join(bad)}.")
        key=(object_id,int(version))
        if key not in self.staged.objects:raise StateEngineError('OBJECT_VERSION_NOT_FOUND',f'{object_id}@{version} does not exist.')
        before=deepcopy(self.staged.objects[key]); after=deepcopy(before)
        for k,v in updates.items():after[k]=deepcopy(v)
        after['updated_at']=self.engine.now(); bd=self.engine.semantic.decision_hash(before); ad=self.engine.semantic.decision_hash(after)
        if bd!=ad:raise StateEngineError('DERIVED_REFRESH_CHANGED_DECISION','Derived refresh changed the authoritative decision hash.')
        self.staged.objects[key]=after; rid=global_index(self.staged.registries)[object_id]; self.staged.registries[rid].entries[object_id].versions[int(version)]=locator_for(after,ad); self.dirty_registries.add(rid); self.changed_keys.add(key)
    def refresh_derived_state(self,object_id,version,updates):self._assert_open(); self._refresh_exact(object_id,version,updates); self.actions.append(ActionAudit('REFRESH_DERIVED_STATE',(f'{object_id}@{version}',),{'fields':sorted(updates)})); return {'id':object_id,'version':int(version)}
    def revalidate_dependency_node(self,node_id,version,*,artifact=False):
        self._assert_open(); node=NodeKey(NodeKind.ARTIFACT if artifact else NodeKind.OBJECT,node_id,int(version))
        ok=self.engine.dependency.revalidate_node(self.staged,node,self.engine.now())
        if not ok:raise StateEngineError('DEPENDENCY_REVALIDATION_FAILED',f'{node.label()} cannot be cleared because one or more exact dependencies remain unresolved or invalid.')
        if not artifact:
            key=(node_id,int(version)); obj=self.staged.objects[key]; rid=global_index(self.staged.registries).get(node_id)
            if rid:
                dec=self.engine.semantic.decision_hash(obj); self.staged.registries[rid].entries[node_id].versions[int(version)]=locator_for(obj,dec); self.dirty_registries.add(rid); self.changed_keys.add(key)
        self.actions.append(ActionAudit('REVALIDATE_DEPENDENCY_NODE',(node.label(),),{})); return node.to_ref()

    def archive_object(self,object_id):
        self._assert_open(); rid=global_index(self.staged.registries).get(object_id)
        if not rid:raise StateEngineError('OBJECT_NOT_FOUND',f'Object {object_id} does not exist.')
        entry=self.staged.registries[rid].entries[object_id]; head=entry.head_version; self._refresh_exact(object_id,head,{'status':'ARCHIVED'}); previous=entry.active_version; entry.active_version=None; self.dirty_registries.add(rid); self.actions.append(ActionAudit('ARCHIVE_OBJECT',(f'{object_id}@{head}',),{'previous_active_version':previous})); return {'id':object_id,'version':head}
    def create_approval(self,payload,*,activate=True):return self._create_object('APPROVAL',payload,activate=activate,action_type='CREATE_APPROVAL')
    def create_edit_request(self,payload,*,activate=True):return self._create_object('EDIT_REQUEST',payload,activate=activate,action_type='CREATE_EDIT_REQUEST')
    def apply_revision(self,*,reason_type,edits,edit_request_refs=(),impact=None,activate_new_versions=False):
        self._assert_open(); edit_request_refs=list(edit_request_refs); changes=[]; new_refs=[]; preserved=set()
        for edit in edits:
            oid=edit['object_id']; base=int(edit['base_version']); before=self.staged.objects.get((oid,base))
            if not before:raise StateEngineError('REVISION_BASE_NOT_FOUND',f'Revision base {oid}@{base} does not exist.')
            nr=self.create_version(oid,base_version=base,patch=edit.get('patch',{}),release_edit_request_refs=edit_request_refs); after=self.staged.objects[(nr['id'],nr['version'])]; preserved.update(c.get('constraint_id') for c in after.get('human_constraints',[]) if c.get('constraint_id')); changes.append({'from':{'id':oid,'version':base},'to':deepcopy(nr),'changed_paths':list(edit.get('changed_paths') or ['/']),'summary':edit.get('summary') or 'Revision applied by State Engine.'}); new_refs.append(nr)
            if activate_new_versions:self.promote_active_version(oid,nr['version'])
        payload={'reason':{'type':reason_type},'edit_request_refs':deepcopy(edit_request_refs),'changes':changes,'preserved_constraints':sorted(preserved),'workflow_state':'APPLIED'}
        if impact is not None:payload['impact']=deepcopy(impact)
        rr=self._create_object('REVISION',payload,activate=True,action_type='APPLY_REVISION',audit_detail={'changed_objects':[f"{r['id']}@{r['version']}" for r in new_refs]}); return {'revision_ref':rr,'new_versions':new_refs}
    def transition_project_state(self,to_state,*,actor_type='SYSTEM',human_confirmed=False):
        self._assert_open()
        if to_state not in PROJECT_STATES:raise StateEngineError('PROJECT_STATE_INVALID',f'Unknown Project State {to_state}.')
        fr=self.staged.project_state
        decision=self.engine.gates.evaluate_transition(self.staged,fr,to_state,self.engine.now(),actor_type=actor_type,human_confirmed=human_confirmed)
        if self.engine.transition_authorizer is not None and decision.allowed:
            if not self.engine.transition_authorizer(fr,to_state,self.staged.clone()):
                raise StateEngineError('PROJECT_STATE_TRANSITION_CUSTOM_VETO',f'Custom transition authorizer vetoed {fr} -> {to_state}.')
        if not decision.allowed:
            raise StateEngineError('PROJECT_STATE_TRANSITION_DENIED',f'Transition {fr} -> {to_state} was not authorized by the Gate Engine.',details=decision.to_dict())
        self.staged.project_state=to_state; self.staged.project_state_entered_at=self.engine.now()
        self.staged.gate_evaluations=tuple(self.staged.gate_evaluations)+tuple(g.evaluation.to_dict() for g in decision.gate_results)
        self.transition_checks.append({'from':fr,'to':to_state,'actor_type':actor_type,'human_confirmed':bool(human_confirmed)})
        self.actions.append(ActionAudit('TRANSITION_PROJECT_STATE',(),{'from':fr,'to':to_state,'permission_class':decision.permission_class,'gate_evaluation_ids':[g.evaluation.evaluation_id for g in decision.gate_results]})); return to_state

    def reenter_stage(self,to_state,*,actor_type='HUMAN'):
        self._assert_open()
        if to_state not in PROJECT_STATES:raise StateEngineError('PROJECT_STATE_INVALID',f'Unknown Project State {to_state}.')
        fr=self.staged.project_state
        if actor_type!='HUMAN':raise StateEngineError('REENTER_STAGE_HUMAN_ONLY','REENTER_STAGE is HUMAN_ONLY.')
        if PROJECT_STATES.index(to_state)>=PROJECT_STATES.index(fr):raise StateEngineError('REENTER_STAGE_DIRECTION_INVALID','REENTER_STAGE may only move to an earlier Project State.')
        blockers=self.engine.gates.derive_blockers(self.staged,action_id='REENTER_STAGE')
        if self.staged.safety_mode!='NORMAL' or blockers:
            raise StateEngineError('REENTER_STAGE_BLOCKED','REENTER_STAGE is blocked by safety mode or scoped blockers.',details=[b.to_dict() for b in blockers])
        self.staged.project_state=to_state; self.staged.project_state_entered_at=self.engine.now()
        self.actions.append(ActionAudit('REENTER_STAGE',(),{'from':fr,'to':to_state,'actor_type':actor_type})); return to_state

    def commit(self):
        self._assert_open()
        try:v=self.engine._publish(self); self._closed=True; return v
        except Exception:self._closed=True; raise
    def discard(self):self._closed=True
