from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state.errors import StateEngineError


class VisualRequirementsError(RuntimeError):
    pass


def _sha256_json(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _active_objects(state, object_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type != object_type or entry.active_version is None:
                continue
            out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: x["id"])


def _artifact_ref(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": a["artifact_id"],
        "artifact_type": a["artifact_type"],
        "version": int(a["version"]),
        "sha256": a["sha256"],
    }


def _object_ref(o: dict[str, Any]) -> dict[str, Any]:
    return {"id": o["id"], "version": int(o["version"])}


@dataclass(frozen=True)
class VisualRequirementsResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    source_narrative_spine_ref: dict[str, Any]
    prior_beat_refs: tuple[dict[str, Any], ...]
    beat_refs: tuple[dict[str, Any], ...]
    requirement_count: int
    priority_counts: dict[str, int]
    asset_need_counts: dict[str, int]
    gate_result: str
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "batch_id": self.batch_id,
            "project_state": self.project_state,
            "manifest_version": self.manifest_version,
            "source_narrative_spine_ref": self.source_narrative_spine_ref,
            "prior_beat_refs": list(self.prior_beat_refs),
            "beat_refs": list(self.beat_refs),
            "requirement_count": self.requirement_count,
            "priority_counts": dict(self.priority_counts),
            "asset_need_counts": dict(self.asset_need_counts),
            "gate_result": self.gate_result,
            "idempotent_replay": self.idempotent_replay,
        }


