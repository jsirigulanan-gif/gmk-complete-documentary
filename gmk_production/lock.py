from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any
import hashlib, yaml
from gmk_state.errors import StateEngineError
from gmk_state.registry import global_index
from gmk_semantics.model import sha256_json
from gmk_dependency import NodeKey, NodeKind


def art_ref(a):
    return {'artifact_id':a['artifact_id'],'artifact_type':a['artifact_type'],'version':int(a['version']),'sha256':a['sha256']}

def obj_ref(o): return {'id':o['id'],'version':int(o['version'])}

class ProductionLockRuntime:
    def __init__(self, engine):
        self.engine=engine
        p=Path(engine.root)/'config'/'gmk_policy_bundle.yaml'
        self.policy_bundle=yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        self.policy_bundle_ref={'config_id':self.policy_bundle['config_id'],'version':str(self.policy_bundle['version']),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

    def _resolve_obj(self,ref):
        o=self.engine.snapshot().objects.get((ref.get('id'),int(ref.get('version',0))))
        if not o: raise StateEngineError('PRODUCTION_LOCK_OBJECT_MISSING',f"Missing exact object {ref}")
        if o.get('status') in {'STALE','BLOCKED','REJECTED'} or (o.get('stale') or {}).get('is_stale'):
            raise StateEngineError('PRODUCTION_LOCK_OBJECT_INELIGIBLE',f"{o['id']}@{o['version']} is not production eligible.")
        return o

    def _resolve_art(self,ref):
        a=self.engine.snapshot().artifacts.get((ref.get('artifact_id'),int(ref.get('version',0))))
        if not a or a.get('sha256')!=ref.get('sha256'): raise StateEngineError('PRODUCTION_LOCK_ARTIFACT_MISSING','Artifact ref missing or hash mismatch.',details=ref)
        return a

    def _approved(self, cls, target):
        s=self.engine.snapshot(); idx=global_index(s.registries)
        for oid,rid in idx.items():
            e=s.registries[rid].entries[oid]
            if e.object_type!='APPROVAL' or e.active_version is None: continue
            a=s.objects.get((oid,int(e.active_version)))
            if not a or a.get('decision')!='APPROVED' or a.get('approval_class')!=cls: continue
            if a.get('status') in {'STALE','BLOCKED','REJECTED'} or (a.get('stale') or {}).get('is_stale'): continue
            if a.get('target')==target:return a
        return None

    def assert_valid(self, lock_ref):
        a=self._resolve_art(lock_ref)
        if a.get('artifact_type')!='PRODUCTION_LOCK_MANIFEST': raise StateEngineError('PRODUCTION_LOCK_TYPE_INVALID','Expected PRODUCTION_LOCK_MANIFEST.')
        s=self.engine.snapshot(); key=NodeKey(NodeKind.ARTIFACT,a['artifact_id'],int(a['version']))
        inv=s.dependency_invalidations.get(key)
        if inv: raise StateEngineError('PRODUCTION_LOCK_STALE','Production Lock has unresolved dependency invalidation.',details=deepcopy(inv))
        return a

    def create_scene_lock(self, *, voice_lock_ref, design_dna_ref, scene_plan_ref, scene_preview_ref, shot_refs=None, extensions=None, artifact_id=None):
        voice=self._resolve_art(voice_lock_ref); plan=self._resolve_art(scene_plan_ref); preview=self._resolve_art(scene_preview_ref); dna=self._resolve_obj(design_dna_ref)
        if voice.get('artifact_type')!='VOICE_LOCK_MANIFEST' or plan.get('artifact_type')!='SCENE_PLAN' or preview.get('artifact_type')!='SCENE_PREVIEW' or dna.get('object_type')!='DESIGN_DNA':
            raise StateEngineError('PRODUCTION_LOCK_INPUT_TYPE_INVALID','Production Lock inputs have invalid types.')
        refs=shot_refs or [x.get('shot_ref',x) for x in plan.get('shots',[]) if isinstance(x,dict)]
        shots=[self._resolve_obj(r) for r in refs]
        if not shots: raise StateEngineError('PRODUCTION_LOCK_SHOTS_REQUIRED','Scene Production Lock requires at least one Shot.')
        layers=[];cues=[]; seen_l=set();seen_c=set()
        for shot in shots:
            if shot.get('object_type')!='SHOT':raise StateEngineError('PRODUCTION_LOCK_SHOT_TYPE_INVALID','Shot refs must point to SHOT.')
            for r in shot.get('layer_refs',[]):
                key=(r['id'],int(r['version']))
                if key not in seen_l: layers.append(self._resolve_obj(r));seen_l.add(key)
            for r in shot.get('cue_refs',[]):
                key=(r['id'],int(r['version']))
                if key not in seen_c: cues.append(self._resolve_obj(r));seen_c.add(key)
        required=[('VOICE',voice_lock_ref),('DESIGN_DNA',design_dna_ref),('SCENE_PREVIEW',scene_preview_ref)]
        for shot in shots:
            if (shot.get('review_class') or {}).get('value') in {'STANDARD','CRITICAL'}:required.append(('SHOT_VISUAL',obj_ref(shot)))
        approvals=[]
        for cls,target in required:
            a=self._approved(cls,target)
            if not a:raise StateEngineError('PRODUCTION_APPROVAL_MISSING',f'Missing current {cls} approval.',details=target)
            approvals.append(a)
        snapshot={'voice_lock':voice_lock_ref,'design_dna':design_dna_ref,'scene_plan':scene_plan_ref,'scene_preview':scene_preview_ref,'shots':[obj_ref(x) for x in shots],'layers':[obj_ref(x) for x in layers],'cues':[obj_ref(x) for x in cues],'approvals':[obj_ref(x) for x in approvals]}
        payload={'scope':{'type':'SCENE','scene_ref':deepcopy(preview['scene_ref'])},'system':{'schema_version':'1.0.0','policy_bundle':deepcopy(self.policy_bundle_ref)},'voice_lock':deepcopy(voice_lock_ref),'design_dna_ref':deepcopy(design_dna_ref),'scene_plan':deepcopy(scene_plan_ref),'scene_preview':deepcopy(scene_preview_ref),'shots':snapshot['shots'],'layers':snapshot['layers'],'cues':snapshot['cues'],'approvals':snapshot['approvals'],'dependency_snapshot_sha256':sha256_json(snapshot)}
        if extensions: payload['extensions']=deepcopy(extensions)
        tx=self.engine.begin();origins=[voice_lock_ref,design_dna_ref,scene_plan_ref,scene_preview_ref]
        if artifact_id:
            old=self.engine.snapshot().artifact_registry.entries[artifact_id]
            ref=tx.create_artifact_version(artifact_id,base_version=old.head_version,payload_patch=payload,origin_refs=origins)
        else: ref=tx.create_artifact('PRODUCTION_LOCK_MANIFEST',payload,origin_refs=origins)
        tx.commit();return ref
    def create_project_lock(self, *, scene_lock_refs, extensions=None, artifact_id=None):
        """Freeze a project render graph by aggregating exact approved scene locks.

        The project lock never re-resolves live SHOT/LAYER/CUE state; it copies the
        exact frozen refs already present in child scene locks.
        """
        refs=list(scene_lock_refs or [])
        if not refs:
            raise StateEngineError('PROJECT_PRODUCTION_LOCK_SCENES_REQUIRED','Project Production Lock requires at least one Scene Production Lock.')
        locks=[]
        for ref in refs:
            lock=self.assert_valid(ref)
            if (lock.get('scope') or {}).get('type')!='SCENE':
                raise StateEngineError('PROJECT_PRODUCTION_LOCK_CHILD_TYPE_INVALID','Project Production Lock may aggregate only SCENE Production Locks.',details=ref)
            locks.append(lock)
        state=self.engine.snapshot(); idx=global_index(state.registries)
        projects=[]
        for oid,rid in idx.items():
            e=state.registries[rid].entries[oid]
            if e.object_type=='PROJECT' and e.active_version is not None:
                o=state.objects.get((oid,int(e.active_version)))
                if o: projects.append(o)
        if len(projects)!=1:
            raise StateEngineError('PROJECT_PRODUCTION_LOCK_PROJECT_INVALID','Project Production Lock requires exactly one ACTIVE PROJECT.')
        project=projects[0]
        def dedupe(field):
            seen=set(); out=[]
            for lock in locks:
                for r in lock.get(field,[]):
                    key=(r.get('id'),int(r.get('version',0)))
                    if key not in seen: seen.add(key); out.append(deepcopy(r))
            return out
        shots=dedupe('shots'); layers=dedupe('layers'); cues=dedupe('cues'); approvals=dedupe('approvals')
        child_refs=[art_ref(x) for x in locks]
        snapshot={'scene_locks':child_refs,'shots':shots,'layers':layers,'cues':cues,'approvals':approvals}
        payload={
            'scope':{'type':'PROJECT','project_ref':obj_ref(project)},
            'system':{'schema_version':'1.0.0','policy_bundle':deepcopy(self.policy_bundle_ref)},
            'scene_locks':child_refs,'shots':shots,'layers':layers,'cues':cues,'approvals':approvals,
            'dependency_snapshot_sha256':sha256_json(snapshot),
        }
        if extensions: payload['extensions']=deepcopy(extensions)
        tx=self.engine.begin()
        if artifact_id:
            old=state.artifact_registry.entries[artifact_id]
            ref=tx.create_artifact_version(artifact_id,base_version=old.head_version,payload_patch=payload,origin_refs=child_refs)
        else: ref=tx.create_artifact('PRODUCTION_LOCK_MANIFEST',payload,origin_refs=child_refs)
        tx.commit();return ref
