from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json, re

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_semantics.model import sha256_json
from .runtime import ReleaseRuntime


class DeliveryStageError(RuntimeError):
    pass


def _oref(o): return {"id":o["id"],"version":int(o["version"])}
def _aref(a): return {"artifact_id":a["artifact_id"],"artifact_type":a["artifact_type"],"version":int(a["version"]),"sha256":a["sha256"]}


def _active(state, typ):
    out=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type==typ and e.active_version is not None:
                out.append(state.objects[(oid,int(e.active_version))])
    return sorted(out,key=lambda x:(str(x.get("evaluated_at") or x.get("decided_at") or x.get("created_at") or ""),x["id"]))


def _heads(state, typ):
    out=[]
    for aid,e in state.artifact_registry.entries.items():
        if e.artifact_type==typ: out.append(state.artifacts[(aid,int(e.head_version))])
    return sorted(out,key=lambda x:(x["artifact_id"],int(x["version"])))


@dataclass(frozen=True)
class DeliveryPrepareResult:
    workspace: Path
    project_state: str
    batch_id: str
    review_package_ref: dict[str,Any]
    delivery_package_ref: dict[str,Any]
    delivery_qa_ref: dict[str,Any]
    final_asset_manifest_ref: dict[str,Any]
    provenance_manifest_ref: dict[str,Any]
    pre_release_checkpoint_ref: dict[str,Any]
    delivery_gate: str
    candidate_sha256: str
    idempotent_replay: bool
    review_record_path: str
    def to_dict(self):
        return {"workspace":str(self.workspace),"project_state":self.project_state,"batch_id":self.batch_id,
                "review_package_ref":dict(self.review_package_ref),"delivery_package_ref":dict(self.delivery_package_ref),
                "delivery_qa_ref":dict(self.delivery_qa_ref),"final_asset_manifest_ref":dict(self.final_asset_manifest_ref),
                "provenance_manifest_ref":dict(self.provenance_manifest_ref),"pre_release_checkpoint_ref":dict(self.pre_release_checkpoint_ref),
                "delivery_gate":self.delivery_gate,"candidate_sha256":self.candidate_sha256,
                "idempotent_replay":self.idempotent_replay,"review_record_path":self.review_record_path}


@dataclass(frozen=True)
class DeliveryDecisionResult:
    workspace: Path
    project_state: str
    decision: str
    actor_id: str
    review_package_ref: dict[str,Any]
    delivery_package_ref: dict[str,Any]
    approval_ref: dict[str,Any]
    delivery_gate: str
    transitioned: bool
    idempotent_replay: bool
    def to_dict(self):
        return {"workspace":str(self.workspace),"project_state":self.project_state,"decision":self.decision,"actor_id":self.actor_id,
                "review_package_ref":dict(self.review_package_ref),"delivery_package_ref":dict(self.delivery_package_ref),
                "approval_ref":dict(self.approval_ref),"delivery_gate":self.delivery_gate,
                "transitioned":self.transitioned,"idempotent_replay":self.idempotent_replay}