class VisualRequirementsRuntime:
    """Attach exact visual evidence requirements to the current rough Narrative Beats.

    This stage does not search for assets and does not select footage. It states what the
    viewer must see and understand, the allowed match modes, the media/reference classes
    needed, and the priority. Asset Recon starts only after this stage passes its Gate.
    """

    MATCHES = {"DIRECT", "SUPPORTING", "EXPLAINER"}
    ASSET_NEEDS = {"VIDEO", "STILL", "DOCUMENT", "TECHNICAL_REFERENCE", "THREE_D_REFERENCE"}
    PRIORITIES = {"CRITICAL", "MAJOR", "STANDARD", "SUPPORTING"}
    PLACEHOLDER_TOKENS = {"TBD", "TODO", "PLACEHOLDER", "FILLER", "TEMP_ASSET"}

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    @staticmethod
    def _rough_key(beat: dict[str, Any]) -> str:
        ext = (beat.get("extensions") or {}).get("rough_narrative") or {}
        key = ext.get("key")
        if not key:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_BEAT_KEY_MISSING: {beat.get('id')}@{beat.get('version')}")
        return str(key)

    @staticmethod
    def _validate_spine_ref(state, requested: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
        heads: dict[str, dict[str, Any]] = {}
        for (aid, version), artifact in state.artifacts.items():
            if artifact.get("artifact_type") != "NARRATIVE_SPINE":
                continue
            cur = heads.get(aid)
            if cur is None or int(version) > int(cur["version"]):
                heads[aid] = artifact
        if not heads:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_NARRATIVE_SPINE_MISSING")
        if requested:
            art = state.artifacts.get((requested.get("artifact_id"), int(requested.get("version", 0))))
            if not art or art.get("artifact_type") != "NARRATIVE_SPINE":
                raise VisualRequirementsError("VISUAL_REQUIREMENTS_NARRATIVE_SPINE_REF_INVALID")
            if requested.get("sha256") and requested.get("sha256") != art.get("sha256"):
                raise VisualRequirementsError("VISUAL_REQUIREMENTS_NARRATIVE_SPINE_HASH_MISMATCH")
            head = heads.get(art["artifact_id"])
            if not head or int(head["version"]) != int(art["version"]):
                raise VisualRequirementsError("VISUAL_REQUIREMENTS_NARRATIVE_SPINE_NOT_CURRENT")
            return art, _artifact_ref(art)
        if len(heads) != 1:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_NARRATIVE_SPINE_CARDINALITY_INVALID: {len(heads)} current spines")
        art = next(iter(heads.values()))
        return art, _artifact_ref(art)

    @classmethod
    def _validate_requirement(cls, rec: dict[str, Any]) -> None:
        key = str(rec.get("beat_key") or "")
        if not key:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_BEAT_KEY_REQUIRED")
        for field in ("viewer_must_see", "viewer_must_understand"):
            value = str(rec.get(field) or "").strip()
            if not value:
                raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_FIELD_REQUIRED: {key}.{field}")
            upper = value.upper()
            if any(tok in upper for tok in cls.PLACEHOLDER_TOKENS):
                raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_PLACEHOLDER_FORBIDDEN: {key}.{field}")
        matches = rec.get("preferred_match") or []
        needs = rec.get("asset_needs") or []
        if not matches or any(x not in cls.MATCHES for x in matches):
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_MATCH_INVALID: {key}")
        if len(matches) != len(set(matches)):
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_MATCH_DUPLICATE: {key}")
        if not needs or any(x not in cls.ASSET_NEEDS for x in needs):
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_ASSET_NEED_INVALID: {key}")
        if len(needs) != len(set(needs)):
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_ASSET_NEED_DUPLICATE: {key}")
        if rec.get("priority") not in cls.PRIORITIES:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_PRIORITY_INVALID: {key}")

    @classmethod
    def _validate_plan_shape(cls, plan: dict[str, Any]) -> None:
        reqs = plan.get("requirements") or []
        if not reqs:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_REQUIRED")
        keys: list[str] = []
        for rec in reqs:
            cls._validate_requirement(rec)
            keys.append(str(rec["beat_key"]))
        if len(keys) != len(set(keys)):
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_DUPLICATE_BEAT_KEY")

    @staticmethod
    def _current_beat_map(state) -> dict[str, dict[str, Any]]:
        beats = _active_objects(state, "NARRATION_BEAT")
        if not beats:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_ACTIVE_BEATS_MISSING")
        out: dict[str, dict[str, Any]] = {}
        for beat in beats:
            key = VisualRequirementsRuntime._rough_key(beat)
            if key in out:
                raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_ACTIVE_BEAT_KEY_COLLISION: {key}")
            out[key] = beat
        return out

    @staticmethod
    def _spine_beat_refs(spine: dict[str, Any]) -> list[dict[str, Any]]:
        ext = (spine.get("extensions") or {}).get("rough_narrative") or {}
        refs = ext.get("beat_refs") or []
        if not refs:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_SPINE_BEAT_REFS_MISSING")
        return [{"id": r["id"], "version": int(r["version"])} for r in refs]

    @classmethod
    def _validate_exact_narrative_baseline(cls, beats: dict[str, dict[str, Any]], spine: dict[str, Any], source_batch: str | None) -> None:
        active_refs = sorted((_object_ref(b) for b in beats.values()), key=lambda r: r["id"])
        spine_refs = sorted(cls._spine_beat_refs(spine), key=lambda r: r["id"])
        if active_refs != spine_refs:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_NARRATIVE_BASELINE_DRIFT")
        batches = {str(((b.get("extensions") or {}).get("rough_narrative") or {}).get("batch_id") or "") for b in beats.values()}
        if len(batches) != 1 or "" in batches:
            raise VisualRequirementsError("VISUAL_REQUIREMENTS_ROUGH_NARRATIVE_BATCH_INCONSISTENT")
        current_batch = next(iter(batches))
        if source_batch and source_batch != current_batch:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_SOURCE_BATCH_MISMATCH: expected {current_batch}, got {source_batch}")
        for beat in beats.values():
            if beat.get("workflow_state") != "RESEARCH_BOUND":
                raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_BEAT_STATE_INVALID: {beat['id']}@{beat['version']}={beat.get('workflow_state')}")
            if beat.get("narration"):
                raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_FINAL_NARRATION_TOO_EARLY: {beat['id']}@{beat['version']}")

    def _scan_batch_history(self, state, batch_id: str) -> set[str]:
        hashes: set[str] = set()
        for obj in state.objects.values():
            if obj.get("object_type") != "NARRATION_BEAT":
                continue
            ext = (obj.get("extensions") or {}).get("visual_requirements") or {}
            if ext.get("batch_id") == batch_id and ext.get("plan_sha256"):
                hashes.add(str(ext["plan_sha256"]))
        return hashes

    def _replay_if_current(self, state, batch_id: str, plan_sha256: str, spine_ref: dict[str, Any]) -> VisualRequirementsResult | None:
        history = self._scan_batch_history(state, batch_id)
        if history and history != {plan_sha256}:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_BATCH_ID_COLLISION: {batch_id} already exists with different plan content.")
        beats = self._current_beat_map(state)
        current = []
        for beat in beats.values():
            ext = (beat.get("extensions") or {}).get("visual_requirements") or {}
            if ext.get("batch_id") != batch_id or ext.get("plan_sha256") != plan_sha256:
                return None
            current.append(beat)
        if not current:
            return None
        priorities: dict[str, int] = {}
        needs: dict[str, int] = {}
        for beat in current:
            vr = beat.get("visual_requirement") or {}
            priorities[vr.get("priority", "UNKNOWN")] = priorities.get(vr.get("priority", "UNKNOWN"), 0) + 1
            for need in vr.get("asset_needs") or []:
                needs[need] = needs.get(need, 0) + 1
        return VisualRequirementsResult(
            self.workspace,
            batch_id,
            state.project_state,
            state.manifest_version,
            spine_ref,
            tuple(),
            tuple(_object_ref(b) for b in sorted(current, key=lambda x: x["id"])),
            len(current),
            priorities,
            needs,
            "UNKNOWN",
            True,
        )

    def run(self, visual_plan: dict[str, Any], *, transition_if_ready: bool = True) -> VisualRequirementsResult:
        plan = deepcopy(visual_plan)
        self._validate_plan_shape(plan)
        batch_id = str(plan.get("batch_id") or ("VISUAL_REQUIREMENTS_" + _sha256_json(plan)[:16].upper()))
        plan_sha256 = _sha256_json(plan)

        loaded = ColdStartLoader(self.root, self.workspace).load()
        engine = loaded.engine
        state = engine.snapshot()
        spine, spine_ref = self._validate_spine_ref(state, plan.get("narrative_spine_ref"))

        replay = self._replay_if_current(state, batch_id, plan_sha256, spine_ref)
        if replay:
            gate = engine.gates.evaluate_gate(state, "VISUAL_REQUIREMENTS", engine.now()).result
            return VisualRequirementsResult(
                replay.workspace,
                replay.batch_id,
                engine.project_state,
                engine.manifest_version,
                replay.source_narrative_spine_ref,
                replay.prior_beat_refs,
                replay.beat_refs,
                replay.requirement_count,
                replay.priority_counts,
                replay.asset_need_counts,
                gate,
                True,
            )

        if engine.project_state != "ROUGH_NARRATIVE_READY":
            raise VisualRequirementsError(
                f"VISUAL_REQUIREMENTS_STATE_INVALID: expected ROUGH_NARRATIVE_READY, found {engine.project_state}"
            )

        beats = self._current_beat_map(state)
        self._validate_exact_narrative_baseline(beats, spine, plan.get("source_narrative_batch_id"))

        requirements = {str(r["beat_key"]): r for r in plan["requirements"]}
        current_keys = set(beats)
        plan_keys = set(requirements)
        missing = sorted(current_keys - plan_keys)
        extra = sorted(plan_keys - current_keys)
        if missing:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_COVERAGE_MISSING: {', '.join(missing)}")
        if extra:
            raise VisualRequirementsError(f"VISUAL_REQUIREMENTS_UNKNOWN_BEAT_KEY: {', '.join(extra)}")

        prior_refs = tuple(_object_ref(beats[k]) for k in sorted(beats))
        tx = engine.begin(
            expected_manifest_version=engine.manifest_version,
            expected_registry_versions=engine.registry_versions(),
        )
        new_refs: list[dict[str, Any]] = []
        priority_counts: dict[str, int] = {}
        asset_need_counts: dict[str, int] = {}
        try:
            for key in sorted(beats):
                beat = beats[key]
                req = requirements[key]
                vr = {
                    "viewer_must_see": req["viewer_must_see"].strip(),
                    "viewer_must_understand": req["viewer_must_understand"].strip(),
                    "preferred_match": list(req["preferred_match"]),
                    "asset_needs": list(req["asset_needs"]),
                    "priority": req["priority"],
                }
                ext = deepcopy(beat.get("extensions") or {})
                ext["visual_requirements"] = {
                    "batch_id": batch_id,
                    "plan_sha256": plan_sha256,
                    "source_narrative_spine_ref": spine_ref,
                    "source_narrative_beat_ref": _object_ref(beat),
                }
                nr = tx.create_version(
                    beat["id"],
                    base_version=int(beat["version"]),
                    patch={
                        "visual_requirement": vr,
                        "workflow_state": "VISUAL_REQUIREMENT_READY",
                        "extensions": ext,
                    },
                )
                tx.promote_active_version(nr["id"], nr["version"])
                new_refs.append({"id": nr["id"], "version": int(nr["version"])})
                priority_counts[vr["priority"]] = priority_counts.get(vr["priority"], 0) + 1
                for need in vr["asset_needs"]:
                    asset_need_counts[need] = asset_need_counts.get(need, 0) + 1
            tx.commit()
        except Exception:
            tx.discard()
            raise

        gate = engine.gates.evaluate_gate(engine.snapshot(), "VISUAL_REQUIREMENTS", engine.now()).result
        if transition_if_ready and gate in {"PASS", "WARN"} and engine.project_state == "ROUGH_NARRATIVE_READY":
            t2 = engine.begin(
                expected_manifest_version=engine.manifest_version,
                expected_registry_versions=engine.registry_versions(),
            )
            try:
                t2.transition_project_state("VISUAL_REQUIREMENTS_READY", actor_type="AI", human_confirmed=False)
                t2.commit()
            except StateEngineError:
                t2.discard()
                raise

        manifest = RuntimeStore(self.root, self.workspace).persist(engine)
        return VisualRequirementsResult(
            self.workspace,
            batch_id,
            engine.project_state,
            manifest["manifest_version"],
            spine_ref,
            prior_refs,
            tuple(sorted(new_refs, key=lambda r: r["id"])),
            len(new_refs),
            priority_counts,
            asset_need_counts,
            gate,
            False,
        )
