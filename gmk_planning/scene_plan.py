from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from copy import deepcopy

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore


class ScenePlanRuntimeError(RuntimeError):
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
    out = []
    for reg in state.registries.values():
        for oid, entry in reg.entries.items():
            if entry.object_type == object_type and entry.active_version is not None:
                out.append(state.objects[(oid, int(entry.active_version))])
    return sorted(out, key=lambda x: (int(x.get("order", 0)), x["id"]))


def _heads(state, artifact_type: str) -> list[dict[str, Any]]:
    out = []
    for aid, entry in state.artifact_registry.entries.items():
        if entry.artifact_type == artifact_type:
            out.append(state.artifacts[(aid, int(entry.head_version))])
    return sorted(out, key=lambda x: (x["artifact_id"], int(x["version"])))


def _rough_key(beat: dict[str, Any]) -> str | None:
    # Production pilot Beats carry stable rough_narrative keys. Legacy/minimal fixtures
    # may predate that extension, so their immutable object id is a safe fallback.
    return (((beat.get("extensions") or {}).get("rough_narrative") or {}).get("key")) or beat.get("id")


def _asset_beat_key(asset: dict[str, Any]) -> str | None:
    ext = asset.get("extensions") or {}
    return ((ext.get("asset_recon") or {}).get("beat_key")
            or (ext.get("asset_acquisition") or {}).get("beat_key"))


@dataclass(frozen=True)
class ScenePlanResult:
    workspace: Path
    project_state: str
    scene_count: int
    scene_plan_refs: tuple[dict[str, Any], ...]
    scene_asset_pool_refs: tuple[dict[str, Any], ...]
    beat_count: int
    verified_segment_count: int
    gate_result: str
    transitioned: bool
    idempotent_replay: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "project_state": self.project_state,
            "scene_count": self.scene_count,
            "scene_plan_refs": [dict(x) for x in self.scene_plan_refs],
            "scene_asset_pool_refs": [dict(x) for x in self.scene_asset_pool_refs],
            "beat_count": self.beat_count,
            "verified_segment_count": self.verified_segment_count,
            "gate_result": self.gate_result,
            "transitioned": self.transitioned,
            "idempotent_replay": self.idempotent_replay,
        }


