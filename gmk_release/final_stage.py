from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import shutil

from gmk_operations import OperationExecutionResult
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_semantics.model import sha256_json
from .runtime import ReleaseRuntime


class ReleaseFinalStageError(RuntimeError):
    pass


def _oref(o): return {"id":o["id"],"version":int(o["version"])}
def _aref(a): return {"artifact_id":a["artifact_id"],"artifact_type":a["artifact_type"],"version":int(a["version"]),"sha256":a["sha256"]}


def _active(state, typ):
    out=[]
    for reg in state.registries.values():
        for oid,e in reg.entries.items():
            if e.object_type==typ and e.active_version is not None:
                out.append(state.objects[(oid,int(e.active_version))])
    return sorted(out,key=lambda x:(str(x.get("released_at") or x.get("decided_at") or x.get("created_at") or ""),x["id"]))


def _heads(state, typ):
    out=[]
    for aid,e in state.artifact_registry.entries.items():
        if e.artifact_type==typ: out.append(state.artifacts[(aid,int(e.head_version))])
    return sorted(out,key=lambda x:(x["artifact_id"],int(x["version"])))


def _sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()


def _safe_name(value:str)->str:
    value=re.sub(r"[^A-Za-z0-9_.-]+","_",value).strip("._")
    return value or "release"


@dataclass(frozen=True)
class ReleaseFinalStageResult:
    workspace: Path
    project_state: str
    batch_id: str
    review_package_ref: dict[str,Any]
    delivery_package_ref: dict[str,Any]
    release_ref: dict[str,Any]
    operation_ref: dict[str,Any]
    final_checkpoint_ref: dict[str,Any]
    destination: str
    receipt_path: str
    idempotent_replay: bool
    record_path: str
    def to_dict(self):
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,"batch_id":self.batch_id,
            "review_package_ref":dict(self.review_package_ref),"delivery_package_ref":dict(self.delivery_package_ref),
            "release_ref":dict(self.release_ref),"operation_ref":dict(self.operation_ref),
            "final_checkpoint_ref":dict(self.final_checkpoint_ref),"destination":self.destination,
            "receipt_path":self.receipt_path,"idempotent_replay":self.idempotent_replay,"record_path":self.record_path,
        }


