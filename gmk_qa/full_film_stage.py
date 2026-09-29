from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import re

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_semantics.model import sha256_json
from .runtime import QARuntime


class FullFilmQAStageError(RuntimeError):
    pass


def _oref(obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": obj["id"], "version": int(obj["version"])}


def _latest(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise FullFilmQAStageError("FULL_FILM_QA_LATEST_EMPTY")
    return max(items, key=lambda q: (
        str(q.get("evaluated_at") or ""),
        str(q.get("updated_at") or q.get("created_at") or ""),
        str(q.get("id") or ""),
    ))


def _active(state, object_type: str) -> list[dict[str, Any]]:
    out=[]
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type==object_type and entry.active_version is not None:
                out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out,key=lambda x:(int(x.get("order",0)),x["id"]))


_ALLOWED={"PASS","WARN","FAIL"}
_PASS_SPECS={
    "viewer_experience": {
        "report_type":"VIEWER_EXPERIENCE_QA",
        "qa_domain":"VIEWER_EXPERIENCE",
        "checks": {
            "narrative_clarity":"NARRATIVE",
            "pacing":"TIMING",
            "engagement":"NARRATIVE",
            "comprehension":"NARRATIVE",
            "emotional_coherence":"NARRATIVE",
        },
    },
    "production_integrity": {
        "report_type":"PRODUCTION_INTEGRITY_QA",
        "qa_domain":"PRODUCTION_INTEGRITY",
        "checks": {
            "scene_continuity":"SHOT_PLAN",
            "visual_consistency":"DESIGN",
            "audio_consistency":"VOICE",
            "timing_sync":"TIMING",
            "locked_decision_integrity":"SHOT_PLAN",
        },
    },
    "delivery_integrity": {
        "report_type":"DELIVERY_INTEGRITY_QA",
        "qa_domain":"DELIVERY_INTEGRITY",
        "checks": {
            "playback_integrity":"TECHNICAL_OUTPUT",
            "frame_integrity":"TECHNICAL_OUTPUT",
            "audio_integrity":"TECHNICAL_OUTPUT",
            "duration_integrity":"TECHNICAL_OUTPUT",
            "output_completeness":"TECHNICAL_OUTPUT",
        },
    },
}


@dataclass(frozen=True)
class FullFilmQAStageResult:
    workspace: Path
    project_state: str
    batch_id: str
    production_lock_ref: dict[str,Any]
    render_output_ref: dict[str,Any]
    scene_qa_report_refs: tuple[dict[str,Any],...]
    pass_report_refs: dict[str,Any]
    full_film_report_ref: dict[str,Any]
    full_film_package_ref: dict[str,Any]
    full_film_qa_gate: str
    transitioned: bool
    idempotent_replay: bool
    review_record_path: str

    def to_dict(self):
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,"batch_id":self.batch_id,
            "production_lock_ref":dict(self.production_lock_ref),"render_output_ref":dict(self.render_output_ref),
            "scene_qa_report_refs":[dict(x) for x in self.scene_qa_report_refs],
            "pass_report_refs":deepcopy(self.pass_report_refs),
            "full_film_report_ref":dict(self.full_film_report_ref),
            "full_film_package_ref":dict(self.full_film_package_ref),
            "full_film_qa_gate":self.full_film_qa_gate,"transitioned":self.transitioned,
            "idempotent_replay":self.idempotent_replay,"review_record_path":self.review_record_path,
        }


