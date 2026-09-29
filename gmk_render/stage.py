from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import shutil
import subprocess

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.media_tools import resolve_ffprobe, MediaToolNotFound
from gmk_runtime.persistence import RuntimeStore
from gmk_semantics.model import sha256_json
from gmk_production.lock import ProductionLockRuntime
from gmk_qa import QARuntime
from .runtime import RenderRuntime, RenderProduct


class RenderQAStageError(RuntimeError):
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
        for oid, entry in reg.entries.items():
            if entry.object_type==object_type and entry.active_version is not None:
                out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x:(int(x.get("order",0)), x["id"]))


def _heads(state, artifact_type: str) -> list[dict[str, Any]]:
    out=[]
    for aid, entry in state.artifact_registry.entries.items():
        if entry.artifact_type==artifact_type:
            out.append(state.artifacts[(aid, int(entry.head_version))])
    return sorted(out, key=lambda x:(x["artifact_id"], int(x["version"])))


def _sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
    try:
        tool = resolve_ffprobe()
    except MediaToolNotFound as exc:
        raise RenderQAStageError("RENDER_FILE_FFPROBE_NOT_INSTALLED") from exc
    p=subprocess.run([
        tool,"-v","error","-show_streams","-show_format","-of","json",str(path)
    ], capture_output=True, text=True)
    if p.returncode!=0:
        raise RenderQAStageError(f"RENDER_FILE_FFPROBE_FAILED: {p.stderr.strip()}")
    try:
        data=json.loads(p.stdout)
    except Exception as exc:
        raise RenderQAStageError(f"RENDER_FILE_FFPROBE_JSON_INVALID: {exc}") from exc
    videos=[s for s in data.get("streams",[]) if s.get("codec_type")=="video"]
    if not videos:
        raise RenderQAStageError("RENDER_FILE_VIDEO_STREAM_REQUIRED")
    v=videos[0]
    try:
        duration=float((data.get("format") or {}).get("duration") or v.get("duration") or 0)
    except Exception:
        duration=0.0
    if duration<=0:
        raise RenderQAStageError("RENDER_FILE_DURATION_INVALID")
    try:
        width=int(v.get("width") or 0);height=int(v.get("height") or 0)
    except Exception:
        width=height=0
    if width<=0 or height<=0:
        raise RenderQAStageError("RENDER_FILE_DIMENSIONS_INVALID")
    rate=str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1")
    try:
        f=Fraction(rate)
        frame_rate={"numerator":int(f.numerator),"denominator":int(f.denominator)} if f.numerator>0 else None
    except Exception:
        frame_rate=None
    tech={
        "width":width,"height":height,"duration_seconds":duration,
        "codec":str(v.get("codec_name") or "unknown"),
        "container":str((data.get("format") or {}).get("format_name") or path.suffix.lstrip(".") or "unknown"),
        "audio_present":any(s.get("codec_type")=="audio" for s in data.get("streams",[])),
    }
    if frame_rate: tech["frame_rate"]=frame_rate
    return tech


class _LocalFinalAdapter:
    def __init__(self, path: Path, media_uri: str, technical: dict[str, Any]):
        self.path=path;self.media_uri=media_uri;self.technical=technical
    def render(self, payload, snapshot, *, attempt):
        return RenderProduct(self.media_uri, self.path.read_bytes(), media_type="VIDEO", technical=deepcopy(self.technical))


@dataclass(frozen=True)
class RenderQAStageResult:
    workspace: Path
    project_state: str
    batch_id: str
    production_lock_ref: dict[str, Any]
    render_job_ref: dict[str, Any]
    render_manifest_ref: dict[str, Any]
    render_output_ref: dict[str, Any]
    qa_report_refs: tuple[dict[str, Any], ...]
    qa_baseline_ref: dict[str, Any] | None
    render_gate: str
    shot_qa_gate: str
    transitioned: bool
    idempotent_replay: bool
    review_record_path: str

    def to_dict(self):
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,"batch_id":self.batch_id,
            "production_lock_ref":dict(self.production_lock_ref),"render_job_ref":dict(self.render_job_ref),
            "render_manifest_ref":dict(self.render_manifest_ref),"render_output_ref":dict(self.render_output_ref),
            "qa_report_refs":[dict(x) for x in self.qa_report_refs],
            "qa_baseline_ref":dict(self.qa_baseline_ref) if self.qa_baseline_ref else None,
            "render_gate":self.render_gate,"shot_qa_gate":self.shot_qa_gate,
            "transitioned":self.transitioned,"idempotent_replay":self.idempotent_replay,
            "review_record_path":self.review_record_path,
        }


