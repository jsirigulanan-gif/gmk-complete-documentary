from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Protocol
import hashlib
from gmk_state.errors import StateEngineError
from gmk_state.registry import global_index
from gmk_semantics.model import sha256_json
from gmk_production.lock import ProductionLockRuntime, art_ref

class TransientRenderError(RuntimeError): pass

@dataclass(frozen=True)
class RenderProduct:
    media_uri:str
    media_bytes:bytes
    media_type:str='VIDEO'
    technical:dict[str,Any]|None=None

class RenderAdapter(Protocol):
    def render(self, compiled_payload:dict[str,Any], input_snapshot:dict[str,Any], *, attempt:int)->RenderProduct: ...

class RenderRuntime:
    def __init__(self,engine):self.engine=engine;self.locks=ProductionLockRuntime(engine)
    def _head(self,oid):
        o=self.engine.resolver().resolve(oid,mode='HEAD')
        if not o:raise StateEngineError('RENDER_JOB_NOT_FOUND',f'{oid} not found.')
        return o
    def _artifact(self,ref):
        a=self.engine.snapshot().artifacts.get((ref['artifact_id'],int(ref['version'])))
        if not a or a.get('sha256')!=ref.get('sha256'):raise StateEngineError('RENDER_ARTIFACT_REF_INVALID','Artifact ref/hash invalid.',details=ref)
        return a
    def queue_final(self, *, production_lock_ref, scope_type='SCENE', scope_target=None, renderer_adapter=None, output_profile=None, compiled_payload=None, transient_retry_limit=2, compiler=None, extensions=None):
        lock=self.locks.assert_valid(production_lock_ref)
        renderer_adapter=renderer_adapter or {'config_id':'GMK_TEST_RENDERER','version':'1.0.0','sha256':'a'*64}
        output_profile=output_profile or {'config_id':'GMK_MASTER_4K','version':'1.0.0','sha256':'b'*64}
        prompt_payload={'production_lock':deepcopy(production_lock_ref),'renderer_adapter':deepcopy(renderer_adapter),'compiled_payload':deepcopy(compiled_payload or {'mode':'EXECUTE_LOCKED_DECISIONS'})}
        if extensions: prompt_payload['extensions']=deepcopy(extensions)
        tx=self.engine.begin();prompt_ref=tx.create_artifact('RENDERER_PROMPT',prompt_payload,origin_refs=[production_lock_ref],compiler=compiler or {'config_id':'GMK_RENDERER_PROMPT_COMPILER','version':'1.0.0','sha256':'c'*64})
        inputs=[]
        for f in ('shots','layers','cues'):inputs.extend(deepcopy(lock.get(f,[])))
        snap={'production_lock':production_lock_ref,'inputs':inputs,'renderer_adapter':renderer_adapter,'output_profile':output_profile,'compiled_payload':deepcopy(compiled_payload or {'mode':'EXECUTE_LOCKED_DECISIONS'})}
        render_key=sha256_json(snap)
        target=scope_target or (lock.get('scope') or {}).get('scene_ref') or lock['shots'][0]
        payload={'render_level':'FINAL','scope':{'type':scope_type,'target':deepcopy(target)},'production_lock':deepcopy(production_lock_ref),'input_snapshot':{'snapshot_sha256':sha256_json(inputs),'inputs':inputs},'renderer':{'adapter_id':renderer_adapter['config_id'],'adapter_version':renderer_adapter['version']},'renderer_prompt':prompt_ref,'output_profile':deepcopy(output_profile),'cost_class':'HIGH','workflow_state':'QUEUED','execution_policy':{'transient_retry_limit':min(2,int(transient_retry_limit))},'extensions':{'render_key_sha256':render_key}}
        if extensions:
            payload['extensions'].update(deepcopy(extensions))
        job_ref=tx.create_object('RENDER_JOB',payload,activate=True);tx.commit();return job_ref
    def _cache_manifest(self,job):
        s=self.engine.snapshot();key=(job.get('extensions') or {}).get('render_key_sha256')
        if not key:return None
        for o in s.objects.values():
            if o.get('object_type')!='RENDER_MANIFEST' or o.get('outcome')!='SUCCESS' or (o.get('technical_validation') or {}).get('state')!='PASS':continue
            src=s.objects.get((o['render_job_ref']['id'],int(o['render_job_ref']['version'])))
            if src and (src.get('extensions') or {}).get('render_key_sha256')==key and o.get('outputs'):return o
        return None
    def execute(self, job_ref, adapter:RenderAdapter):
        cur=self._head(job_ref['id'])
        if cur.get('workflow_state') not in {'QUEUED','FAILED'}:raise StateEngineError('RENDER_EXECUTION_STATE_INVALID',f"Cannot execute from {cur.get('workflow_state')}")
        lock_ref=cur.get('production_lock');self.locks.assert_valid(lock_ref)
        cached=self._cache_manifest(cur)
        tx=self.engine.begin();runref=tx.create_version(cur['id'],base_version=cur['version'],patch={'workflow_state':'RUNNING'});tx.promote_active_version(cur['id'],runref['version'],confirm_locked_impact=True);tx.commit();running=self._head(cur['id'])
        if cached:
            tx=self.engine.begin();done=tx.create_version(running['id'],base_version=running['version'],patch={'workflow_state':'SUCCEEDED'});tx.promote_active_version(running['id'],done['version'],confirm_locked_impact=True)
            m=tx.create_object('RENDER_MANIFEST',{'render_job_ref':done,'execution':{'attempt':1,'mode':'CACHE_HIT','started_at':self.engine.now(),'finished_at':self.engine.now(),'cache_source':{'id':cached['id'],'version':cached['version']}},'outcome':'SUCCESS','inputs_snapshot_sha256':running['input_snapshot']['snapshot_sha256'],'outputs':deepcopy(cached['outputs']),'technical_validation':{'state':'PASS'}},activate=True);tx.commit();return {'job_ref':done,'manifest_ref':m,'cache_hit':True}
        prompt=self._artifact(running['renderer_prompt'])
        limit=(running.get('execution_policy') or {}).get('transient_retry_limit',2);last=None;attempt=0
        for attempt in range(1,int(limit)+2):
            try:
                product=adapter.render(deepcopy(prompt.get('compiled_payload') or {}),deepcopy(running['input_snapshot']),attempt=attempt);last=None;break
            except TransientRenderError as exc:last=exc;continue
        if last is not None:
            tx=self.engine.begin();failed=tx.create_version(running['id'],base_version=running['version'],patch={'workflow_state':'FAILED'});tx.promote_active_version(running['id'],failed['version'],confirm_locked_impact=True);m=tx.create_object('RENDER_MANIFEST',{'render_job_ref':failed,'execution':{'attempt':attempt,'mode':'EXECUTED','started_at':self.engine.now(),'finished_at':self.engine.now()},'outcome':'FAILED','inputs_snapshot_sha256':running['input_snapshot']['snapshot_sha256'],'outputs':[],'technical_validation':{'state':'FAIL'}},activate=True);tx.commit();return {'job_ref':failed,'manifest_ref':m,'cache_hit':False,'failed':True}
        tech=deepcopy(product.technical or {});technical_ok=(tech.get('width',1)>0 and tech.get('height',1)>0 and tech.get('duration_seconds',0)>=0)
        tx=self.engine.begin();done=tx.create_version(running['id'],base_version=running['version'],patch={'workflow_state':'SUCCEEDED' if technical_ok else 'FAILED'});tx.promote_active_version(running['id'],done['version'],confirm_locked_impact=True)
        media_hash=hashlib.sha256(product.media_bytes).hexdigest();render_key=(running.get('extensions') or {}).get('render_key_sha256') or sha256_json(running['input_snapshot'])
        outref=tx.create_artifact('RENDER_OUTPUT',{'render_job_ref':done,'media_uri':product.media_uri,'media_sha256':media_hash,'media_type':product.media_type,'technical':tech,'render_key_sha256':render_key},origin_refs=[done,running['production_lock']])
        manifest=tx.create_object('RENDER_MANIFEST',{'render_job_ref':done,'execution':{'attempt':attempt,'mode':'EXECUTED','started_at':self.engine.now(),'finished_at':self.engine.now()},'outcome':'SUCCESS' if technical_ok else 'FAILED','inputs_snapshot_sha256':running['input_snapshot']['snapshot_sha256'],'outputs':[outref],'technical_validation':{'state':'PASS' if technical_ok else 'FAIL'}},activate=True);tx.commit();return {'job_ref':done,'manifest_ref':manifest,'output_ref':outref,'cache_hit':False,'failed':not technical_ok}
