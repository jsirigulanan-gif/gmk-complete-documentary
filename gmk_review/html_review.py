from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from html import escape
import hashlib

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore


class HTMLReviewRuntimeError(RuntimeError):
    pass


def _oref(o):
    return {"id": o["id"], "version": int(o["version"])}


def _aref(a):
    return {
        "artifact_id": a["artifact_id"],
        "artifact_type": a["artifact_type"],
        "version": int(a["version"]),
        "sha256": a["sha256"],
    }


def _active(state, object_type):
    out = []
    for reg in state.registries.values():
        for entry in reg.entries.values():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(entry.object_id, int(entry.active_version))])
    return sorted(out, key=lambda x: x["id"])


def _heads(state, artifact_type):
    out = []
    for aid, entry in state.artifact_registry.entries.items():
        if entry.artifact_type != artifact_type:
            continue
        out.append(state.artifacts[(aid, int(entry.head_version))])
    return sorted(out, key=lambda x: x["artifact_id"])


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _plan_shot_refs(plan):
    refs = []
    for item in plan.get("shots") or []:
        ref = item.get("shot_ref") if isinstance(item, dict) and "shot_ref" in item else item
        if not isinstance(ref, dict) or not ref.get("id") or not ref.get("version"):
            raise HTMLReviewRuntimeError(f"HTML_REVIEW_SCENE_PLAN_SHOT_INVALID: {plan['artifact_id']}")
        refs.append({"id": ref["id"], "version": int(ref["version"])})
    if not refs:
        raise HTMLReviewRuntimeError(f"HTML_REVIEW_SCENE_PLAN_EMPTY: {plan['artifact_id']}")
    return refs