class ReleaseFinalStageRuntime:
    """Build 034 authorized publish + immutable release + final project closeout.

    CLI execution deliberately supports LOCAL_EXPORT only. A future external adapter
    may call ReleaseRuntime.publish directly, but this stage never pretends that a
    remote platform publish occurred without an authorized adapter.
    """
    def __init__(self,schema_root:Path,workspace:Path): self.root=Path(schema_root);self.workspace=Path(workspace)
    def _load(self): return ColdStartLoader(self.root,self.workspace).load().engine
    def _record(self,batch):
        safe=_safe_name(batch)
        return self.workspace/"reviews"/"release"/(safe+".json")
    def _latest_package(self,state):
        xs=_heads(state,"DELIVERY_REVIEW_PACKAGE")
        if not xs: raise ReleaseFinalStageError("RELEASE_DELIVERY_REVIEW_PACKAGE_REQUIRED")
        return xs[-1]
    def _approval(self,state,pkg):
        pkgref=_aref(pkg);target=deepcopy(pkg["delivery_package"])
        matches=[]
        for a in _active(state,"APPROVAL"):
            if a.get("approval_class")!="RELEASE" or a.get("decision")!="APPROVED": continue
            if a.get("target")!=target or a.get("review_context")!=pkgref: continue
            if a.get("status") in {"STALE","BLOCKED","REJECTED"} or (a.get("stale") or {}).get("is_stale"): continue
            matches.append(a)
        if not matches: raise ReleaseFinalStageError("RELEASE_EXACT_HUMAN_APPROVAL_REQUIRED")
        return matches[-1]
    def _candidate(self,pkg):
        return {
            "project_lock":deepcopy(pkg["project_lock"]),"master_output":deepcopy(pkg["master_output"]),
            "full_film_qa":deepcopy(pkg["full_film_qa"]),"delivery_qa":deepcopy(pkg["delivery_qa"]),
            "delivery_profile":deepcopy(pkg["delivery_profile"]),"final_asset_manifest":deepcopy(pkg["final_asset_manifest"]),
            "provenance_manifest":deepcopy(pkg["provenance_manifest"]),"delivery_package":deepcopy(pkg["delivery_package"]),
            "pre_release_checkpoint":deepcopy(pkg["pre_release_checkpoint"]),"metadata":deepcopy(pkg.get("metadata") or {}),
        }
    def _media_path(self,state,master_ref):
        out=state.artifacts.get((master_ref.get("artifact_id"),int(master_ref.get("version",0))))
        if not out or out.get("artifact_type")!="RENDER_OUTPUT": raise ReleaseFinalStageError("RELEASE_MASTER_OUTPUT_MISSING")
        uri=str(out.get("media_uri") or "")
        prefix="gmk://media/"
        if not uri.startswith(prefix): raise ReleaseFinalStageError(f"RELEASE_LOCAL_EXPORT_MEDIA_URI_UNSUPPORTED: {uri}")
        rel=uri[len(prefix):]
        path=(self.workspace/"media"/rel).resolve()
        media_root=(self.workspace/"media").resolve()
        if media_root not in path.parents: raise ReleaseFinalStageError("RELEASE_LOCAL_EXPORT_MEDIA_PATH_INVALID")
        if not path.is_file(): raise ReleaseFinalStageError(f"RELEASE_MASTER_MEDIA_FILE_MISSING: {path}")
        if _sha256_file(path)!=out.get("media_sha256"): raise ReleaseFinalStageError("RELEASE_MASTER_MEDIA_HASH_MISMATCH")
        return path,out
    def _write_json_exact(self,path:Path,data:Any):
        payload=(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8")
        if path.exists():
            if path.read_bytes()!=payload: raise ReleaseFinalStageError(f"RELEASE_LOCAL_EXPORT_CONFLICT: {path}")
            return
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
    def _local_executor(self,eng,candidate,destination:Path,release_label:str,pkgref:dict[str,Any]):
        state=eng.snapshot();src,out=self._media_path(state,candidate["master_output"])
        root=destination.resolve();root.mkdir(parents=True,exist_ok=True)
        export_dir=root/_safe_name(release_label)
        export_dir.mkdir(parents=True,exist_ok=True)
        master=export_dir/("master"+src.suffix.lower())
        if master.exists():
            if _sha256_file(master)!=out["media_sha256"]: raise ReleaseFinalStageError("RELEASE_LOCAL_EXPORT_MASTER_CONFLICT")
        else: shutil.copyfile(src,master)
        if _sha256_file(master)!=out["media_sha256"]: raise ReleaseFinalStageError("RELEASE_LOCAL_EXPORT_MASTER_COPY_HASH_MISMATCH")
        refs={
            "delivery_review_package":pkgref,"delivery_package":candidate["delivery_package"],
            "final_asset_manifest":candidate["final_asset_manifest"],"provenance_manifest":candidate["provenance_manifest"],
            "full_film_qa":candidate["full_film_qa"],"delivery_qa":candidate["delivery_qa"],
            "master_output":candidate["master_output"],"production_lock":candidate["project_lock"],
        }
        artifacts={}
        for key,ref in refs.items():
            if "artifact_id" in ref:
                art=state.artifacts.get((ref["artifact_id"],int(ref["version"])))
                if not art: raise ReleaseFinalStageError(f"RELEASE_EXPORT_ARTIFACT_MISSING: {key}")
                artifacts[key]=art
            else:
                obj=state.objects.get((ref["id"],int(ref["version"])))
                if not obj: raise ReleaseFinalStageError(f"RELEASE_EXPORT_OBJECT_MISSING: {key}")
                artifacts[key]=obj
        self._write_json_exact(export_dir/"delivery-candidate.json",{
            "release_label":release_label,"metadata":candidate.get("metadata") or {},"refs":refs,
            "master_file":master.name,"master_sha256":out["media_sha256"],"artifacts":artifacts,
        })
        receipt={"mode":"LOCAL_EXPORT","release_label":release_label,"destination":str(export_dir),"master_file":master.name,
                 "master_sha256":out["media_sha256"],"delivery_package_sha256":candidate["delivery_package"]["sha256"],
                 "candidate_sha256":sha256_json({"review_package":pkgref,"candidate":candidate,"release_label":release_label})}
        self._write_json_exact(export_dir/"publish-receipt.json",receipt)
        return OperationExecutionResult("SUCCEEDED",f"LOCAL_EXPORT {export_dir}",{"receipt_path":str(export_dir/"publish-receipt.json"),"export_dir":str(export_dir),"master_path":str(master)})
    def run(self,plan:dict[str,Any])->ReleaseFinalStageResult:
        batch=str(plan.get("batch_id") or "").strip();release_label=str(plan.get("release_label") or "v1").strip()
        if not batch: raise ReleaseFinalStageError("RELEASE_BATCH_ID_REQUIRED")
        if not release_label: raise ReleaseFinalStageError("RELEASE_LABEL_REQUIRED")
        mode=str(plan.get("mode") or "LOCAL_EXPORT").upper()
        if mode!="LOCAL_EXPORT": raise ReleaseFinalStageError("RELEASE_CLI_MODE_UNSUPPORTED: only LOCAL_EXPORT is authorized in Build 034 CLI")
        dest_raw=str(plan.get("destination_dir") or "").strip()
        if not dest_raw: raise ReleaseFinalStageError("RELEASE_DESTINATION_REQUIRED")
        dest=Path(dest_raw)
        eng=self._load();state=eng.snapshot()
        if eng.project_state not in {"DELIVERY_READY","PROJECT_COMPLETED"}: raise ReleaseFinalStageError(f"RELEASE_STATE_INVALID: {eng.project_state}")
        pkg=self._latest_package(state);pkgref=_aref(pkg);self._approval(state,pkg);candidate=self._candidate(pkg)
        normalized={"batch_id":batch,"mode":mode,"destination":str(dest.resolve()),"release_label":release_label,
                    "review_package":pkgref,"candidate_sha256":pkg.get("candidate_sha256")}
        ph=sha256_json(normalized);record=self._record(batch)
        if record.exists():
            data=json.loads(record.read_text(encoding="utf-8"))
            if data.get("plan_sha256")!=ph: raise ReleaseFinalStageError("RELEASE_BATCH_ID_COLLISION")
            out=data.get("result") or {};snap=eng.snapshot()
            rr=out.get("release_ref") or {};cp=out.get("final_checkpoint_ref") or {}
            if (rr.get("id"),int(rr.get("version",0))) not in snap.objects or (cp.get("id"),int(cp.get("version",0))) not in snap.objects:
                raise ReleaseFinalStageError("RELEASE_REPLAY_REFERENCES_MISSING")
            return ReleaseFinalStageResult(self.workspace,eng.project_state,batch,pkgref,candidate["delivery_package"],rr,out["operation_ref"],cp,
                                           str(dest.resolve()),out["receipt_path"],True,str(record.relative_to(self.workspace)))
        rel=ReleaseRuntime(eng,workspace=self.workspace)
        published=rel.publish(candidate,executor=lambda _op:self._local_executor(eng,candidate,dest,release_label,pkgref),
                              provider="GMK_LOCAL_EXPORT",destination=str(dest.resolve()),release_label=release_label,human_confirmed=True)
        completed=rel.finalize_project(published.release_ref,important_artifact_refs=[candidate["delivery_package"],pkgref])
        RuntimeStore(self.root,self.workspace).persist(eng)
        op=eng.snapshot().objects[(published.operation_ref["id"],int(published.operation_ref["version"]))]
        details=((op.get("attempts") or [{}])[-1].get("result") or "")
        receipt=str(dest.resolve()/_safe_name(release_label)/"publish-receipt.json")
        result=ReleaseFinalStageResult(self.workspace,eng.project_state,batch,pkgref,candidate["delivery_package"],published.release_ref,
                                       published.operation_ref,completed["final_checkpoint_ref"],str(dest.resolve()),receipt,False,str(record.relative_to(self.workspace)))
        record.parent.mkdir(parents=True,exist_ok=True)
        record.write_text(json.dumps({"batch_id":batch,"plan_sha256":ph,"normalized":normalized,"operation_result":details,"result":result.to_dict()},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return result
