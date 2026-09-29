from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
import hashlib, yaml

from gmk_state.errors import StateEngineError
from gmk_state.registry import global_index
from gmk_semantics.model import sha256_json
from gmk_production import ProductionLockRuntime
from gmk_operations import OperationRuntime, OperationExecutionResult
from gmk_recovery import CheckpointRuntime
from gmk_qa import QARuntime


def _obj_ref(o:dict[str,Any])->dict[str,Any]: return {'id':o['id'],'version':int(o['version'])}
def _art_ref(a:dict[str,Any])->dict[str,Any]: return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}

@dataclass(frozen=True)
class PublishResult:
    release_ref: dict[str,Any]
    operation_ref: dict[str,Any]
    final_checkpoint_ref: dict[str,Any] | None = None

class ReleaseRuntime:
    """Release/delivery boundary for frozen GMK Schema v1.

    The runtime never treats a rendered file as a release by itself. A Release is
    created only after a project-scope Production Lock, Full Film QA, Delivery QA,
    provenance, rights checks, a verified pre-release Checkpoint, and a successful
    PUBLISH Operation all agree on exact versions/hashes.
    """
    def __init__(self, engine, *, workspace:Path|None=None):
        self.engine=engine; self.root=Path(engine.root); self.workspace=Path(workspace) if workspace is not None else None
        self.locks=ProductionLockRuntime(engine); self.qa=QARuntime(engine); self.ops=OperationRuntime(engine); self.checkpoints=CheckpointRuntime(engine,workspace=workspace)
        p=self.root/'config'/'release_policies.yaml'; self.policy=yaml.safe_load(p.read_text(encoding='utf-8')) or {}

    def _object(self,ref,typ=None):
        if not ref:return None
        o=self.engine.snapshot().objects.get((ref.get('id'),int(ref.get('version',0))))
        if not o:raise StateEngineError('RELEASE_OBJECT_MISSING','Exact Core Object reference is missing.',details=ref)
        if typ and o.get('object_type')!=typ:raise StateEngineError('RELEASE_OBJECT_TYPE_INVALID',f'Expected {typ}, got {o.get("object_type")}.',details=ref)
        return o

    def _artifact(self,ref,typ=None):
        if not ref:return None
        a=self.engine.snapshot().artifacts.get((ref.get('artifact_id'),int(ref.get('version',0))))
        if not a or a.get('sha256')!=ref.get('sha256'):raise StateEngineError('RELEASE_ARTIFACT_MISSING','Exact Artifact reference/hash is missing.',details=ref)
        if typ and a.get('artifact_type')!=typ:raise StateEngineError('RELEASE_ARTIFACT_TYPE_INVALID',f'Expected {typ}, got {a.get("artifact_type")}.',details=ref)
        return a

    def _approval(self,approval_class,target):
        s=self.engine.snapshot();idx=global_index(s.registries)
        for oid,rid in idx.items():
            e=s.registries[rid].entries[oid]
            if e.object_type!='APPROVAL' or e.active_version is None:continue
            a=s.objects.get((oid,int(e.active_version)))
            if not a or a.get('decision')!='APPROVED' or a.get('approval_class')!=approval_class:continue
            if a.get('status') in {'STALE','BLOCKED','REJECTED'} or (a.get('stale') or {}).get('is_stale'):continue
            if a.get('target')==target:return a
        return None

    def load_delivery_profile(self,config_id='GMK_YOUTUBE_4K'):
        folder=self.root/'config'/'delivery_profiles'
        for p in sorted(folder.glob('*.yaml')):
            data=yaml.safe_load(p.read_text(encoding='utf-8')) or {}
            if data.get('config_id')==config_id:
                ref={'config_id':config_id,'version':str(data['version']),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                return data,ref
        raise StateEngineError('DELIVERY_PROFILE_NOT_FOUND',f'Delivery Profile {config_id} not found.')

    def assert_project_lock_ready(self,lock_ref):
        lock=self.locks.assert_valid(lock_ref)
        if (lock.get('scope') or {}).get('type')!='PROJECT':raise StateEngineError('RELEASE_PROJECT_LOCK_REQUIRED','Release requires PROJECT-scope Production Lock.')
        required=(self.policy.get('production_lock') or {}).get('require_approval_class','PRODUCTION_LOCK')
        if not self._approval(required,lock_ref):raise StateEngineError('RELEASE_PRODUCTION_LOCK_APPROVAL_MISSING',f'Project Production Lock requires exact {required} approval.')
        return lock

    def _locked_usage(self,lock):
        s=self.engine.snapshot(); layer_to_shots={}
        for sr in lock.get('shots',[]):
            shot=self._object(sr,'SHOT')
            for lr in shot.get('layer_refs',[]):layer_to_shots.setdefault((lr['id'],int(lr['version'])),[]).append(sr)
        items={}; disclosures=[]; provenance=[]
        for lr in lock.get('layers',[]):
            layer=self._object(lr,'LAYER'); content=layer.get('content') or {}; ctype=content.get('type')
            segref=content.get('segment_ref')
            if segref:
                seg=self._object(segref,'SEGMENT'); asset=self._object(seg.get('asset_ref'),'ASSET'); source=self._object(asset.get('source_ref'),'SOURCE')
                aid=(asset['id'],int(asset['version']))
                rec=items.setdefault(aid,{'asset_ref':_obj_ref(asset),'segment_refs':[],'usage':{'shots':[]},'rights_status':(asset.get('rights') or {}).get('status')})
                if segref not in rec['segment_refs']:rec['segment_refs'].append(deepcopy(segref))
                for sr in layer_to_shots.get((lr['id'],int(lr['version'])),[]):
                    if sr not in rec['usage']['shots']:rec['usage']['shots'].append(deepcopy(sr))
                provenance.append({'kind':'MEDIA_LINEAGE','layer_ref':deepcopy(lr),'segment_ref':deepcopy(segref),'asset_ref':_obj_ref(asset),'source_ref':_obj_ref(source),'rights_status':(asset.get('rights') or {}).get('status')})
            elif ctype=='SOURCE_LABEL' and content.get('source_ref'):
                src=self._object(content['source_ref'],'SOURCE');provenance.append({'kind':'SOURCE_LABEL','layer_ref':deepcopy(lr),'source_ref':_obj_ref(src)})
            elif ctype=='THREE_D':
                disclosures.append({'kind':'THREE_D_RECONSTRUCTION','layer_ref':deepcopy(lr),'evidence_basis':deepcopy(content.get('evidence_basis') or []),'known':deepcopy(content.get('known') or []),'unknown':deepcopy(content.get('unknown') or []),'restrictions':deepcopy(content.get('restrictions') or [])})
            elif ctype=='GRAPHIC_PRIMITIVE':
                disclosures.append({'kind':'PROCEDURAL_GRAPHIC','layer_ref':deepcopy(lr),'statement':'Explanatory graphic; not documentary evidence.'})
        # Voice provenance comes from exact child scene locks.
        for slr in lock.get('scene_locks',[]):
            sl=self._artifact(slr,'PRODUCTION_LOCK_MANIFEST'); vlr=sl.get('voice_lock')
            if vlr:
                vl=self._artifact(vlr,'VOICE_LOCK_MANIFEST'); provenance.append({'kind':'VOICE_LINEAGE','scene_lock_ref':deepcopy(slr),'voice_lock_ref':deepcopy(vlr),'master_voice_ref':deepcopy(vl.get('master_voice'))})
        return list(items.values()),provenance,disclosures

    def build_release_manifests(self,project_lock_ref):
        lock=self.assert_project_lock_ready(project_lock_ref); assets,entries,disclosures=self._locked_usage(lock)
        allowed=set((self.policy.get('rights') or {}).get('allowed_statuses') or ['CLEAR','COMMENTARY_REVIEW'])
        bad=[x for x in assets if x.get('rights_status') not in allowed]
        if bad:raise StateEngineError('RELEASE_RIGHTS_BLOCK','One or more locked Assets have unresolved/blocking rights status.',details=bad)
        if not entries and not disclosures:
            disclosures=[{'kind':'NO_EXTERNAL_VISUAL_ASSETS','statement':'Release contains no external visual Asset lineage in the frozen graph.'}]
        tx=self.engine.begin()
        fam=tx.create_artifact('FINAL_ASSET_MANIFEST',{'assets':assets},origin_refs=[project_lock_ref,*[x['asset_ref'] for x in assets]])
        prov=tx.create_artifact('PROVENANCE_MANIFEST',{'entries':entries,'disclosures':disclosures},origin_refs=[project_lock_ref,fam])
        tx.commit(); return {'final_asset_manifest':fam,'provenance_manifest':prov}

    def evaluate_delivery(self, *, master_output_ref, profile_id='GMK_YOUTUBE_4K', metadata=None):
        out=self._artifact(master_output_ref,'RENDER_OUTPUT'); profile,pref=self.load_delivery_profile(profile_id); tech=out.get('technical') or {}; findings=[]
        video=profile.get('video') or {}
        if video.get('width') and tech.get('width')!=video['width']:findings.append({'severity':'MAJOR','code':'DELIVERY_WIDTH_MISMATCH','description':f"Expected width {video['width']}, got {tech.get('width')}",'root_cause':{'state':'IDENTIFIED','category':'TECHNICAL_OUTPUT'}})
        if video.get('height') and tech.get('height')!=video['height']:findings.append({'severity':'MAJOR','code':'DELIVERY_HEIGHT_MISMATCH','description':f"Expected height {video['height']}, got {tech.get('height')}",'root_cause':{'state':'IDENTIFIED','category':'TECHNICAL_OUTPUT'}})
        allowed={str(x).lower() for x in video.get('allowed_codecs') or []}; codec=str(tech.get('codec','')).lower()
        if allowed and codec not in allowed:findings.append({'severity':'MAJOR','code':'DELIVERY_CODEC_INVALID','description':f'Codec {codec or "<missing>"} not allowed by profile.','root_cause':{'state':'IDENTIFIED','category':'TECHNICAL_OUTPUT'}})
        if float(tech.get('duration_seconds',0))<float(video.get('min_duration_seconds',0)):findings.append({'severity':'MAJOR','code':'DELIVERY_DURATION_INVALID','description':'Master output duration is below Delivery Profile minimum.','root_cause':{'state':'IDENTIFIED','category':'TECHNICAL_OUTPUT'}})
        md=metadata or {}; missing=[k for k in ((profile.get('metadata') or {}).get('required_fields') or []) if not str(md.get(k,'')).strip()]
        if missing:findings.append({'severity':'MAJOR','code':'DELIVERY_METADATA_MISSING','description':'Missing required delivery metadata: '+', '.join(missing),'root_cause':{'state':'IDENTIFIED','category':'TECHNICAL_OUTPUT'}})
        result=self.qa.evaluate(report_type='DELIVERY_QA',scope=master_output_ref,observed_artifact=master_output_ref,qa_profile=pref,findings=findings)
        return {**result,'delivery_profile_ref':pref,'profile':profile}

    def prepare_release(self, *, project_lock_ref, master_output_ref, full_film_qa_ref, profile_id='GMK_YOUTUBE_4K', metadata=None, extra_delivery_items=()):
        lock=self.assert_project_lock_ready(project_lock_ref); output=self._artifact(master_output_ref,'RENDER_OUTPUT')
        # Master output must have been rendered from this exact Project Lock.
        job=self._object(output.get('render_job_ref'),'RENDER_JOB')
        if job.get('production_lock')!=project_lock_ref:raise StateEngineError('RELEASE_MASTER_OUTPUT_LOCK_MISMATCH','Master output was not rendered from the exact Project Production Lock.')
        ff=self._object(full_film_qa_ref,'QA_REPORT')
        if ff.get('report_type')!='FULL_FILM_QA' or ff.get('result') not in {'PASS','WARN'}:raise StateEngineError('RELEASE_FULL_FILM_QA_INVALID','Release requires acceptable FULL_FILM_QA.')
        if ff.get('observed_artifact')!=master_output_ref:raise StateEngineError('RELEASE_FULL_FILM_QA_OUTPUT_MISMATCH','FULL_FILM_QA did not evaluate the release master output.')
        manifests=self.build_release_manifests(project_lock_ref)
        dq=self.evaluate_delivery(master_output_ref=master_output_ref,profile_id=profile_id,metadata=metadata)
        if dq['result']=='FAIL':raise StateEngineError('RELEASE_DELIVERY_QA_INVALID','Delivery QA failed; Release cannot proceed.',details=dq['report_ref'])
        items=[deepcopy(master_output_ref),deepcopy(manifests['final_asset_manifest']),deepcopy(manifests['provenance_manifest']),*deepcopy(list(extra_delivery_items))]
        tx=self.engine.begin(); package=tx.create_artifact('DELIVERY_PACKAGE',{'items':items},origin_refs=[project_lock_ref,*items,full_film_qa_ref,dq['report_ref']]);tx.commit()
        cp=self.checkpoints.create_checkpoint(checkpoint_class='PRE_RELEASE',reason='Pre-release recovery baseline before external publish.',important_artifact_refs=[project_lock_ref,master_output_ref,manifests['final_asset_manifest'],manifests['provenance_manifest'],package])
        return {'project_lock':deepcopy(project_lock_ref),'master_output':deepcopy(master_output_ref),'full_film_qa':deepcopy(full_film_qa_ref),'delivery_qa':dq['report_ref'],'delivery_profile':dq['delivery_profile_ref'],'final_asset_manifest':manifests['final_asset_manifest'],'provenance_manifest':manifests['provenance_manifest'],'delivery_package':package,'pre_release_checkpoint':cp,'metadata':deepcopy(metadata or {})}

    def publish(self, candidate:dict[str,Any], *, executor:Callable[[dict[str,Any]],OperationExecutionResult], provider='GMK_DELIVERY_ADAPTER', destination='PRIMARY', release_label='v1', human_confirmed=True, supersedes_release_ref=None)->PublishResult:
        self.assert_project_lock_ready(candidate['project_lock']); self._artifact(candidate['delivery_package'],'DELIVERY_PACKAGE')
        idem='PUBLISH_'+sha256_json({'package':candidate['delivery_package'],'destination':destination})[:32].upper()
        plan=self.ops.plan(operation_type='PUBLISH',subject=candidate['delivery_package'],provider=provider,action='PUBLISH_DELIVERY_PACKAGE',input_fingerprint=sha256_json(candidate['delivery_package']),idempotency_key=idem,destination=destination,human_confirmed=human_confirmed,checkpoint_ref=candidate['pre_release_checkpoint'])
        executed=self.ops.execute(plan['operation_ref'],executor); state=executed['workflow_state']
        allowed=set((self.policy.get('operation') or {}).get('required_success_states') or ['SUCCEEDED','PARTIALLY_SUCCEEDED'])
        if state not in allowed:raise StateEngineError('RELEASE_OPERATION_INCOMPLETE',f'Publish operation ended in {state}.',details=executed)
        opref=executed['operation_ref']; lock=self._artifact(candidate['project_lock']); project_ref=(lock.get('scope') or {}).get('project_ref')
        # Idempotent publish replay must not create a second immutable RELEASE for
        # the same terminal external operation.
        state=self.engine.snapshot(); idx=global_index(state.registries)
        for oid,rid in idx.items():
            entry=state.registries[rid].entries[oid]
            if entry.object_type!='RELEASE' or entry.active_version is None: continue
            existing=state.objects.get((oid,int(entry.active_version)))
            if existing and existing.get('state')=='RELEASED' and existing.get('release_operation_ref')==opref:
                return PublishResult(_obj_ref(existing),opref,None)
        payload={'project_ref':deepcopy(project_ref),'release_label':release_label,'production_lock':deepcopy(candidate['project_lock']),'master_output':deepcopy(candidate['master_output']),'delivery_profile':deepcopy(candidate['delivery_profile']),'final_asset_manifest':deepcopy(candidate['final_asset_manifest']),'provenance_manifest':deepcopy(candidate['provenance_manifest']),'qa_reports':[deepcopy(candidate['full_film_qa']),deepcopy(candidate['delivery_qa'])],'release_operation_ref':deepcopy(opref),'state':'RELEASED','released_at':self.engine.now()}
        if supersedes_release_ref is not None:payload['supersedes_release_ref']=deepcopy(supersedes_release_ref)
        tx=self.engine.begin(); rr=tx.create_object('RELEASE',payload,activate=True);tx.commit();return PublishResult(rr,opref,None)

    def finalize_project(self, release_ref, *, important_artifact_refs=()):
        rel=self._object(release_ref,'RELEASE')
        if rel.get('state')!='RELEASED':raise StateEngineError('PROJECT_COMPLETION_RELEASE_INVALID','Finalization requires RELEASED Release.')
        # Completion replay is safe: once PROJECT_COMPLETED is current, return the
        # existing valid FINAL_PROJECT checkpoint instead of creating another.
        if self.engine.project_state=='PROJECT_COMPLETED':
            state=self.engine.snapshot(); idx=global_index(state.registries); cps=[]
            for oid,rid in idx.items():
                entry=state.registries[rid].entries[oid]
                if entry.object_type!='CHECKPOINT' or entry.active_version is None: continue
                cpobj=state.objects.get((oid,int(entry.active_version)))
                if cpobj and cpobj.get('checkpoint_class')=='FINAL_PROJECT' and cpobj.get('integrity_summary')=='PASS': cps.append(cpobj)
            if not cps: raise StateEngineError('PROJECT_COMPLETION_CHECKPOINT_MISSING','PROJECT_COMPLETED has no valid FINAL_PROJECT Checkpoint.')
            cpobj=sorted(cps,key=lambda x:(str(x.get('created_at') or ''),x['id']))[-1]
            return {'release_ref':deepcopy(release_ref),'final_checkpoint_ref':_obj_ref(cpobj),'project_state':self.engine.project_state}
        if self.engine.project_state!='DELIVERY_READY':raise StateEngineError('PROJECT_COMPLETION_STATE_INVALID',f'Project must be DELIVERY_READY before completion, current={self.engine.project_state}.')
        refs=[deepcopy(rel['production_lock']),deepcopy(rel['master_output']),deepcopy(rel['final_asset_manifest']),deepcopy(rel['provenance_manifest']),*deepcopy(list(important_artifact_refs))]
        cp=self.checkpoints.create_checkpoint(checkpoint_class='FINAL_PROJECT',reason='Final project closeout checkpoint after successful Release.',important_artifact_refs=refs)
        tx=self.engine.begin();tx.transition_project_state('PROJECT_COMPLETED',actor_type='SYSTEM');tx.commit()
        return {'release_ref':deepcopy(release_ref),'final_checkpoint_ref':cp,'project_state':self.engine.project_state}
