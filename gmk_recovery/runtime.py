from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any

from gmk_semantics.model import sha256_json
from gmk_state.errors import StateEngineError
from gmk_state.models import RegistrySnapshot, ActionAudit
from gmk_state.artifact_registry import ArtifactRegistrySnapshot, ARTIFACT_REGISTRY_ID
from gmk_state.registry import global_index, locator_for
from gmk_runtime.manifest import ProjectManifestBuilder
from gmk_runtime.persistence import RuntimeStore

PRESERVE_LIVE_REGISTRIES={"CHECKPOINT_REGISTRY","OPERATION_REGISTRY","INCIDENT_REGISTRY","RELEASE_REGISTRY"}
MANAGED_ARTIFACT_FIELDS={"schema_header","artifact_id","artifact_type","version","supersedes_version","uri","sha256","created_at"}

class CheckpointRuntime:
    """Checkpoint/restore implementation for frozen GMK v1.

    Checkpoints capture a pre-checkpoint Manifest plus immutable Registry snapshot
    bundle. Restore creates a new current state; it never deletes later versions or
    rewrites released/external truth.
    """
    def __init__(self, engine, *, workspace:Path|None=None):
        self.engine=engine
        self.workspace=Path(workspace) if workspace is not None else None
        self.builder=ProjectManifestBuilder(engine.root)

    @staticmethod
    def _obj(state,ref):
        return state.objects.get((ref.get("id"),int(ref.get("version",0)))) if ref else None
    @staticmethod
    def _art(state,ref):
        return state.artifacts.get((ref.get("artifact_id"),int(ref.get("version",0)))) if ref else None

    def create_checkpoint(self, *, checkpoint_class:str="PROJECT_STATE", reason:str, important_artifact_refs=()) -> dict[str,Any]:
        state=self.engine.snapshot()
        baseline_manifest=self.builder.build(state,self.engine.gates)
        mhash=sha256_json(baseline_manifest)
        registries={rid:reg.to_dict() for rid,reg in state.registries.items()}
        registries[ARTIFACT_REGISTRY_ID]=state.artifact_registry.to_dict()
        rhashes={rid:data["sha256"] for rid,data in registries.items()}

        tx=self.engine.begin(recovery=True)
        ms=tx.create_artifact("PROJECT_MANIFEST_SNAPSHOT",{
            "manifest":deepcopy(baseline_manifest),"manifest_sha256":mhash,
        },origin_refs=[baseline_manifest["project_ref"]])
        rb=tx.create_artifact("REGISTRY_SNAPSHOT_BUNDLE",{
            "registries":deepcopy(registries),"registry_hashes":deepcopy(rhashes),
        },origin_refs=[ms])
        payload={
            "checkpoint_class":checkpoint_class,
            "project_ref":deepcopy(baseline_manifest["project_ref"]),
            "manifest_snapshot":deepcopy(ms),
            "system_pins":{
                "schema_version":baseline_manifest["system"]["schema_version"],
                "policy_bundle_ref":deepcopy(baseline_manifest["system"]["policy_bundle_ref"]),
            },
            "registry_snapshots":[deepcopy(rb)],
            "important_artifact_refs":deepcopy(list(important_artifact_refs)),
            "reason":reason,
            "integrity_summary":"PASS",
        }
        ref=tx.create_object("CHECKPOINT",payload,activate=True)
        tx.commit()
        if self.workspace is not None:RuntimeStore(self.engine.root,self.workspace).persist(self.engine)
        return ref

    def verify_checkpoint(self, checkpoint_ref:dict[str,Any]) -> dict[str,Any]:
        state=self.engine.snapshot();cp=self._obj(state,checkpoint_ref)
        if not cp or cp.get("object_type")!="CHECKPOINT":
            raise StateEngineError("CHECKPOINT_NOT_FOUND","Checkpoint does not exist.")
        ms=self._art(state,cp.get("manifest_snapshot"))
        if not ms or ms.get("artifact_type")!="PROJECT_MANIFEST_SNAPSHOT":
            raise StateEngineError("CHECKPOINT_MANIFEST_NOT_FOUND","Checkpoint Manifest snapshot is missing.")
        if sha256_json(ms.get("manifest"))!=ms.get("manifest_sha256"):
            raise StateEngineError("CHECKPOINT_MANIFEST_HASH_MISMATCH","Checkpoint Manifest snapshot checksum mismatch.")
        bundles=[]
        for ref in cp.get("registry_snapshots") or []:
            a=self._art(state,ref)
            if not a or a.get("artifact_type")!="REGISTRY_SNAPSHOT_BUNDLE":
                raise StateEngineError("CHECKPOINT_REGISTRY_MISSING","Checkpoint Registry snapshot bundle is missing.")
            bundles.append(a)
        if not bundles:raise StateEngineError("CHECKPOINT_REGISTRY_MISSING","Checkpoint has no Registry snapshot bundle.")
        bundle=bundles[0]
        for rid,data in (bundle.get("registries") or {}).items():
            expected=(bundle.get("registry_hashes") or {}).get(rid)
            body={k:v for k,v in data.items() if k!="sha256"}
            actual=sha256_json(body)
            if not expected or data.get("sha256")!=actual or expected!=actual:
                raise StateEngineError("CHECKPOINT_REGISTRY_HASH_MISMATCH",f"Checkpoint Registry snapshot {rid} checksum mismatch.")
        for ref in cp.get("important_artifact_refs") or []:
            if self._art(state,ref) is None:
                raise StateEngineError("CHECKPOINT_IMPORTANT_ARTIFACT_MISSING","Checkpoint important artifact is missing.",details=ref)
        return {"checkpoint_ref":deepcopy(checkpoint_ref),"integrity":"PASS","baseline_manifest_version":int(ms["manifest"]["manifest_version"])}

    def build_restore_plan(self, checkpoint_ref:dict[str,Any]) -> dict[str,Any]:
        self.verify_checkpoint(checkpoint_ref)
        state=self.engine.snapshot();cp=self._obj(state,checkpoint_ref);ms=self._art(state,cp["manifest_snapshot"]);baseline=ms["manifest"]
        current=self.builder.build(state,self.engine.gates)
        changes={
            "project_state":{"from":current["project_state"]["current"],"to":baseline["project_state"]["current"]},
            "registry_pointers":{},
            "current_refs":{"from":deepcopy(current.get("current") or {}),"to":deepcopy(baseline.get("current") or {})},
            "preserved_live_registries":sorted(PRESERVE_LIVE_REGISTRIES),
            "external_side_effects_reversed":False,
        }
        for rid,bptr in (baseline.get("registries") or {}).items():
            cptr=(current.get("registries") or {}).get(rid)
            if cptr!=bptr:changes["registry_pointers"][rid]={"from":deepcopy(cptr),"baseline":deepcopy(bptr)}
        tx=self.engine.begin(recovery=True)
        ref=tx.create_artifact("RESTORE_PLAN",{
            "checkpoint_ref":deepcopy(checkpoint_ref),
            "current_manifest_version":int(current["manifest_version"])+1,
            "target_baseline_manifest_version":int(baseline["manifest_version"]),
            "changes":changes,
            "risk":"HIGH" if current["manifest_version"]!=baseline["manifest_version"] else "LOW",
            "human_confirmation_required":True,
        },origin_refs=[checkpoint_ref])
        tx.commit()
        if self.workspace is not None:RuntimeStore(self.engine.root,self.workspace).persist(self.engine)
        return ref

    def _copy_artifact_payload_patch(self,current:dict[str,Any],baseline:dict[str,Any]):
        keys=(set(current)|set(baseline))-MANAGED_ARTIFACT_FIELDS-{"origin_refs","compiler"}
        patch={}
        for k in keys:
            patch[k]=deepcopy(baseline[k]) if k in baseline else None
        return patch

    def restore(self, restore_plan_ref:dict[str,Any], *, human_confirmed:bool) -> dict[str,Any]:
        if not human_confirmed:
            raise StateEngineError("RESTORE_HUMAN_CONFIRMATION_REQUIRED","Restore requires explicit Human confirmation.")
        state=self.engine.snapshot();plan=self._art(state,restore_plan_ref)
        if not plan or plan.get("artifact_type")!="RESTORE_PLAN":raise StateEngineError("RESTORE_PLAN_NOT_FOUND","Restore Plan does not exist.")
        if int(plan.get("current_manifest_version",0))!=int(self.engine.manifest_version):
            raise StateEngineError("RESTORE_PLAN_STALE","Project changed after the Restore Plan was created; build a new impact plan.")
        cp_ref=plan["checkpoint_ref"];self.verify_checkpoint(cp_ref);state=self.engine.snapshot();cp=self._obj(state,cp_ref)
        ms=self._art(state,cp["manifest_snapshot"]);baseline_manifest=ms["manifest"]
        bundle=self._art(state,cp["registry_snapshots"][0]);baseline_regs=bundle["registries"]

        tx=self.engine.begin(recovery=True)
        restored_active=[];deactivated=[];artifact_copies=[]
        # Restore production decision ACTIVE selections, but do not rewrite truths about
        # external effects, incidents, releases, or checkpoint history.
        for rid,reg in tx.staged.registries.items():
            if rid in PRESERVE_LIVE_REGISTRIES:continue
            base=baseline_regs.get(rid)
            if base is None:continue
            base_entries=base.get("entries") or {}
            for oid,entry in reg.entries.items():
                desired=(base_entries.get(oid) or {}).get("active_version")
                if desired is not None and int(desired) not in entry.versions:
                    raise StateEngineError("RESTORE_BASE_VERSION_MISSING",f"Historical version {oid}@{desired} required by checkpoint is unavailable.")
                if entry.active_version!=desired:
                    if desired is None:deactivated.append(oid)
                    else:restored_active.append({"id":oid,"version":int(desired)})
                    entry.active_version=None if desired is None else int(desired)
                    tx.dirty_registries.add(rid)

        # Re-establish project-level Artifact current pointers without moving Artifact
        # HEAD backwards: clone baseline content into a new version of the baseline ID.
        artifact_current_fields={k:v for k,v in (baseline_manifest.get("current") or {}).items() if isinstance(v,dict) and "artifact_id" in v}
        for field,ref in artifact_current_fields.items():
            baseline_art=tx.staged.artifacts.get((ref["artifact_id"],int(ref["version"])))
            if baseline_art is None:raise StateEngineError("RESTORE_ARTIFACT_VERSION_MISSING",f"Baseline Artifact {ref['artifact_id']}@{ref['version']} is unavailable.")
            entry=tx.staged.artifact_registry.entries[ref["artifact_id"]]
            current_art=tx.staged.artifacts[(ref["artifact_id"],int(entry.head_version))]
            patch=self._copy_artifact_payload_patch(current_art,baseline_art)
            new=tx.create_artifact_version(ref["artifact_id"],base_version=entry.head_version,payload_patch=patch,origin_refs=baseline_art.get("origin_refs") or [],compiler=baseline_art.get("compiler"))
            artifact_copies.append({"field":field,"from":deepcopy(ref),"restored_as":deepcopy(new)})

        tx.staged.project_state=baseline_manifest["project_state"]["current"]
        tx.staged.project_state_entered_at=self.engine.now()
        # Recompute dependency invalidation from exact refs versus the restored ACTIVE graph.
        summary=self.engine.dependency.recompute_live_state(tx.staged,self.engine.semantic,self.engine.now())
        idx=global_index(tx.staged.registries)
        for key in summary["changed_objects"]:
            obj=tx.staged.objects[key];rid=idx.get(obj["id"])
            if rid:
                dec=self.engine.semantic.decision_hash(obj)
                tx.staged.registries[rid].entries[obj["id"]].versions[int(obj["version"])]=locator_for(obj,dec)
                tx.dirty_registries.add(rid);tx.changed_keys.add(key)
        tx.actions.append(ActionAudit("RESTORE_FROM_CHECKPOINT",(f"{cp_ref['id']}@{cp_ref['version']}",),{
            "restore_plan":deepcopy(restore_plan_ref),"baseline_manifest_version":int(baseline_manifest["manifest_version"]),
            "restored_active":restored_active,"deactivated":deactivated,"artifact_copies":artifact_copies,
            "preserved_live_registries":sorted(PRESERVE_LIVE_REGISTRIES),
        }))
        tx.commit()
        manifest=None
        if self.workspace is not None:manifest=RuntimeStore(self.engine.root,self.workspace).persist(self.engine)
        return {"manifest_version":self.engine.manifest_version,"project_state":self.engine.project_state,"restored_active":restored_active,"artifact_copies":artifact_copies,"manifest":manifest}
