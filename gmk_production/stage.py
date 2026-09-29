from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_semantics.model import sha256_json
from .lock import ProductionLockRuntime


class ProductionLockStageError(RuntimeError):
    pass


def _oref(obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": obj["id"], "version": int(obj["version"])}


def _aref(art: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": art["artifact_id"],
        "artifact_type": art["artifact_type"],
        "version": int(art["version"]),
        "sha256": art["sha256"],
    }


def _active(state, object_type: str) -> list[dict[str, Any]]:
    out=[]
    for reg in state.registries.values():
        for oid,entry in reg.entries.items():
            if entry.object_type==object_type and entry.active_version is not None:
                out.append(state.objects[(oid,int(entry.active_version))])
    return sorted(out,key=lambda x:(int(x.get("order",0)),x["id"]))


def _heads(state, artifact_type: str) -> list[dict[str, Any]]:
    out=[]
    for aid,entry in state.artifact_registry.entries.items():
        if entry.artifact_type==artifact_type:
            out.append(state.artifacts[(aid,int(entry.head_version))])
    return sorted(out,key=lambda x:(x["artifact_id"],int(x["version"])))


def _plan_shots(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for item in plan.get("shots") or []:
        ref=item.get("shot_ref") if isinstance(item,dict) and "shot_ref" in item else item
        if isinstance(ref,dict) and ref.get("id") and ref.get("version"):
            out.append({"id":ref["id"],"version":int(ref["version"])})
    return out


def _dedupe_obj_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen=set();out=[]
    for r in refs:
        key=(r.get("id"),int(r.get("version",0)))
        if key not in seen:
            seen.add(key);out.append({"id":r["id"],"version":int(r["version"])})
    return out


def _dedupe_art_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen=set();out=[]
    for r in refs:
        key=(r.get("artifact_id"),int(r.get("version",0)))
        if key not in seen:
            seen.add(key);out.append(dict(r))
    return out


@dataclass(frozen=True)
class ProductionLockPrepareResult:
    workspace: Path
    project_state: str
    scene_count: int
    shot_count: int
    layer_count: int
    cue_count: int
    review_package_ref: dict[str, Any]
    closure_sha256: str
    gate_result: str
    transitioned: bool
    idempotent_replay: bool

    def to_dict(self):
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,
            "scene_count":self.scene_count,"shot_count":self.shot_count,
            "layer_count":self.layer_count,"cue_count":self.cue_count,
            "review_package_ref":dict(self.review_package_ref),"closure_sha256":self.closure_sha256,
            "gate_result":self.gate_result,"transitioned":self.transitioned,
            "idempotent_replay":self.idempotent_replay,
        }


@dataclass(frozen=True)
class ProductionLockDecisionResult:
    workspace: Path
    project_state: str
    decision: str
    actor_id: str
    review_package_ref: dict[str, Any]
    scene_lock_refs: tuple[dict[str, Any], ...]
    project_lock_ref: dict[str, Any] | None
    shot_visual_approval_count: int
    production_lock_approval_count: int
    gate_result: str
    transitioned: bool
    idempotent_replay: bool

    def to_dict(self):
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,
            "decision":self.decision,"actor_id":self.actor_id,
            "review_package_ref":dict(self.review_package_ref),
            "scene_lock_refs":[dict(x) for x in self.scene_lock_refs],
            "project_lock_ref":dict(self.project_lock_ref) if self.project_lock_ref else None,
            "shot_visual_approval_count":self.shot_visual_approval_count,
            "production_lock_approval_count":self.production_lock_approval_count,
            "gate_result":self.gate_result,"transitioned":self.transitioned,
            "idempotent_replay":self.idempotent_replay,
        }