class ScenePlanRuntime:
    """Build 026 scene planning boundary.

    Creates exactly one SCENE_ASSET_POOL and SCENE_PLAN per active Scene after
    DESIGN_DNA_APPROVED. It deliberately creates no SHOT objects; the frozen
    pipeline reserves those for the following SHOT_PLAN stage.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    def _existing(self, state, scenes: list[dict[str, Any]]):
        plans = _heads(state, "SCENE_PLAN")
        pools = _heads(state, "SCENE_ASSET_POOL")
        by_scene_plan = {(p.get("scene_ref") or {}).get("id"): p for p in plans}
        by_scene_pool = {(p.get("scene_ref") or {}).get("id"): p for p in pools}
        if len(by_scene_plan) == len(scenes) and len(by_scene_pool) == len(scenes):
            for s in scenes:
                p = by_scene_plan.get(s["id"])
                pool = by_scene_pool.get(s["id"])
                if not p or not pool:
                    return None
                if (p.get("scene_ref") or {}).get("version") != s["version"]:
                    return None
                if (pool.get("scene_ref") or {}).get("version") != s["version"]:
                    return None
            return plans, pools
        return None

    def run(self) -> ScenePlanResult:
        loaded = ColdStartLoader(self.root, self.workspace).load()
        eng = loaded.engine
        state = eng.snapshot()
        if eng.project_state not in {"DESIGN_DNA_APPROVED", "SCENE_PLAN_READY"}:
            raise ScenePlanRuntimeError(
                f"SCENE_PLAN_STATE_INVALID: expected DESIGN_DNA_APPROVED/SCENE_PLAN_READY, found {eng.project_state}"
            )

        scenes = _active(state, "SCENE")
        if not scenes:
            raise ScenePlanRuntimeError("SCENE_PLAN_ACTIVE_SCENES_MISSING")

        existing = self._existing(state, scenes)
        if existing:
            plans, pools = existing
            gate = eng.gates.evaluate_gate(state, "SCENE_PLAN", eng.now()).result
            beats = _active(state, "NARRATION_BEAT")
            segs = [s for s in _active(state, "SEGMENT") if s.get("production_state") == "VERIFIED"]
            return ScenePlanResult(
                self.workspace, eng.project_state, len(scenes), tuple(_aref(x) for x in plans),
                tuple(_aref(x) for x in pools), len(beats), len(segs), gate, False, True,
            )

        if eng.project_state != "DESIGN_DNA_APPROVED":
            raise ScenePlanRuntimeError("SCENE_PLAN_REPLAY_INCOMPLETE")

        voices = _heads(state, "VOICE_LOCK_MANIFEST")
        tokens = _heads(state, "EFFECTIVE_DESIGN_TOKENS")
        dnas = _active(state, "DESIGN_DNA")
        if not (len(voices) == len(tokens) == len(dnas) == 1):
            raise ScenePlanRuntimeError("SCENE_PLAN_DEPENDENCY_CARDINALITY_INVALID")
        voice_lock, design_tokens, dna = voices[0], tokens[0], dnas[0]

        # Exact approved design identity must match the tokens being used.
        if (design_tokens.get("design_dna_ref") or {}) != _oref(dna):
            raise ScenePlanRuntimeError("SCENE_PLAN_DESIGN_TOKEN_DNA_MISMATCH")

        timing_ref = voice_lock.get("timing_map")
        timing_map = None
        if timing_ref:
            timing_map = state.artifacts.get((timing_ref.get("artifact_id"), int(timing_ref.get("version", 0))))
        if not timing_map or timing_map.get("artifact_type") != "VOICE_TIMING_MAP":
            raise ScenePlanRuntimeError("SCENE_PLAN_TIMING_MAP_REQUIRED")

        beats = _active(state, "NARRATION_BEAT")
        beats_by_scene: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in scenes}
        for beat in beats:
            sr = beat.get("scene_ref") or {}
            if sr.get("id") in beats_by_scene:
                beats_by_scene[sr["id"]].append(beat)

        # Resolve production-ready, VERIFIED Segments back to Beat keys through Assets.
        segs_by_key: dict[str, list[dict[str, Any]]] = {}
        verified_segments = []
        for seg in _active(state, "SEGMENT"):
            if seg.get("production_state") != "VERIFIED":
                continue
            acq = ((seg.get("extensions") or {}).get("asset_acquisition") or {})
            if not acq.get("production_ready"):
                continue
            ar = seg.get("asset_ref") or {}
            asset = state.objects.get((ar.get("id"), int(ar.get("version", 0))))
            if not asset:
                continue
            key = _asset_beat_key(asset)
            if key:
                segs_by_key.setdefault(str(key), []).append(seg)
                verified_segments.append(seg)

        # Build timing ranges from Voice Blocks referenced by the exact Timing Map.
        voice_blocks = {b["id"]: b for b in _active(state, "VOICE_BLOCK")}
        beat_timing: dict[tuple[str, int], dict[str, float]] = {}
        for item in timing_map.get("blocks") or []:
            vr = item.get("voice_block_ref") or {}
            vb = voice_blocks.get(vr.get("id"))
            if not vb or int(vb.get("version", 0)) != int(vr.get("version", 0)):
                continue
            for br in vb.get("source_beat_refs") or []:
                beat_timing[(br.get("id"), int(br.get("version", 0)))] = {
                    "start_seconds": float(item["start_seconds"]),
                    "end_seconds": float(item["end_seconds"]),
                }

        tx = eng.begin(expected_manifest_version=eng.manifest_version, expected_registry_versions=eng.registry_versions())
        plan_refs = []
        pool_refs = []
        try:
            for scene in scenes:
                scene_beats = sorted(beats_by_scene.get(scene["id"], []), key=lambda x: (int(x.get("order", 0)), x["id"]))
                beat_pools = []
                scene_ranges = []
                for beat in scene_beats:
                    key = _rough_key(beat)
                    if not key:
                        raise ScenePlanRuntimeError(f"SCENE_PLAN_BEAT_KEY_MISSING: {beat['id']}@{beat['version']}")
                    segs = segs_by_key.get(str(key), [])
                    if not segs:
                        raise ScenePlanRuntimeError(f"SCENE_PLAN_VERIFIED_SEGMENT_MISSING: {key}")
                    timing = beat_timing.get((beat["id"], int(beat["version"])))
                    if not timing:
                        raise ScenePlanRuntimeError(f"SCENE_PLAN_BEAT_TIMING_MISSING: {key}")
                    scene_ranges.append(timing)
                    beat_pools.append({
                        "beat_ref": _oref(beat),
                        "beat_key": str(key),
                        "visual_requirement": deepcopy(beat.get("visual_requirement") or {}),
                        "segment_refs": [_oref(s) for s in segs],
                        "voice_range": timing,
                    })

                pool_ref = tx.create_artifact(
                    "SCENE_ASSET_POOL",
                    {"scene_ref": _oref(scene), "beat_pools": beat_pools},
                    origin_refs=[_oref(scene), *[_oref(b) for b in scene_beats], *[_oref(s) for p in beat_pools for s in [state.objects[(r["id"], int(r["version"]))] for r in p["segment_refs"]]]],
                )
                pool_art = tx.staged.artifacts[(pool_ref["artifact_id"], int(pool_ref["version"]))]
                ext = {
                    "scene_plan_runtime": {
                        "beat_count": len(scene_beats),
                        "shot_objects_deferred_to": "SHOT_PLAN",
                        "voice_range": ({
                            "start_seconds": min(x["start_seconds"] for x in scene_ranges),
                            "end_seconds": max(x["end_seconds"] for x in scene_ranges),
                        } if scene_ranges else None),
                    }
                }
                plan_ref = tx.create_artifact(
                    "SCENE_PLAN",
                    {
                        "scene_ref": _oref(scene),
                        "voice_lock": _aref(voice_lock),
                        "design_dna_ref": _oref(dna),
                        "design_tokens": _aref(design_tokens),
                        "scene_asset_pool": _aref(pool_art),
                        "shots": [],
                        "extensions": ext,
                    },
                    origin_refs=[_oref(scene), _aref(voice_lock), _oref(dna), _aref(design_tokens), _aref(pool_art)],
                )
                pool_refs.append(pool_ref)
                plan_refs.append(plan_ref)
            tx.commit()
        except Exception:
            tx.discard()
            raise

        state2 = eng.snapshot()
        gate = eng.gates.evaluate_gate(state2, "SCENE_PLAN", eng.now()).result
        transitioned = False
        if gate in {"PASS", "WARN"}:
            tx2 = eng.begin(expected_manifest_version=eng.manifest_version, expected_registry_versions=eng.registry_versions())
            try:
                tx2.transition_project_state("SCENE_PLAN_READY", actor_type="AI", human_confirmed=False)
                tx2.commit()
                transitioned = True
            except Exception:
                tx2.discard()
                raise
        else:
            raise ScenePlanRuntimeError(f"SCENE_PLAN_GATE_FAILED: {gate}")

        RuntimeStore(self.root, self.workspace).persist(eng)
        final = eng.snapshot()
        plans = _heads(final, "SCENE_PLAN")
        pools = _heads(final, "SCENE_ASSET_POOL")
        return ScenePlanResult(
            self.workspace, eng.project_state, len(scenes), tuple(_aref(x) for x in plans), tuple(_aref(x) for x in pools),
            len(beats), len(verified_segments), gate, transitioned, False,
        )