class RenderQAStageRuntime:
    """Build 030 final-render handoff and explicit Shot QA stage.

    This runtime never invents rendered media or visual QA. The caller must supply
    an actual local video file and one explicit review record for every current
    ACTIVE Shot. Each review is content-hashed into the QA profile and written to
    an immutable workspace review ledger before transition is attempted.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root=Path(schema_root);self.workspace=Path(workspace)

    def _load(self):
        return ColdStartLoader(self.root,self.workspace).load().engine

    def _project_lock(self, eng, state):
        locks=[a for a in _heads(state,"PRODUCTION_LOCK_MANIFEST") if (a.get("scope") or {}).get("type")=="PROJECT"]
        valid=[]
        runtime=ProductionLockRuntime(eng)
        for a in locks:
            try:
                runtime.assert_valid(_aref(a));valid.append(a)
            except Exception:
                continue
        if len(valid)!=1:
            raise RenderQAStageError(f"RENDER_PROJECT_LOCK_CARDINALITY_INVALID: {len(valid)}")
        return valid[0]

    def _normalize_reviews(self, shots, plan, now):
        reviewer=str(plan.get("reviewer_id") or "").strip()
        reviewed_at=str(plan.get("reviewed_at") or now).strip()
        if not reviewer: raise RenderQAStageError("SHOT_QA_REVIEWER_REQUIRED")
        raw=plan.get("shot_reviews")
        if not isinstance(raw,list): raise RenderQAStageError("SHOT_QA_REVIEWS_REQUIRED")
        by_id={}
        active={x["id"]:x for x in shots}
        for item in raw:
            sid=str((item or {}).get("shot_id") or "").strip()
            if not sid or sid in by_id: raise RenderQAStageError(f"SHOT_QA_REVIEW_DUPLICATE_OR_INVALID: {sid}")
            if sid not in active: raise RenderQAStageError(f"SHOT_QA_REVIEW_UNKNOWN_SHOT: {sid}")
            findings=deepcopy((item or {}).get("findings") or [])
            if not isinstance(findings,list): raise RenderQAStageError(f"SHOT_QA_FINDINGS_INVALID: {sid}")
            by_id[sid]={
                "shot_ref":_oref(active[sid]),"reviewer_id":reviewer,"reviewed_at":reviewed_at,
                "findings":findings,"notes":str((item or {}).get("notes") or ""),
            }
        missing=sorted(set(active)-set(by_id))
        if missing: raise RenderQAStageError(f"SHOT_QA_REVIEW_COVERAGE_INCOMPLETE: {missing}")
        return [by_id[x["id"]] for x in shots]

    def _record_path(self,batch_id):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",batch_id).strip("._")
        if not safe: raise RenderQAStageError("RENDER_QA_BATCH_ID_INVALID")
        return self.workspace/"reviews"/"shot_qa"/(safe+".json")

    def _load_replay(self, eng, path:Path, plan_hash:str):
        if not path.exists(): return None
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("plan_sha256")!=plan_hash:
            raise RenderQAStageError("RENDER_QA_BATCH_ID_COLLISION")
        out=data.get("result") or {}
        # Exact refs are durable; ensure they still resolve after cold start.
        state=eng.snapshot()
        rr=out.get("render_output_ref") or {}
        if (rr.get("artifact_id"),int(rr.get("version",0))) not in state.artifacts:
            raise RenderQAStageError("RENDER_QA_REPLAY_OUTPUT_MISSING")
        return RenderQAStageResult(
            self.workspace,eng.project_state,data["batch_id"],out["production_lock_ref"],out["render_job_ref"],
            out["render_manifest_ref"],out["render_output_ref"],tuple(out.get("qa_report_refs") or []),
            out.get("qa_baseline_ref"),out["render_gate"],out["shot_qa_gate"],False,True,str(path.relative_to(self.workspace)),
        )

    def _matching_qa(self,state,shot_ref,output_ref,profile_sha):
        matches=[]
        for q in _active(state,"QA_REPORT"):
            if q.get("report_type")!="SHOT_QA" or q.get("scope")!=shot_ref or q.get("observed_artifact")!=output_ref: continue
            if (q.get("qa_profile") or {}).get("sha256")!=profile_sha: continue
            matches.append(q)
        return matches[-1] if matches else None

    def _resolve_prior_issues(self, eng, shot_ref, verification_report_ref):
        state=eng.snapshot();runtime=QARuntime(eng)
        candidates=[]
        for issue in _active(state,"QA_ISSUE"):
            if issue.get("target")!=shot_ref: continue
            if issue.get("qa_domain") not in {"SHOT","SHOT_QA"}: continue
            if issue.get("workflow_state") in {"RESOLVED","ACCEPTED_EXCEPTION","CLOSED"}: continue
            candidates.append(_oref(issue))
        for ref in candidates:
            runtime.resolve_issue(ref,verification_report_ref)

    def run(self, plan:dict[str,Any])->RenderQAStageResult:
        batch_id=str(plan.get("batch_id") or "").strip()
        if not batch_id: raise RenderQAStageError("RENDER_QA_BATCH_ID_REQUIRED")
        src=Path(str(plan.get("render_file") or ""))
        if not src.is_file(): raise RenderQAStageError(f"RENDER_FILE_NOT_FOUND: {src}")
        eng=self._load();state=eng.snapshot()
        if eng.project_state not in {"PRODUCTION_RENDER","SHOT_QA_PASSED"}:
            raise RenderQAStageError(f"RENDER_QA_STATE_INVALID: {eng.project_state}")
        project_locks=[a for a in _heads(state,"PRODUCTION_LOCK_MANIFEST") if (a.get("scope") or {}).get("type")=="PROJECT"]
        if not project_locks: raise RenderQAStageError("RENDER_PROJECT_LOCK_MISSING")
        lock=self._project_lock(eng,state);lock_ref=_aref(lock)
        projects=_active(state,"PROJECT");shots=_active(state,"SHOT")
        if len(projects)!=1 or not shots: raise RenderQAStageError("RENDER_QA_PROJECT_SHOT_CARDINALITY_INVALID")
        project_ref=_oref(projects[0]);reviews=self._normalize_reviews(shots,plan,eng.now())
        source_sha=_sha256_file(src);technical=_ffprobe(src)
        normalized={"batch_id":batch_id,"production_lock_ref":lock_ref,"render_source_sha256":source_sha,"reviews":reviews}
        plan_hash=sha256_json(normalized);record_path=self._record_path(batch_id)
        replay=self._load_replay(eng,record_path,plan_hash)
        if replay:return replay
        if eng.project_state!="PRODUCTION_RENDER":
            raise RenderQAStageError("RENDER_QA_REVIEW_RECORD_MISSING_AFTER_TRANSITION")

        # Store the exact render bytes immutably inside the workspace.
        ext=src.suffix.lower() or ".bin";dest=self.workspace/"media"/"renders"/(source_sha+ext)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if _sha256_file(dest)!=source_sha: raise RenderQAStageError("RENDER_MEDIA_IMMUTABLE_CONFLICT")
        else:
            shutil.copyfile(src,dest)
        media_uri=f"gmk://media/renders/{dest.name}"

        rr=RenderRuntime(eng)
        job=rr.queue_final(
            production_lock_ref=lock_ref,scope_type="PROJECT",scope_target=project_ref,
            compiled_payload={"mode":"LOCAL_FILE_FINAL_MASTER","source_media_sha256":source_sha,"build":30},
        )
        rendered=rr.execute(job,_LocalFinalAdapter(dest,media_uri,technical))
        if rendered.get("failed"):
            RuntimeStore(self.root,self.workspace).persist(eng)
            raise RenderQAStageError("FINAL_RENDER_TECHNICAL_VALIDATION_FAILED")
        output_ref=rendered["output_ref"] if rendered.get("output_ref") else None
        if output_ref is None:
            # Cache-hit manifests reuse the cached output reference.
            m=eng.snapshot().objects[(rendered["manifest_ref"]["id"],int(rendered["manifest_ref"]["version"]))]
            output_ref=deepcopy(m["outputs"][0])

        qa=QARuntime(eng);qrefs=[]
        for review in reviews:
            profile_sha=sha256_json(review);state_now=eng.snapshot()
            found=self._matching_qa(state_now,review["shot_ref"],output_ref,profile_sha)
            if found:
                qref=_oref(found)
            else:
                q=qa.evaluate(
                    report_type="SHOT_QA",scope=review["shot_ref"],observed_artifact=output_ref,
                    qa_profile={"config_id":"GMK_SHOT_QA_REVIEW","version":"1.0.0","sha256":profile_sha},
                    findings=review["findings"],
                )
                qref=q["report_ref"]
            qrefs.append(qref)
            current=eng.snapshot().objects[(qref["id"],int(qref["version"]))]
            if current.get("result")=="PASS": self._resolve_prior_issues(eng,review["shot_ref"],qref)

        baseline=qa.create_baseline(
            scope=project_ref,production_lock=lock_ref,render_manifest_ref=rendered["manifest_ref"],
            qa_report_refs=qrefs,output_refs=[output_ref],
        )
        state2=eng.snapshot();render_gate=eng.gates.evaluate_gate(state2,"RENDER",eng.now()).result
        shot_gate=eng.gates.evaluate_gate(state2,"SHOT_QA",eng.now()).result
        transitioned=False
        if render_gate=="PASS" and shot_gate=="PASS":
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                tx.transition_project_state("SHOT_QA_PASSED",actor_type="SYSTEM");tx.commit();transitioned=True
            except Exception:
                tx.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        result=RenderQAStageResult(
            self.workspace,eng.project_state,batch_id,lock_ref,rendered["job_ref"],rendered["manifest_ref"],output_ref,
            tuple(qrefs),baseline,render_gate,shot_gate,transitioned,False,str(record_path.relative_to(self.workspace)),
        )
        ledger={"batch_id":batch_id,"plan_sha256":plan_hash,"render_source_sha256":source_sha,"technical":technical,
                "reviews":reviews,"result":result.to_dict()}
        record_path.parent.mkdir(parents=True,exist_ok=True)
        payload=(json.dumps(ledger,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8")
        if record_path.exists() and record_path.read_bytes()!=payload: raise RenderQAStageError("RENDER_QA_REVIEW_RECORD_CONFLICT")
        if not record_path.exists(): record_path.write_bytes(payload)
        return result