class ProductionLockStageRuntime:
    """Build 029 production-lock review and lock boundary.

    The human reviews an exact pre-lock closure. Approval may create only the
    Shot approvals and Production Locks whose exact refs are present in that
    reviewed closure. Any drift produces a new closure hash and requires a new
    human decision.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root=Path(schema_root);self.workspace=Path(workspace)

    def _load(self):
        return ColdStartLoader(self.root,self.workspace).load().engine

    def _closure(self,state):
        projects=_active(state,"PROJECT")
        scenes=_active(state,"SCENE")
        if len(projects)!=1 or not scenes:
            raise ProductionLockStageError("PRODUCTION_LOCK_PROJECT_SCENE_CARDINALITY_INVALID")
        project=projects[0]
        plans=_heads(state,"SCENE_PLAN"); previews=_heads(state,"SCENE_PREVIEW")
        p_by_scene={(p.get("scene_ref") or {}).get("id"):p for p in plans}
        v_by_scene={(p.get("scene_ref") or {}).get("id"):p for p in previews}
        approvals=_active(state,"APPROVAL")
        pairs=[]
        shots=[];layers=[];cues=[];voice_refs=[];dna_refs=[]
        for scene in scenes:
            plan=p_by_scene.get(scene["id"]);preview=v_by_scene.get(scene["id"])
            if not plan or not preview:
                raise ProductionLockStageError(f"PRODUCTION_LOCK_SCENE_REVIEW_MISSING: {scene['id']}")
            pref=preview.get("scene_plan") or {}
            if (pref.get("artifact_id"),int(pref.get("version",0)))!=(plan.get("artifact_id"),int(plan.get("version",0))):
                raise ProductionLockStageError(f"PRODUCTION_LOCK_PREVIEW_PLAN_MISMATCH: {scene['id']}")
            target=_aref(preview)
            if not any(a.get("approval_class")=="SCENE_PREVIEW" and a.get("decision")=="APPROVED" and a.get("target")==target for a in approvals):
                raise ProductionLockStageError(f"PRODUCTION_LOCK_SCENE_PREVIEW_NOT_APPROVED: {scene['id']}")
            srefs=_plan_shots(plan)
            if not srefs:
                raise ProductionLockStageError(f"PRODUCTION_LOCK_SCENE_SHOTS_MISSING: {scene['id']}")
            scene_shots=[]
            for ref in srefs:
                shot=state.objects.get((ref["id"],int(ref["version"])))
                if not shot or shot.get("object_type")!="SHOT":
                    raise ProductionLockStageError(f"PRODUCTION_LOCK_SHOT_MISSING: {ref}")
                scene_shots.append(shot);shots.append(ref)
                for r in shot.get("layer_refs") or []: layers.append(r)
                for r in shot.get("cue_refs") or []: cues.append(r)
            voice=plan.get("voice_lock") or {};dna=plan.get("design_dna_ref") or {}
            if not voice.get("artifact_id") or not dna.get("id"):
                raise ProductionLockStageError("PRODUCTION_LOCK_PLAN_DEPENDENCY_MISSING")
            voice_refs.append(dict(voice));dna_refs.append({"id":dna["id"],"version":int(dna["version"])})
            pairs.append((scene,plan,preview,scene_shots))
        shots=_dedupe_obj_refs(shots);layers=_dedupe_obj_refs(layers);cues=_dedupe_obj_refs(cues)
        voice_refs=_dedupe_art_refs(voice_refs);dna_refs=_dedupe_obj_refs(dna_refs)
        payload={
            "scene_previews":[_aref(x[2]) for x in pairs],
            "scene_plans":[_aref(x[1]) for x in pairs],
            "voice_locks":voice_refs,
            "design_dna_refs":dna_refs,
            "shots":shots,"layers":layers,"cues":cues,
        }
        return project,pairs,payload,sha256_json(payload)

    def _current_package(self,state,closure_hash):
        matches=[a for a in _heads(state,"PRODUCTION_LOCK_REVIEW_PACKAGE") if a.get("closure_sha256")==closure_hash]
        return matches[-1] if matches else None

    def prepare(self)->ProductionLockPrepareResult:
        eng=self._load();state=eng.snapshot()
        if eng.project_state not in {"HTML_APPROVED","PRODUCTION_RENDER"}:
            raise ProductionLockStageError(f"PRODUCTION_LOCK_STATE_INVALID: expected HTML_APPROVED/PRODUCTION_RENDER, found {eng.project_state}")
        html_gate=eng.gates.evaluate_gate(state,"HTML_REVIEW",eng.now()).result
        if html_gate not in {"PASS","WARN"}:
            raise ProductionLockStageError(f"PRODUCTION_LOCK_HTML_APPROVAL_INVALID: {html_gate}")
        project,pairs,closure,closure_hash=self._closure(state)
        existing=self._current_package(state,closure_hash)
        gate=eng.gates.evaluate_gate(state,"PRODUCTION_LOCK",eng.now()).result
        if existing:
            return ProductionLockPrepareResult(self.workspace,eng.project_state,len(pairs),len(closure["shots"]),len(closure["layers"]),len(closure["cues"]),_aref(existing),closure_hash,gate,False,True)
        if eng.project_state!="HTML_APPROVED":
            raise ProductionLockStageError("PRODUCTION_LOCK_REVIEW_PACKAGE_MISSING_AFTER_TRANSITION")
        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        try:
            ref=tx.create_artifact("PRODUCTION_LOCK_REVIEW_PACKAGE",{
                "scope":{"type":"PROJECT_PRODUCTION_LOCK","project_ref":_oref(project)},
                **closure,
                "closure_sha256":closure_hash,
                "review_summary":{"scene_count":len(pairs),"shot_count":len(closure["shots"]),"layer_count":len(closure["layers"]),"cue_count":len(closure["cues"])},
                "extensions":{"production_lock_stage":{"requires_human_decision":True,"build":29}},
            },origin_refs=[_oref(project),*closure["scene_previews"],*closure["scene_plans"],*closure["voice_locks"],*closure["design_dna_refs"],*closure["shots"],*closure["layers"],*closure["cues"]])
            tx.commit()
        except Exception:
            tx.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        state2=eng.snapshot();pkg=state2.artifacts[(ref["artifact_id"],int(ref["version"]))]
        gate=eng.gates.evaluate_gate(state2,"PRODUCTION_LOCK",eng.now()).result
        return ProductionLockPrepareResult(self.workspace,eng.project_state,len(pairs),len(closure["shots"]),len(closure["layers"]),len(closure["cues"]),_aref(pkg),closure_hash,gate,False,False)

    def _approval_exists(self,state,cls,target,decision,actor_id=None,context=None):
        for a in _active(state,"APPROVAL"):
            if a.get("approval_class")!=cls or a.get("target")!=target or a.get("decision")!=decision: continue
            if actor_id is not None and (a.get("actor") or {}).get("actor_id")!=actor_id: continue
            if context is not None and a.get("review_context")!=context: continue
            return a
        return None

    def _matching_scene_lock(self,state,scene,plan,preview,shots):
        want_shots=[_oref(x) for x in shots]
        for a in _heads(state,"PRODUCTION_LOCK_MANIFEST"):
            if (a.get("scope") or {}).get("type")!="SCENE": continue
            if (a.get("scope") or {}).get("scene_ref")!=_oref(scene): continue
            if a.get("voice_lock")!=(plan.get("voice_lock") or {}): continue
            if a.get("design_dna_ref")!=(plan.get("design_dna_ref") or {}): continue
            if a.get("scene_plan")!=_aref(plan) or a.get("scene_preview")!=_aref(preview): continue
            if a.get("shots")==want_shots: return a
        return None

    def _matching_project_lock(self,state,scene_lock_refs):
        for a in _heads(state,"PRODUCTION_LOCK_MANIFEST"):
            if (a.get("scope") or {}).get("type")!="PROJECT": continue
            if a.get("scene_locks")==scene_lock_refs: return a
        return None

    def decide(self,plan:dict[str,Any])->ProductionLockDecisionResult:
        actor_id=str(plan.get("actor_id") or "").strip();decision=str(plan.get("decision") or "").upper()
        if not actor_id: raise ProductionLockStageError("PRODUCTION_LOCK_HUMAN_ACTOR_REQUIRED")
        if decision not in {"APPROVED","REJECTED"}: raise ProductionLockStageError("PRODUCTION_LOCK_DECISION_INVALID")
        eng=self._load();state=eng.snapshot()
        if eng.project_state not in {"HTML_APPROVED","PRODUCTION_RENDER"}:
            raise ProductionLockStageError(f"PRODUCTION_LOCK_DECISION_STATE_INVALID: {eng.project_state}")
        project,pairs,closure,closure_hash=self._closure(state)
        pkg=self._current_package(state,closure_hash)
        if not pkg: raise ProductionLockStageError("PRODUCTION_LOCK_REVIEW_PACKAGE_REQUIRED")
        pkgref=_aref(pkg)

        if decision=="REJECTED":
            existing=self._approval_exists(state,"PRODUCTION_LOCK",pkgref,"REJECTED",actor_id,pkgref)
            if not existing:
                tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
                try:
                    tx.create_approval({"approval_class":"PRODUCTION_LOCK","target":pkgref,"review_context":pkgref,"decision":"REJECTED","actor":{"type":"HUMAN","actor_id":actor_id},"decided_at":eng.now()})
                    tx.commit()
                except Exception:
                    tx.discard();raise
                RuntimeStore(self.root,self.workspace).persist(eng)
            gate=eng.gates.evaluate_gate(eng.snapshot(),"PRODUCTION_LOCK",eng.now()).result
            return ProductionLockDecisionResult(self.workspace,eng.project_state,decision,actor_id,pkgref,tuple(),None,0,0,gate,False,existing is not None)

        # Re-verify exact reviewed closure immediately before mutating approvals.
        _,pairs2,closure2,hash2=self._closure(state)
        if hash2!=closure_hash or closure2!={k:pkg.get(k,[]) for k in ("scene_previews","scene_plans","voice_locks","design_dna_refs","shots","layers","cues")}:
            raise ProductionLockStageError("PRODUCTION_LOCK_REVIEW_CLOSURE_DRIFT")

        # Human decision explicitly covers every Shot in the reviewed closure.
        missing=[]
        for ref in closure["shots"]:
            shot=state.objects[(ref["id"],int(ref["version"]))]
            target=_oref(shot)
            if not self._approval_exists(state,"SHOT_VISUAL",target,"APPROVED",None,pkgref):
                missing.append(shot)
        if missing:
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                for shot in missing:
                    tx.create_approval({
                        "approval_class":"SHOT_VISUAL","target":_oref(shot),
                        "target_decision_sha256":eng.semantic.decision_hash(shot),
                        "review_context":pkgref,"decision":"APPROVED",
                        "actor":{"type":"HUMAN","actor_id":actor_id},"decided_at":eng.now(),
                    })
                tx.commit()
            except Exception:
                tx.discard();raise
            RuntimeStore(self.root,self.workspace).persist(eng)

        # Build exact scene/project locks. Existing matching locks are reused on replay.
        lock_runtime=ProductionLockRuntime(eng);scene_refs=[]
        for scene,scene_plan,preview,scene_shots in pairs2:
            current=eng.snapshot();found=self._matching_scene_lock(current,scene,scene_plan,preview,scene_shots)
            if found:
                scene_refs.append(_aref(found));continue
            ref=lock_runtime.create_scene_lock(
                voice_lock_ref=scene_plan["voice_lock"],design_dna_ref=scene_plan["design_dna_ref"],
                scene_plan_ref=_aref(scene_plan),scene_preview_ref=_aref(preview),
                shot_refs=[_oref(x) for x in scene_shots],
            )
            current=eng.snapshot();scene_refs.append(_aref(current.artifacts[(ref["artifact_id"],int(ref["version"]))]))
        state_locks=eng.snapshot();project_lock=self._matching_project_lock(state_locks,scene_refs)
        if not project_lock:
            pref=lock_runtime.create_project_lock(scene_lock_refs=scene_refs)
            state_locks=eng.snapshot();project_lock=state_locks.artifacts[(pref["artifact_id"],int(pref["version"]))]
        project_ref=_aref(project_lock)

        # Gate covers every current fresh Production Lock head, including scene locks.
        state_before_approval=eng.snapshot();lock_targets=[]
        for a in _heads(state_before_approval,"PRODUCTION_LOCK_MANIFEST"):
            # Only locks belonging to the exact reviewed closure may receive this decision.
            if (a.get("scope") or {}).get("type")=="SCENE" and _aref(a) not in scene_refs: continue
            if (a.get("scope") or {}).get("type")=="PROJECT" and _aref(a)!=project_ref: continue
            lock_targets.append(_aref(a))
        missing_lock_targets=[t for t in lock_targets if not self._approval_exists(state_before_approval,"PRODUCTION_LOCK",t,"APPROVED",None,pkgref)]
        if missing_lock_targets:
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                for target in missing_lock_targets:
                    tx.create_approval({"approval_class":"PRODUCTION_LOCK","target":target,"review_context":pkgref,"decision":"APPROVED","actor":{"type":"HUMAN","actor_id":actor_id},"decided_at":eng.now()})
                tx.commit()
            except Exception:
                tx.discard();raise
            RuntimeStore(self.root,self.workspace).persist(eng)

        state2=eng.snapshot();gate=eng.gates.evaluate_gate(state2,"PRODUCTION_LOCK",eng.now()).result
        transitioned=False
        if eng.project_state=="HTML_APPROVED" and gate in {"PASS","WARN"}:
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                tx.transition_project_state("PRODUCTION_RENDER",actor_type="HUMAN",human_confirmed=True);tx.commit();transitioned=True
            except Exception:
                tx.discard();raise
            RuntimeStore(self.root,self.workspace).persist(eng)
            state2=eng.snapshot();gate=eng.gates.evaluate_gate(state2,"PRODUCTION_LOCK",eng.now()).result

        shot_count=sum(1 for a in _active(state2,"APPROVAL") if a.get("approval_class")=="SHOT_VISUAL" and a.get("decision")=="APPROVED" and a.get("review_context")==pkgref)
        lock_count=sum(1 for a in _active(state2,"APPROVAL") if a.get("approval_class")=="PRODUCTION_LOCK" and a.get("decision")=="APPROVED" and a.get("review_context")==pkgref)
        replay=(eng.project_state=="PRODUCTION_RENDER" and not transitioned and not missing and not missing_lock_targets)
        return ProductionLockDecisionResult(self.workspace,eng.project_state,decision,actor_id,pkgref,tuple(scene_refs),project_ref,shot_count,lock_count,gate,transitioned,replay)
