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


class SceneQAStageError(RuntimeError):
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


def _plan_shots(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out=[]
    for item in plan.get("shots") or []:
        ref=item.get("shot_ref") if isinstance(item,dict) and "shot_ref" in item else item
        if isinstance(ref,dict) and ref.get("id") and ref.get("version"):
            out.append({"id":ref["id"],"version":int(ref["version"])})
    return out


def _latest(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items: raise SceneQAStageError("SCENE_QA_LATEST_EMPTY")
    return max(items,key=lambda q:(
        str(q.get("evaluated_at") or ""),
        str(q.get("updated_at") or q.get("created_at") or ""),
        str(q.get("id") or ""),
    ))


_REQUIRED_CHECKS=(
    "shot_continuity",
    "visual_continuity",
    "audio_continuity",
    "narrative_flow",
    "coverage",
)
_ALLOWED_CHECK_RESULTS={"PASS","WARN","FAIL"}
_CHECK_ROOT_CAUSE={
    "shot_continuity":"SHOT_PLAN",
    "visual_continuity":"DESIGN",
    "audio_continuity":"VOICE",
    "narrative_flow":"NARRATIVE",
    "coverage":"SEGMENT",
}


@dataclass(frozen=True)
class SceneQAStageResult:
    workspace: Path
    project_state: str
    batch_id: str
    render_output_ref: dict[str, Any]
    scene_qa_report_refs: tuple[dict[str, Any], ...]
    scene_qa_gate: str
    transitioned: bool
    idempotent_replay: bool
    review_record_path: str

    def to_dict(self):
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,"batch_id":self.batch_id,
            "render_output_ref":dict(self.render_output_ref),
            "scene_qa_report_refs":[dict(x) for x in self.scene_qa_report_refs],
            "scene_qa_gate":self.scene_qa_gate,"transitioned":self.transitioned,
            "idempotent_replay":self.idempotent_replay,"review_record_path":self.review_record_path,
        }


class SceneQAStageRuntime:
    """Build 031 explicit Scene QA aggregation stage.

    Scene QA is allowed only after Shot QA has already passed. Every active Scene
    must receive an explicit review checklist and every Shot referenced by its
    current Scene Plan must have a latest PASS Shot QA report against the same
    current Final Render output. Historical failed Scene QA may be superseded by
    a later PASS retest; verified prior Scene issues are then resolved explicitly.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root=Path(schema_root);self.workspace=Path(workspace)

    def _load(self):
        return ColdStartLoader(self.root,self.workspace).load().engine

    def _scene_graph(self,state):
        scenes=_active(state,"SCENE")
        shots={x["id"]:x for x in _active(state,"SHOT")}
        plans=_heads(state,"SCENE_PLAN")
        by_scene={(p.get("scene_ref") or {}).get("id"):p for p in plans}
        if not scenes: raise SceneQAStageError("SCENE_QA_ACTIVE_SCENES_MISSING")
        out=[]
        for scene in scenes:
            plan=by_scene.get(scene["id"])
            if not plan: raise SceneQAStageError(f"SCENE_QA_SCENE_PLAN_MISSING: {scene['id']}")
            sref=plan.get("scene_ref") or {}
            if (sref.get("id"),int(sref.get("version",0)))!=(scene["id"],int(scene["version"])):
                raise SceneQAStageError(f"SCENE_QA_SCENE_PLAN_STALE: {scene['id']}")
            shot_refs=_plan_shots(plan)
            if not shot_refs: raise SceneQAStageError(f"SCENE_QA_SCENE_SHOTS_MISSING: {scene['id']}")
            scene_shots=[]
            for ref in shot_refs:
                shot=shots.get(ref["id"])
                if not shot or int(shot["version"])!=int(ref["version"]):
                    raise SceneQAStageError(f"SCENE_QA_SHOT_NOT_CURRENT: {ref}")
                scene_shots.append(shot)
            out.append((scene,plan,scene_shots))
        return out

    def _latest_shot_qa(self,state,shot_ref):
        matches=[q for q in _active(state,"QA_REPORT") if q.get("report_type")=="SHOT_QA" and q.get("scope")==shot_ref]
        if not matches: raise SceneQAStageError(f"SCENE_QA_SHOT_QA_MISSING: {shot_ref}")
        return _latest(matches)

    def _shot_evidence(self,state,graph):
        render_ref=None;by_scene={}
        for scene,plan,shots in graph:
            qrefs=[]
            for shot in shots:
                q=self._latest_shot_qa(state,_oref(shot))
                if q.get("result")!="PASS":
                    raise SceneQAStageError(f"SCENE_QA_SHOT_QA_NOT_PASS: {shot['id']}={q.get('result')}")
                observed=q.get("observed_artifact") or {}
                if not observed.get("artifact_id"):
                    raise SceneQAStageError(f"SCENE_QA_SHOT_QA_OUTPUT_MISSING: {shot['id']}")
                if render_ref is None: render_ref=deepcopy(observed)
                elif observed!=render_ref:
                    raise SceneQAStageError("SCENE_QA_MULTIPLE_RENDER_OUTPUTS")
                qrefs.append(_oref(q))
            by_scene[scene["id"]]={"shot_refs":[_oref(x) for x in shots],"shot_qa_report_refs":qrefs}
        if render_ref is None: raise SceneQAStageError("SCENE_QA_RENDER_OUTPUT_MISSING")
        if (render_ref.get("artifact_id"),int(render_ref.get("version",0))) not in state.artifacts:
            raise SceneQAStageError("SCENE_QA_RENDER_OUTPUT_UNRESOLVED")
        return render_ref,by_scene

    def _normalize_reviews(self,graph,evidence,plan,now):
        reviewer=str(plan.get("reviewer_id") or "").strip()
        reviewed_at=str(plan.get("reviewed_at") or now).strip()
        if not reviewer: raise SceneQAStageError("SCENE_QA_REVIEWER_REQUIRED")
        raw=plan.get("scene_reviews")
        if not isinstance(raw,list): raise SceneQAStageError("SCENE_QA_REVIEWS_REQUIRED")
        scenes={s["id"]:s for s,_,_ in graph};by_id={}
        for item in raw:
            item=item or {};sid=str(item.get("scene_id") or "").strip()
            if not sid or sid in by_id: raise SceneQAStageError(f"SCENE_QA_REVIEW_DUPLICATE_OR_INVALID: {sid}")
            if sid not in scenes: raise SceneQAStageError(f"SCENE_QA_REVIEW_UNKNOWN_SCENE: {sid}")
            checks=item.get("checks")
            if not isinstance(checks,dict): raise SceneQAStageError(f"SCENE_QA_CHECKS_REQUIRED: {sid}")
            normalized_checks={}
            for key in _REQUIRED_CHECKS:
                value=str(checks.get(key) or "").upper()
                if value not in _ALLOWED_CHECK_RESULTS:
                    raise SceneQAStageError(f"SCENE_QA_CHECK_INVALID: {sid}:{key}={value}")
                normalized_checks[key]=value
            findings=deepcopy(item.get("findings") or [])
            if not isinstance(findings,list): raise SceneQAStageError(f"SCENE_QA_FINDINGS_INVALID: {sid}")
            for key,value in normalized_checks.items():
                if value=="PASS": continue
                findings.append({
                    "qa_domain":"SCENE",
                    "severity":"MINOR" if value=="WARN" else "MAJOR",
                    "code":f"SCENE_{key.upper()}_{value}",
                    "description":f"Scene checklist {key} reported {value}.",
                    "root_cause":{"state":"IDENTIFIED","category":_CHECK_ROOT_CAUSE[key]},
                    "target":_oref(scenes[sid]),
                })
            by_id[sid]={
                "scene_ref":_oref(scenes[sid]),"reviewer_id":reviewer,"reviewed_at":reviewed_at,
                "checks":normalized_checks,"findings":findings,"notes":str(item.get("notes") or ""),
                "shot_refs":deepcopy(evidence[sid]["shot_refs"]),
                "shot_qa_report_refs":deepcopy(evidence[sid]["shot_qa_report_refs"]),
            }
        missing=sorted(set(scenes)-set(by_id))
        if missing: raise SceneQAStageError(f"SCENE_QA_REVIEW_COVERAGE_INCOMPLETE: {missing}")
        return [by_id[s["id"]] for s,_,_ in graph]

    def _record_path(self,batch_id):
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",batch_id).strip("._")
        if not safe: raise SceneQAStageError("SCENE_QA_BATCH_ID_INVALID")
        return self.workspace/"reviews"/"scene_qa"/(safe+".json")

    def _load_replay(self,eng,path,plan_hash):
        if not path.exists(): return None
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("plan_sha256")!=plan_hash: raise SceneQAStageError("SCENE_QA_BATCH_ID_COLLISION")
        out=data.get("result") or {};state=eng.snapshot()
        rr=out.get("render_output_ref") or {}
        if (rr.get("artifact_id"),int(rr.get("version",0))) not in state.artifacts:
            raise SceneQAStageError("SCENE_QA_REPLAY_OUTPUT_MISSING")
        for q in out.get("scene_qa_report_refs") or []:
            if (q.get("id"),int(q.get("version",0))) not in state.objects:
                raise SceneQAStageError("SCENE_QA_REPLAY_REPORT_MISSING")
        return SceneQAStageResult(
            self.workspace,eng.project_state,data["batch_id"],out["render_output_ref"],
            tuple(out.get("scene_qa_report_refs") or []),out["scene_qa_gate"],False,True,
            str(path.relative_to(self.workspace)),
        )

    def _matching_scene_qa(self,state,review,render_ref,profile_sha):
        matches=[]
        for q in _active(state,"QA_REPORT"):
            if q.get("report_type")!="SCENE_QA" or q.get("scope")!=review["scene_ref"]: continue
            if q.get("observed_artifact")!=render_ref: continue
            if (q.get("qa_profile") or {}).get("sha256")!=profile_sha: continue
            matches.append(q)
        return _latest(matches) if matches else None

    def _resolve_prior_issues(self,eng,scene_ref,verification_report_ref):
        state=eng.snapshot();qa=QARuntime(eng);refs=[]
        for issue in _active(state,"QA_ISSUE"):
            if issue.get("target")!=scene_ref: continue
            if issue.get("qa_domain") not in {"SCENE","SCENE_QA"}: continue
            if issue.get("workflow_state") in {"RESOLVED","ACCEPTED_EXCEPTION","WONT_FIX","CLOSED"}: continue
            refs.append(_oref(issue))
        for ref in refs: qa.resolve_issue(ref,verification_report_ref)

    def run(self,plan:dict[str,Any])->SceneQAStageResult:
        batch_id=str(plan.get("batch_id") or "").strip()
        if not batch_id: raise SceneQAStageError("SCENE_QA_BATCH_ID_REQUIRED")
        eng=self._load();state=eng.snapshot()
        if eng.project_state not in {"SHOT_QA_PASSED","SCENE_QA_PASSED"}:
            raise SceneQAStageError(f"SCENE_QA_STATE_INVALID: {eng.project_state}")
        shot_gate=eng.gates.evaluate_gate(state,"SHOT_QA",eng.now()).result
        render_gate=eng.gates.evaluate_gate(state,"RENDER",eng.now()).result
        if shot_gate!="PASS" or render_gate!="PASS":
            raise SceneQAStageError(f"SCENE_QA_PREREQUISITE_GATE_INVALID: RENDER={render_gate}, SHOT_QA={shot_gate}")
        graph=self._scene_graph(state);render_ref,evidence=self._shot_evidence(state,graph)
        reviews=self._normalize_reviews(graph,evidence,plan,eng.now())
        normalized={"batch_id":batch_id,"render_output_ref":render_ref,"reviews":reviews}
        plan_hash=sha256_json(normalized);record_path=self._record_path(batch_id)
        replay=self._load_replay(eng,record_path,plan_hash)
        if replay:return replay
        if eng.project_state!="SHOT_QA_PASSED": raise SceneQAStageError("SCENE_QA_REVIEW_RECORD_MISSING_AFTER_TRANSITION")

        qa=QARuntime(eng);qrefs=[]
        for review in reviews:
            profile_sha=sha256_json(review);current=self._matching_scene_qa(eng.snapshot(),review,render_ref,profile_sha)
            if current:qref=_oref(current)
            else:
                q=qa.evaluate(
                    report_type="SCENE_QA",scope=review["scene_ref"],observed_artifact=render_ref,
                    qa_profile={"config_id":"GMK_SCENE_QA_REVIEW","version":"1.0.0","sha256":profile_sha},
                    findings=review["findings"],
                );qref=q["report_ref"]
            qrefs.append(qref)
            qobj=eng.snapshot().objects[(qref["id"],int(qref["version"]))]
            if qobj.get("result")=="PASS": self._resolve_prior_issues(eng,review["scene_ref"],qref)

        gate=eng.gates.evaluate_gate(eng.snapshot(),"SCENE_QA",eng.now()).result;transitioned=False
        if gate=="PASS":
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                tx.transition_project_state("SCENE_QA_PASSED",actor_type="SYSTEM");tx.commit();transitioned=True
            except Exception:
                tx.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        result=SceneQAStageResult(
            self.workspace,eng.project_state,batch_id,render_ref,tuple(qrefs),gate,transitioned,False,
            str(record_path.relative_to(self.workspace)),
        )
        ledger={"batch_id":batch_id,"plan_sha256":plan_hash,"render_output_ref":render_ref,"reviews":reviews,"result":result.to_dict()}
        record_path.parent.mkdir(parents=True,exist_ok=True)
        payload=(json.dumps(ledger,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode("utf-8")
        if record_path.exists() and record_path.read_bytes()!=payload: raise SceneQAStageError("SCENE_QA_REVIEW_RECORD_CONFLICT")
        if not record_path.exists(): record_path.write_bytes(payload)
        return result