class DeliveryStageRuntime:
    """Build 033 delivery candidate + human delivery approval boundary."""
    REQUIRED_CHECKS=("package_integrity","provenance_complete","rights_ready","metadata_ready","destination_ready")
    def __init__(self,schema_root:Path,workspace:Path): self.root=Path(schema_root);self.workspace=Path(workspace)
    def _load(self): return ColdStartLoader(self.root,self.workspace).load().engine
    def _record(self,batch):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",batch).strip("._")
        if not safe: raise DeliveryStageError("DELIVERY_BATCH_ID_INVALID")
        return self.workspace/"reviews"/"delivery"/(safe+".json")
    def _evidence(self,eng):
        state=eng.snapshot()
        reports=[q for q in _active(state,"QA_REPORT") if q.get("report_type")=="FULL_FILM_QA"]
        if not reports: raise DeliveryStageError("DELIVERY_FULL_FILM_QA_MISSING")
        ff=reports[-1]
        if ff.get("result")!="PASS": raise DeliveryStageError(f"DELIVERY_FULL_FILM_QA_NOT_PASS: {ff.get('result')}")
        outref=deepcopy(ff.get("observed_artifact") or {})
        out=state.artifacts.get((outref.get("artifact_id"),int(outref.get("version",0))))
        if not out or out.get("artifact_type")!="RENDER_OUTPUT": raise DeliveryStageError("DELIVERY_MASTER_OUTPUT_UNRESOLVED")
        jobref=out.get("render_job_ref") or {};job=state.objects.get((jobref.get("id"),int(jobref.get("version",0))))
        if not job or job.get("object_type")!="RENDER_JOB": raise DeliveryStageError("DELIVERY_RENDER_JOB_UNRESOLVED")
        lockref=deepcopy(job.get("production_lock") or {})
        lock=state.artifacts.get((lockref.get("artifact_id"),int(lockref.get("version",0))))
        if not lock or lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST" or (lock.get("scope") or {}).get("type")!="PROJECT":
            raise DeliveryStageError("DELIVERY_PROJECT_LOCK_UNRESOLVED")
        return _oref(ff),outref,lockref
    def _existing(self,state,candidate_hash):
        xs=[a for a in _heads(state,"DELIVERY_REVIEW_PACKAGE") if a.get("candidate_sha256")==candidate_hash]
        return xs[-1] if xs else None
    def prepare(self,plan:dict[str,Any])->DeliveryPrepareResult:
        batch=str(plan.get("batch_id") or "").strip()
        if not batch: raise DeliveryStageError("DELIVERY_BATCH_ID_REQUIRED")
        eng=self._load()
        if eng.project_state not in {"FULL_FILM_QA_PASSED","DELIVERY_READY"}: raise DeliveryStageError(f"DELIVERY_STATE_INVALID: {eng.project_state}")
        if eng.gates.evaluate_gate(eng.snapshot(),"FULL_FILM_QA",eng.now()).result!="PASS": raise DeliveryStageError("DELIVERY_FULL_FILM_GATE_NOT_PASS")
        ffref,outref,lockref=self._evidence(eng)
        profile_id=str(plan.get("profile_id") or "GMK_YOUTUBE_4K")
        metadata=deepcopy(plan.get("metadata") or {})
        rel=ReleaseRuntime(eng,workspace=self.workspace);_,pref=rel.load_delivery_profile(profile_id)
        normalized={"batch_id":batch,"project_lock":lockref,"master_output":outref,"full_film_qa":ffref,"delivery_profile":pref,"metadata":metadata}
        ch=sha256_json(normalized);rp=self._record(batch)
        if rp.exists():
            data=json.loads(rp.read_text(encoding="utf-8"))
            if data.get("candidate_sha256")!=ch: raise DeliveryStageError("DELIVERY_BATCH_ID_COLLISION")
        existing=self._existing(eng.snapshot(),ch)
        if existing:
            x=existing
            result=DeliveryPrepareResult(self.workspace,eng.project_state,batch,_aref(x),x["delivery_package"],x["delivery_qa"],x["final_asset_manifest"],x["provenance_manifest"],x["pre_release_checkpoint"],eng.gates.evaluate_gate(eng.snapshot(),"DELIVERY",eng.now()).result,ch,True,str(rp.relative_to(self.workspace)))
            if not rp.exists():
                rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps({"batch_id":batch,"candidate_sha256":ch,"normalized":normalized,"result":result.to_dict()},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
            return result
        if eng.project_state!="FULL_FILM_QA_PASSED": raise DeliveryStageError("DELIVERY_REVIEW_PACKAGE_MISSING_AFTER_TRANSITION")
        try: cand=rel.prepare_release(project_lock_ref=lockref,master_output_ref=outref,full_film_qa_ref=ffref,profile_id=profile_id,metadata=metadata)
        except Exception as exc: raise DeliveryStageError(f"DELIVERY_PREPARE_FAILED: {exc}") from exc
        state=eng.snapshot();dq=state.objects[(cand["delivery_qa"]["id"],int(cand["delivery_qa"]["version"]))]
        fam=state.artifacts[(cand["final_asset_manifest"]["artifact_id"],int(cand["final_asset_manifest"]["version"]))]
        prov=state.artifacts[(cand["provenance_manifest"]["artifact_id"],int(cand["provenance_manifest"]["version"]))]
        lock=state.artifacts[(lockref["artifact_id"],int(lockref["version"]))];project_ref=deepcopy((lock.get("scope") or {}).get("project_ref"))
        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        try:
            rr=tx.create_artifact("DELIVERY_REVIEW_PACKAGE",{
                "scope":{"type":"DELIVERY","project_ref":project_ref},"project_lock":lockref,"master_output":outref,"full_film_qa":ffref,
                "delivery_qa":cand["delivery_qa"],"delivery_profile":cand["delivery_profile"],"final_asset_manifest":cand["final_asset_manifest"],
                "provenance_manifest":cand["provenance_manifest"],"delivery_package":cand["delivery_package"],"pre_release_checkpoint":cand["pre_release_checkpoint"],
                "metadata":metadata,"candidate_sha256":ch,
                "review_summary":{"delivery_qa_result":dq.get("result"),"asset_count":len(fam.get("assets") or []),"provenance_entry_count":len(prov.get("entries") or []),"disclosure_count":len(prov.get("disclosures") or [])},
                "extensions":{"delivery_stage":{"requires_human_decision":True,"build":33}},
            },origin_refs=[lockref,outref,ffref,cand["delivery_qa"],cand["final_asset_manifest"],cand["provenance_manifest"],cand["delivery_package"],cand["pre_release_checkpoint"]])
            tx.commit()
        except Exception:
            tx.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        gate=eng.gates.evaluate_gate(eng.snapshot(),"DELIVERY",eng.now()).result
        result=DeliveryPrepareResult(self.workspace,eng.project_state,batch,rr,cand["delivery_package"],cand["delivery_qa"],cand["final_asset_manifest"],cand["provenance_manifest"],cand["pre_release_checkpoint"],gate,ch,False,str(rp.relative_to(self.workspace)))
        rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps({"batch_id":batch,"candidate_sha256":ch,"normalized":normalized,"result":result.to_dict()},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return result
    def decide(self,plan:dict[str,Any])->DeliveryDecisionResult:
        eng=self._load()
        if eng.project_state not in {"FULL_FILM_QA_PASSED","DELIVERY_READY"}: raise DeliveryStageError(f"DELIVERY_DECISION_STATE_INVALID: {eng.project_state}")
        actor=str(plan.get("actor_id") or "").strip();decision=str(plan.get("decision") or "").upper()
        if not actor: raise DeliveryStageError("DELIVERY_ACTOR_REQUIRED")
        if decision not in {"APPROVED","REJECTED"}: raise DeliveryStageError("DELIVERY_DECISION_INVALID")
        state=eng.snapshot();packages=_heads(state,"DELIVERY_REVIEW_PACKAGE")
        if not packages: raise DeliveryStageError("DELIVERY_REVIEW_PACKAGE_REQUIRED")
        pkg=packages[-1];pkgref=_aref(pkg);target=deepcopy(pkg["delivery_package"])
        if decision=="APPROVED":
            checks=plan.get("checks") or {}
            bad=[k for k in self.REQUIRED_CHECKS if str(checks.get(k) or "").upper()!="PASS"]
            if bad: raise DeliveryStageError("DELIVERY_HUMAN_CHECKS_INCOMPLETE: "+",".join(bad))
            if eng.gates.evaluate_gate(state,"DELIVERY",eng.now()).result!="PASS": raise DeliveryStageError("DELIVERY_GATE_NOT_PASS")
        approvals=_active(state,"APPROVAL")
        found=next((a for a in approvals if a.get("approval_class")=="RELEASE" and a.get("target")==target and a.get("review_context")==pkgref and a.get("decision")==decision and (a.get("actor") or {}).get("actor_id")==actor),None)
        replay=found is not None;transitioned=False
        if found: ar=_oref(found)
        else:
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                ar=tx.create_approval({"approval_class":"RELEASE","target":target,"review_context":pkgref,"decision":decision,"actor":{"type":"HUMAN","actor_id":actor},"decided_at":eng.now()})
                tx.commit()
            except Exception:
                tx.discard();raise
        if decision=="APPROVED" and eng.project_state=="FULL_FILM_QA_PASSED":
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                tx.transition_project_state("DELIVERY_READY",actor_type="HUMAN",human_confirmed=True);tx.commit();transitioned=True
            except Exception:
                tx.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        return DeliveryDecisionResult(self.workspace,eng.project_state,decision,actor,pkgref,target,ar,eng.gates.evaluate_gate(eng.snapshot(),"DELIVERY",eng.now()).result,transitioned,replay)