class FullFilmQAStageRuntime:
    """Build 032 explicit three-pass Full Film QA stage.

    The stage requires latest PASS Scene QA for every current Scene, all against one
    exact current final Render Output. It derives the exact Project Production Lock
    from that Render Output's Render Job, then requires explicit reviewer checklists
    for Viewer Experience, Production Integrity, and Delivery Integrity. A later PASS
    retest resolves prior Full Film QA issues and may advance SCENE_QA_PASSED to
    FULL_FILM_QA_PASSED through the frozen Gate.
    """

    def __init__(self,schema_root:Path,workspace:Path):
        self.root=Path(schema_root);self.workspace=Path(workspace)

    def _load(self):
        return ColdStartLoader(self.root,self.workspace).load().engine

    def _latest_scene_evidence(self,state):
        scenes=_active(state,"SCENE")
        if not scenes: raise FullFilmQAStageError("FULL_FILM_QA_ACTIVE_SCENES_MISSING")
        refs=[];render_ref=None
        all_reports=_active(state,"QA_REPORT")
        for scene in scenes:
            sref=_oref(scene)
            matches=[q for q in all_reports if q.get("report_type")=="SCENE_QA" and q.get("scope")==sref]
            if not matches: raise FullFilmQAStageError(f"FULL_FILM_QA_SCENE_QA_MISSING: {scene['id']}")
            q=_latest(matches)
            if q.get("result")!="PASS":
                raise FullFilmQAStageError(f"FULL_FILM_QA_SCENE_QA_NOT_PASS: {scene['id']}={q.get('result')}")
            observed=q.get("observed_artifact") or {}
            if not observed.get("artifact_id"): raise FullFilmQAStageError("FULL_FILM_QA_SCENE_OUTPUT_MISSING")
            if render_ref is None: render_ref=deepcopy(observed)
            elif observed!=render_ref: raise FullFilmQAStageError("FULL_FILM_QA_MULTIPLE_RENDER_OUTPUTS")
            refs.append(_oref(q))
        if render_ref is None or (render_ref.get("artifact_id"),int(render_ref.get("version",0))) not in state.artifacts:
            raise FullFilmQAStageError("FULL_FILM_QA_RENDER_OUTPUT_UNRESOLVED")
        return render_ref,refs

    def _production_lock_from_output(self,state,render_ref):
        output=state.artifacts[(render_ref["artifact_id"],int(render_ref["version"]))]
        job_ref=output.get("render_job_ref") or {}
        job=state.objects.get((job_ref.get("id"),int(job_ref.get("version",0))))
        if not job or job.get("object_type")!="RENDER_JOB": raise FullFilmQAStageError("FULL_FILM_QA_RENDER_JOB_UNRESOLVED")
        if job.get("render_level")!="FINAL" or (job.get("scope") or {}).get("type")!="PROJECT":
            raise FullFilmQAStageError("FULL_FILM_QA_RENDER_NOT_PROJECT_FINAL")
        lock=deepcopy(job.get("production_lock") or {})
        if not lock.get("artifact_id") or (lock.get("artifact_id"),int(lock.get("version",0))) not in state.artifacts:
            raise FullFilmQAStageError("FULL_FILM_QA_PRODUCTION_LOCK_UNRESOLVED")
        return lock

    def _normalize_pass(self,key,raw,reviewer,reviewed_at,scope):
        spec=_PASS_SPECS[key]
        if not isinstance(raw,dict): raise FullFilmQAStageError(f"FULL_FILM_QA_PASS_REVIEW_REQUIRED: {key}")
        checks=raw.get("checks")
        if not isinstance(checks,dict): raise FullFilmQAStageError(f"FULL_FILM_QA_CHECKS_REQUIRED: {key}")
        norm={};findings=deepcopy(raw.get("findings") or [])
        if not isinstance(findings,list): raise FullFilmQAStageError(f"FULL_FILM_QA_FINDINGS_INVALID: {key}")
        for check,category in spec["checks"].items():
            value=str(checks.get(check) or "").upper()
            if value not in _ALLOWED: raise FullFilmQAStageError(f"FULL_FILM_QA_CHECK_INVALID: {key}:{check}={value}")
            norm[check]=value
            if value!="PASS":
                findings.append({
                    "qa_domain":spec["qa_domain"],"severity":"MINOR" if value=="WARN" else "MAJOR",
                    "code":f"FULL_FILM_{key.upper()}_{check.upper()}_{value}",
                    "description":f"Full Film {key} checklist {check} reported {value}.",
                    "root_cause":{"state":"IDENTIFIED","category":category},"target":deepcopy(scope),
                })
        return {
            "reviewer_id":reviewer,"reviewed_at":reviewed_at,"checks":norm,"findings":findings,
            "notes":str(raw.get("notes") or ""),
        }

    def _normalize(self,plan,now,lock_ref,render_ref,scene_refs):
        reviewer=str(plan.get("reviewer_id") or "").strip();reviewed_at=str(plan.get("reviewed_at") or now).strip()
        if not reviewer: raise FullFilmQAStageError("FULL_FILM_QA_REVIEWER_REQUIRED")
        passes={k:self._normalize_pass(k,plan.get(k),reviewer,reviewed_at,lock_ref) for k in _PASS_SPECS}
        return {
            "batch_id":str(plan.get("batch_id") or "").strip(),"reviewer_id":reviewer,"reviewed_at":reviewed_at,
            "production_lock_ref":deepcopy(lock_ref),"render_output_ref":deepcopy(render_ref),
            "scene_qa_report_refs":deepcopy(scene_refs),"passes":passes,
        }

    def _record_path(self,batch_id):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",batch_id).strip("._")
        if not safe: raise FullFilmQAStageError("FULL_FILM_QA_BATCH_ID_INVALID")
        return self.workspace/"reviews"/"full_film_qa"/(safe+".json")

    def _load_replay(self,eng,path,plan_hash):
        if not path.exists(): return None
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("plan_sha256")!=plan_hash: raise FullFilmQAStageError("FULL_FILM_QA_BATCH_ID_COLLISION")
        out=data.get("result") or {};state=eng.snapshot()
        rr=out.get("render_output_ref") or {};pr=out.get("full_film_report_ref") or {};pa=out.get("full_film_package_ref") or {}
        if (rr.get("artifact_id"),int(rr.get("version",0))) not in state.artifacts: raise FullFilmQAStageError("FULL_FILM_QA_REPLAY_OUTPUT_MISSING")
        if (pr.get("id"),int(pr.get("version",0))) not in state.objects: raise FullFilmQAStageError("FULL_FILM_QA_REPLAY_REPORT_MISSING")
        if (pa.get("artifact_id"),int(pa.get("version",0))) not in state.artifacts: raise FullFilmQAStageError("FULL_FILM_QA_REPLAY_PACKAGE_MISSING")
        return FullFilmQAStageResult(
            self.workspace,eng.project_state,data["batch_id"],out["production_lock_ref"],out["render_output_ref"],
            tuple(out.get("scene_qa_report_refs") or []),deepcopy(out.get("pass_report_refs") or {}),
            out["full_film_report_ref"],out["full_film_package_ref"],out["full_film_qa_gate"],False,True,
            str(path.relative_to(self.workspace)),
        )

    def _resolve_prior_issues(self,eng,lock_ref,verification_report_ref):
        qa=QARuntime(eng);refs=[]
        for issue in _active(eng.snapshot(),"QA_ISSUE"):
            if issue.get("target")!=lock_ref: continue
            domain=str(issue.get("qa_domain") or "")
            if domain not in {"VIEWER_EXPERIENCE","PRODUCTION_INTEGRITY","DELIVERY_INTEGRITY","FULL_FILM","FULL_FILM_QA"}: continue
            if issue.get("workflow_state") in {"RESOLVED","ACCEPTED_EXCEPTION","WONT_FIX"}: continue
            refs.append(_oref(issue))
        for ref in refs: qa.resolve_issue(ref,verification_report_ref)

    def run(self,plan:dict[str,Any])->FullFilmQAStageResult:
        batch_id=str(plan.get("batch_id") or "").strip()
        if not batch_id: raise FullFilmQAStageError("FULL_FILM_QA_BATCH_ID_REQUIRED")
        eng=self._load();state=eng.snapshot()
        if eng.project_state not in {"SCENE_QA_PASSED","FULL_FILM_QA_PASSED"}:
            raise FullFilmQAStageError(f"FULL_FILM_QA_STATE_INVALID: {eng.project_state}")
        for gid in ("RENDER","SHOT_QA","SCENE_QA"):
            result=eng.gates.evaluate_gate(state,gid,eng.now()).result
            if result!="PASS": raise FullFilmQAStageError(f"FULL_FILM_QA_PREREQUISITE_GATE_INVALID: {gid}={result}")
        render_ref,scene_refs=self._latest_scene_evidence(state)
        lock_ref=self._production_lock_from_output(state,render_ref)
        normalized=self._normalize(plan,eng.now(),lock_ref,render_ref,scene_refs)
        plan_hash=sha256_json(normalized);record_path=self._record_path(batch_id)
        replay=self._load_replay(eng,record_path,plan_hash)
        if replay:return replay
        if eng.project_state!="SCENE_QA_PASSED": raise FullFilmQAStageError("FULL_FILM_QA_REVIEW_RECORD_MISSING_AFTER_TRANSITION")

        p=normalized["passes"];profiles={
            k:{"config_id":f"GMK_{_PASS_SPECS[k]['report_type']}_REVIEW","version":"1.0.0","sha256":sha256_json(p[k])}
            for k in _PASS_SPECS
        }
        full_profile={"config_id":"GMK_FULL_FILM_QA_REVIEW","version":"1.0.0","sha256":sha256_json({"passes":profiles,"scenes":scene_refs,"output":render_ref})}
        qa=QARuntime(eng)
        full=qa.evaluate_full_film(
            production_lock=lock_ref,master_output=render_ref,
            viewer_findings=p["viewer_experience"]["findings"],
            production_findings=p["production_integrity"]["findings"],
            delivery_integrity_findings=p["delivery_integrity"]["findings"],
            qa_profiles={
                "viewer":profiles["viewer_experience"],
                "production":profiles["production_integrity"],
                "delivery_integrity":profiles["delivery_integrity"],
                "aggregate":full_profile,
            },
        )
        if full["result"]=="PASS": self._resolve_prior_issues(eng,lock_ref,full["report_ref"])
        gate=eng.gates.evaluate_gate(eng.snapshot(),"FULL_FILM_QA",eng.now()).result;transitioned=False
        if gate=="PASS":
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                tx.transition_project_state("FULL_FILM_QA_PASSED",actor_type="SYSTEM");tx.commit();transitioned=True
            except Exception:
                tx.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        result=FullFilmQAStageResult(
            self.workspace,eng.project_state,batch_id,lock_ref,render_ref,tuple(scene_refs),deepcopy(full["pass_reports"]),
            full["report_ref"],full["package_ref"],gate,transitioned,False,str(record_path.relative_to(self.workspace)),
        )
        ledger={"batch_id":batch_id,"plan_sha256":plan_hash,"normalized_review":normalized,"result":result.to_dict()}
        record_path.parent.mkdir(parents=True,exist_ok=True)
        payload=(json.dumps(ledger,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8")
        if record_path.exists() and record_path.read_bytes()!=payload: raise FullFilmQAStageError("FULL_FILM_QA_REVIEW_RECORD_CONFLICT")
        if not record_path.exists(): record_path.write_bytes(payload)
        return result