def _render_html(scene, plan, shots, state) -> str:
    cards = []
    for shot_ref in shots:
        shot = state.objects.get((shot_ref["id"], int(shot_ref["version"])))
        if not shot:
            raise HTMLReviewRuntimeError(f"HTML_REVIEW_SHOT_MISSING: {shot_ref['id']}@{shot_ref['version']}")
        timing = shot.get("timing") or {}
        start = (timing.get("start") or {}).get("seconds")
        end = (timing.get("end") or {}).get("seconds")
        layers = ", ".join(f"{r['id']}@{r['version']}" for r in shot.get("layer_refs") or [])
        cues = ", ".join(f"{r['id']}@{r['version']}" for r in shot.get("cue_refs") or [])
        cards.append(f"""
        <article class="shot">
          <h2>{escape(shot['id'])} <small>v{int(shot['version'])}</small></h2>
          <p class="time">{escape(str(start))}s → {escape(str(end))}s</p>
          <p><strong>Visual job:</strong> {escape(str(shot.get('visual_job') or ''))}</p>
          <p><strong>Viewer takeaway:</strong> {escape(str(shot.get('viewer_takeaway') or ''))}</p>
          <p><strong>Strategy:</strong> {escape(str(shot.get('visual_strategy') or ''))}</p>
          <p><strong>Layers:</strong> {escape(layers)}</p>
          <p><strong>Cues:</strong> {escape(cues)}</p>
        </article>""")
    scene_title = scene.get("title") or scene.get("name") or scene["id"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GMK Scene Review — {escape(str(scene_title))}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;background:#111;color:#eee}}
header{{border-bottom:1px solid #444;margin-bottom:24px}} .shot{{border:1px solid #444;border-radius:12px;padding:18px;margin:14px 0;background:#181818}}
small,.time{{color:#aaa}} strong{{color:#fff}} code{{color:#ddd}}
</style></head><body>
<header><h1>{escape(str(scene_title))}</h1><p>Scene {escape(scene['id'])} · Plan {escape(plan['artifact_id'])}@{int(plan['version'])}</p></header>
{''.join(cards)}
</body></html>"""


@dataclass(frozen=True)
class HTMLReviewPrepareResult:
    workspace: Path
    project_state: str
    preview_count: int
    review_package_count: int
    preview_refs: tuple
    review_package_refs: tuple
    gate_result: str
    transitioned: bool
    idempotent_replay: bool

    def to_dict(self):
        return {
            "workspace": str(self.workspace),
            "project_state": self.project_state,
            "preview_count": self.preview_count,
            "review_package_count": self.review_package_count,
            "preview_refs": list(self.preview_refs),
            "review_package_refs": list(self.review_package_refs),
            "gate_result": self.gate_result,
            "transitioned": self.transitioned,
            "idempotent_replay": self.idempotent_replay,
        }


@dataclass(frozen=True)
class HTMLReviewDecisionResult:
    workspace: Path
    project_state: str
    decision_count: int
    approved_count: int
    preview_count: int
    approval_refs: tuple
    gate_result: str
    transitioned: bool
    idempotent_replay: bool

    def to_dict(self):
        return {
            "workspace": str(self.workspace),
            "project_state": self.project_state,
            "decision_count": self.decision_count,
            "approved_count": self.approved_count,
            "preview_count": self.preview_count,
            "approval_refs": list(self.approval_refs),
            "gate_result": self.gate_result,
            "transitioned": self.transitioned,
            "idempotent_replay": self.idempotent_replay,
        }


class HTMLReviewRuntime:
    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    def _load(self):
        return ColdStartLoader(self.root, self.workspace).load().engine

    def _current_pairs(self, state):
        scenes = _active(state, "SCENE")
        plans = _heads(state, "SCENE_PLAN")
        by_scene = {(p.get("scene_ref") or {}).get("id"): p for p in plans}
        if not scenes or len(by_scene) != len(scenes):
            raise HTMLReviewRuntimeError("HTML_REVIEW_SCENE_PLAN_COVERAGE_INVALID")
        return [(s, by_scene[s["id"]]) for s in scenes]

    def _existing_complete(self, state, pairs):
        previews = _heads(state, "SCENE_PREVIEW")
        packages = _heads(state, "REVIEW_PACKAGE")
        p_by_scene = {(p.get("scene_ref") or {}).get("id"): p for p in previews}
        r_by_preview = {((r.get("scene_preview") or {}).get("artifact_id"), int((r.get("scene_preview") or {}).get("version", 0))): r for r in packages}
        out_p, out_r = [], []
        for scene, plan in pairs:
            pv = p_by_scene.get(scene["id"])
            if not pv:
                return None
            pref = pv.get("scene_plan") or {}
            if pref.get("artifact_id") != plan["artifact_id"] or int(pref.get("version", 0)) != int(plan["version"]):
                return None
            exact_shots = _plan_shot_refs(plan)
            if pv.get("shots") != exact_shots:
                return None
            rp = r_by_preview.get((pv["artifact_id"], int(pv["version"])))
            if not rp:
                return None
            out_p.append(pv); out_r.append(rp)
        return out_p, out_r

    def prepare(self) -> HTMLReviewPrepareResult:
        eng = self._load(); state = eng.snapshot()
        if eng.project_state not in {"SHOT_PLAN_READY", "HTML_REVIEW", "HTML_APPROVED"}:
            raise HTMLReviewRuntimeError(f"HTML_REVIEW_STATE_INVALID: expected SHOT_PLAN_READY/HTML_REVIEW/HTML_APPROVED, found {eng.project_state}")
        pairs = self._current_pairs(state)
        existing = self._existing_complete(state, pairs)
        if existing:
            pvs, rps = existing
            gate = eng.gates.evaluate_gate(state, "HTML_REVIEW", eng.now()).result
            return HTMLReviewPrepareResult(self.workspace, eng.project_state, len(pvs), len(rps), tuple(_aref(x) for x in pvs), tuple(_aref(x) for x in rps), gate, False, True)
        if eng.project_state != "SHOT_PLAN_READY":
            raise HTMLReviewRuntimeError("HTML_REVIEW_REPLAY_INCOMPLETE")

        review_dir = self.workspace / "review" / "html"
        review_dir.mkdir(parents=True, exist_ok=True)
        tx = eng.begin(expected_manifest_version=eng.manifest_version, expected_registry_versions=eng.registry_versions())
        preview_refs, package_refs = [], []
        try:
            for scene, plan in pairs:
                shots = _plan_shot_refs(plan)
                html = _render_html(scene, plan, shots, state)
                out = review_dir / f"{scene['id']}_scene_review.html"
                out.write_text(html, encoding="utf-8")
                digest = _sha256(out)
                pv = tx.create_artifact("SCENE_PREVIEW", {
                    "scene_ref": _oref(scene),
                    "scene_plan": _aref(plan),
                    "shots": shots,
                    "preview": {
                        "format": "HTML",
                        "workspace_path": str(out.relative_to(self.workspace)),
                        "sha256": digest,
                        "size_bytes": out.stat().st_size,
                        "purpose": "HUMAN_SCENE_REVIEW",
                    },
                    "extensions": {"html_review_runtime": {"generated_from_exact_scene_plan": True}},
                }, origin_refs=[_oref(scene), _aref(plan), *shots])
                pv_obj = tx.staged.artifacts[(pv["artifact_id"], pv["version"])]
                rp = tx.create_artifact("REVIEW_PACKAGE", {
                    "scope": {"type": "SCENE", "scene_ref": _oref(scene)},
                    "scene_preview": _aref(pv_obj),
                    "scene_plan": _aref(plan),
                    "shots": shots,
                    "extensions": {"html_review_runtime": {"requires_human_decision": True, "html_sha256": digest}},
                }, origin_refs=[_aref(pv_obj), _aref(plan), *shots])
                preview_refs.append(pv); package_refs.append(rp)
            tx.transition_project_state("HTML_REVIEW", actor_type="SYSTEM", human_confirmed=False)
            tx.commit()
        except Exception:
            tx.discard(); raise
        RuntimeStore(self.root, self.workspace).persist(eng)
        final = eng.snapshot(); pvs = _heads(final, "SCENE_PREVIEW"); rps = _heads(final, "REVIEW_PACKAGE")
        gate = eng.gates.evaluate_gate(final, "HTML_REVIEW", eng.now()).result
        return HTMLReviewPrepareResult(self.workspace, eng.project_state, len(pvs), len(rps), tuple(_aref(x) for x in pvs), tuple(_aref(x) for x in rps), gate, True, False)

    def decide(self, plan: dict) -> HTMLReviewDecisionResult:
        actor_id = str(plan.get("actor_id") or "").strip()
        if not actor_id:
            raise HTMLReviewRuntimeError("HTML_REVIEW_HUMAN_ACTOR_REQUIRED")
        raw = plan.get("decisions")
        if raw is None:
            decision = str(plan.get("decision") or "").upper()
            if decision not in {"APPROVED", "REJECTED"}:
                raise HTMLReviewRuntimeError("HTML_REVIEW_DECISION_INVALID")
            raw = [{"scene_id": plan.get("scene_id"), "decision": decision}]
        if not isinstance(raw, list) or not raw:
            raise HTMLReviewRuntimeError("HTML_REVIEW_DECISIONS_REQUIRED")

        eng = self._load(); state = eng.snapshot()
        if eng.project_state not in {"HTML_REVIEW", "HTML_APPROVED"}:
            raise HTMLReviewRuntimeError(f"HTML_REVIEW_DECISION_STATE_INVALID: {eng.project_state}")
        pairs = self._current_pairs(state)
        existing = self._existing_complete(state, pairs)
        if not existing:
            raise HTMLReviewRuntimeError("HTML_REVIEW_PACKAGE_INCOMPLETE")
        previews, packages = existing
        preview_by_scene = {(p.get("scene_ref") or {}).get("id"): p for p in previews}
        package_by_preview = {((r.get("scene_preview") or {}).get("artifact_id"), int((r.get("scene_preview") or {}).get("version",0))): r for r in packages}

        normalized = []
        if len(raw)==1 and not raw[0].get("scene_id"):
            for sid in sorted(preview_by_scene): normalized.append({"scene_id":sid,"decision":str(raw[0]["decision"]).upper()})
        else:
            normalized = [{"scene_id":str(x.get("scene_id") or ""),"decision":str(x.get("decision") or "").upper()} for x in raw]
        for x in normalized:
            if x["scene_id"] not in preview_by_scene: raise HTMLReviewRuntimeError(f"HTML_REVIEW_SCENE_UNKNOWN: {x['scene_id']}")
            if x["decision"] not in {"APPROVED","REJECTED"}: raise HTMLReviewRuntimeError("HTML_REVIEW_DECISION_INVALID")

        approvals = _active(state, "APPROVAL")
        to_create=[]; replay=True
        for x in normalized:
            pv=preview_by_scene[x["scene_id"]]; rp=package_by_preview[(pv["artifact_id"],int(pv["version"]))]
            target=_aref(pv); rc=_aref(rp)
            found=next((a for a in approvals if a.get("approval_class")=="SCENE_PREVIEW" and a.get("target")==target and a.get("review_context")==rc and a.get("decision")==x["decision"] and (a.get("actor") or {}).get("actor_id")==actor_id),None)
            if not found:
                replay=False; to_create.append((x,pv,rp))

        created=[]
        if to_create:
            tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                for x,pv,rp in to_create:
                    ar=tx.create_approval({
                        "approval_class":"SCENE_PREVIEW","target":_aref(pv),"review_context":_aref(rp),
                        "decision":x["decision"],"actor":{"type":"HUMAN","actor_id":actor_id},"decided_at":eng.now()
                    })
                    created.append(ar)
                tx.commit()
            except Exception:
                tx.discard(); raise
            RuntimeStore(self.root,self.workspace).persist(eng)

        state2=eng.snapshot(); gate=eng.gates.evaluate_gate(state2,"HTML_REVIEW",eng.now()).result
        transitioned=False
        if eng.project_state=="HTML_REVIEW" and gate in {"PASS","WARN"}:
            tx2=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
            try:
                tx2.transition_project_state("HTML_APPROVED",actor_type="HUMAN",human_confirmed=True);tx2.commit();transitioned=True
            except Exception:
                tx2.discard();raise
            RuntimeStore(self.root,self.workspace).persist(eng)
            state2=eng.snapshot(); gate=eng.gates.evaluate_gate(state2,"HTML_REVIEW",eng.now()).result
        approvals2=_active(state2,"APPROVAL")
        current_targets={tuple(sorted(_aref(p).items())) for p in previews}
        approved=0
        for p in previews:
            target=_aref(p)
            if any(a.get("approval_class")=="SCENE_PREVIEW" and a.get("decision")=="APPROVED" and a.get("target")==target for a in approvals2): approved+=1
        relevant=[_oref(a) for a in approvals2 if a.get("approval_class")=="SCENE_PREVIEW" and tuple(sorted((a.get("target") or {}).items())) in current_targets]
        return HTMLReviewDecisionResult(self.workspace,eng.project_state,len(normalized),approved,len(previews),tuple(relevant),gate,transitioned,replay and not transitioned)
