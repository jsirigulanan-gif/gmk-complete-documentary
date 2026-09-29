from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any
import hashlib
import yaml

from gmk_state.constants import STANDARD_REGISTRY_IDS
from gmk_state.artifact_registry import ARTIFACT_REGISTRY_ID
from gmk_state.registry import global_index


class ManifestBuildError(RuntimeError):
    pass


def _artifact_ref(a: dict[str, Any]) -> dict[str, Any]:
    return {
        'artifact_id': a['artifact_id'], 'artifact_type': a['artifact_type'],
        'version': int(a['version']), 'sha256': a['sha256']
    }


def _object_ref(o: dict[str, Any]) -> dict[str, Any]:
    return {'id': o['id'], 'version': int(o['version'])}


class ProjectManifestBuilder:
    """Compile the live RuntimeState into the frozen Project Manifest contract.

    The manifest is intentionally a resume pointer, not a database. It pins exact
    registry snapshots and selected current project-level artifacts/objects.
    """
    CURRENT_ARTIFACT_TYPES = {
        'narrative_spine': 'NARRATIVE_SPINE',
        'voiceover_script': 'VOICEOVER_SCRIPT_FINAL',
        'tts_script': 'TTS_READY_SCRIPT',
        'master_voice': 'MASTER_VOICE',
    }

    def __init__(self, schema_root: Path, *, master_spec_id: str='GMK_MASTER_SPEC_V2', master_checkpoint_id: str='GMK_PIPELINE_V2_CHECKPOINT_002', environment_mode: str='PRODUCTION'):
        self.schema_root = Path(schema_root)
        self.master_spec_id = master_spec_id
        self.master_checkpoint_id = master_checkpoint_id
        self.environment_mode = environment_mode
        self.policy_bundle_path = self.schema_root/'config'/'gmk_policy_bundle.yaml'
        self.policy_bundle = yaml.safe_load(self.policy_bundle_path.read_text(encoding='utf-8')) or {}

    def policy_bundle_ref(self) -> dict[str, Any]:
        return {
            'config_id': str(self.policy_bundle['config_id']),
            'version': str(self.policy_bundle['version']),
            'sha256': hashlib.sha256(self.policy_bundle_path.read_bytes()).hexdigest(),
        }

    @staticmethod
    def _active_object(state, object_type: str) -> dict[str, Any] | None:
        idx = global_index(state.registries)
        candidates=[]
        for oid,rid in idx.items():
            e=state.registries[rid].entries[oid]
            if e.object_type!=object_type or e.active_version is None: continue
            obj=state.objects.get((oid,int(e.active_version)))
            if obj:candidates.append(obj)
        if not candidates:return None
        return sorted(candidates,key=lambda o:(o.get('created_at',''),o['id']))[-1]

    @staticmethod
    def _artifact_head(state, artifact_type: str) -> dict[str, Any] | None:
        candidates=[]
        for entry in state.artifact_registry.entries.values():
            if entry.artifact_type!=artifact_type:continue
            a=state.artifacts.get((entry.artifact_id,int(entry.head_version)))
            if a:candidates.append(a)
        if not candidates:return None
        return sorted(candidates,key=lambda a:(a.get('created_at',''),a['artifact_id']))[-1]

    def _project(self,state):
        p=self._active_object(state,'PROJECT')
        if p is None:raise ManifestBuildError('PROJECT_MANIFEST_PROJECT_MISSING: no ACTIVE PROJECT exists.')
        return p

    def _registry_pointers(self,state):
        out={}
        missing=[]
        for rid in STANDARD_REGISTRY_IDS:
            reg=state.registries.get(rid)
            if reg is None:missing.append(rid);continue
            out[rid]={'id':rid,'version':int(reg.version),'uri':f'gmk://registries/{rid}/v{int(reg.version)}','sha256':reg.sha256}
        if missing:raise ManifestBuildError('REGISTRY_MISSING: '+', '.join(missing))
        ar=state.artifact_registry
        out[ARTIFACT_REGISTRY_ID]={'id':ARTIFACT_REGISTRY_ID,'version':int(ar.version),'uri':f'gmk://registries/{ARTIFACT_REGISTRY_ID}/v{int(ar.version)}','sha256':ar.sha256}
        return out

    def _current(self,state):
        out={}
        for field,typ in self.CURRENT_ARTIFACT_TYPES.items():
            a=self._artifact_head(state,typ)
            if a:out[field]=_artifact_ref(a)
        dna=self._active_object(state,'DESIGN_DNA')
        if dna:out['design_dna']=_object_ref(dna)
        cp=self._active_object(state,'CHECKPOINT')
        if cp:out['latest_checkpoint']=_object_ref(cp)
        releases=[]
        idx=global_index(state.registries)
        for oid,rid in idx.items():
            e=state.registries[rid].entries[oid]
            if e.object_type!='RELEASE' or e.active_version is None:continue
            r=state.objects.get((oid,int(e.active_version)))
            if r and r.get('state')=='RELEASED':releases.append(r)
        if releases:
            r=sorted(releases,key=lambda x:(x.get('released_at',''),x.get('created_at',''),x['id']))[-1]
            out['current_release']=_object_ref(r)
        return out

    def _gate_summaries(self,state):
        latest={}
        for ev in state.gate_evaluations:
            if not ev.get('evidence'): continue  # schema requires concrete evidence in a persisted summary
            latest[ev['gate_id']]=ev
        out=[]
        for gid,ev in sorted(latest.items()):
            out.append({
                'gate_id':gid,'result':ev['result'],'evidence':deepcopy(ev.get('evidence') or []),
                'warning_codes':list(ev.get('warning_codes') or []),'blocker_refs':list(ev.get('blocker_refs') or []),
                'evaluated_at':ev['evaluated_at'],
            })
        return out

    def _blockers(self,state,gate_engine,timestamp):
        found={}
        # Manifest carries current project blockers across all gate scopes, deduplicated.
        for gid in gate_engine.policy.gates:
            for b in gate_engine.derive_blockers(state,gate_id=gid):found[b.blocker_id]=b
        for b in gate_engine.derive_blockers(state,action_id='TRANSITION_PROJECT_STATE'):found[b.blocker_id]=b
        out=[]
        for bid,b in sorted(found.items()):
            rec={'blocker_id':bid,'code':b.code,'severity':b.severity,'state':'OPEN','message':b.message,'opened_at':timestamp}
            if b.target is not None:rec['target']=deepcopy(b.target)
            if b.source_ref is not None and 'id' in b.source_ref:rec['source_issue_ref']=deepcopy(b.source_ref)
            out.append(rec)
        return out

    def build(self,state,gate_engine) -> dict[str, Any]:
        project=self._project(state)
        timestamp=(state.audit_log[-1].committed_at if state.audit_log else state.project_state_entered_at or project.get('created_at'))
        created_at=project.get('created_at') or timestamp
        manifest_id=f"MANIFEST_{project['id']}"
        env=self.environment_mode
        if state.safety_mode=='READ_ONLY':env='READ_ONLY'
        elif state.safety_mode!='NORMAL':env='SAFE_MODE'
        manifest={
            'schema_header':{'schema_id':'gmk://schema/v1/project-manifest','schema_version':'1.0.0'},
            'manifest_id':manifest_id,'manifest_version':int(state.manifest_version),
            'project_ref':_object_ref(project),
            'system':{
                'master_spec_id':self.master_spec_id,'master_checkpoint_id':self.master_checkpoint_id,
                'schema_version':'1.0.0','policy_bundle_ref':self.policy_bundle_ref(),
            },
            'project_state':{'current':state.project_state,'entered_at':state.project_state_entered_at or timestamp},
            'registries':self._registry_pointers(state),'current':self._current(state),
            'gates':self._gate_summaries(state),'blockers':self._blockers(state,gate_engine,timestamp),
            'environment':{'mode':env},'created_at':created_at,'updated_at':timestamp,
        }
        if state.manifest_version>1:manifest['supersedes_manifest_version']=int(state.manifest_version)-1
        research_pack=self._artifact_head(state,'RESEARCH_PACK')
        if research_pack:manifest['bootstrap_inputs']={'research_pack':_artifact_ref(research_pack)}
        return manifest
