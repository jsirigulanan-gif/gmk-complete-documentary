from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from copy import deepcopy

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore


class ShotPlanRuntimeError(RuntimeError):
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


def _beat_key(beat: dict[str, Any]) -> str:
    return str((((beat.get("extensions") or {}).get("rough_narrative") or {}).get("key")) or beat["id"])


def _asset_beat_key(asset: dict[str, Any]) -> str | None:
    ext=asset.get("extensions") or {}
    return ((ext.get("asset_recon") or {}).get("beat_key") or
            (ext.get("asset_acquisition") or {}).get("beat_key"))


@dataclass(frozen=True)
class ShotPlanResult:
    workspace: Path
    project_state: str
    shot_count: int
    layer_count: int
    cue_count: int
    scene_plan_refs: tuple[dict[str,Any],...]
    gate_result: str
    transitioned: bool
    idempotent_replay: bool

    def to_dict(self)->dict[str,Any]:
        return {
            "workspace":str(self.workspace),"project_state":self.project_state,
            "shot_count":self.shot_count,"layer_count":self.layer_count,"cue_count":self.cue_count,
            "scene_plan_refs":[dict(x) for x in self.scene_plan_refs],
            "gate_result":self.gate_result,"transitioned":self.transitioned,
            "idempotent_replay":self.idempotent_replay,
        }


class ShotPlanRuntime:
    """Build 027 deterministic shot-plan compiler.

    Baseline policy: exactly one Shot per active Narration Beat. Each Shot owns one
    BASE media Layer sourced from a production-ready VERIFIED Segment and one SHOW
    Cue anchored to the exact Voice Block used by the Voice Timing Map. Scene Plan
    heads are revised to pin the exact ordered Shot refs.
    """

    def __init__(self,schema_root:Path,workspace:Path):
        self.root=Path(schema_root); self.workspace=Path(workspace)

    def _existing(self,state,scenes):
        shots=_active(state,"SHOT"); layers=_active(state,"LAYER"); cues=_active(state,"CUE")
        plans=_heads(state,"SCENE_PLAN")
        if not shots or not plans:return None
        shot_keys={(x["id"],int(x["version"])) for x in shots}
        for p in plans:
            refs=[]
            for item in p.get("shots") or []:
                ref=item.get("shot_ref") if isinstance(item,dict) and "shot_ref" in item else item
                if not isinstance(ref,dict):return None
                refs.append((ref.get("id"),int(ref.get("version",0))))
            if not refs or any(k not in shot_keys for k in refs):return None
        if len(plans)!=len(scenes):return None
        return shots,layers,cues,plans

    def run(self)->ShotPlanResult:
        loaded=ColdStartLoader(self.root,self.workspace).load(); eng=loaded.engine; state=eng.snapshot()
        if eng.project_state not in {"SCENE_PLAN_READY","SHOT_PLAN_READY"}:
            raise ShotPlanRuntimeError(f"SHOT_PLAN_STATE_INVALID: expected SCENE_PLAN_READY/SHOT_PLAN_READY, found {eng.project_state}")
        scenes=_active(state,"SCENE"); beats=_active(state,"NARRATION_BEAT")
        if not scenes or not beats:raise ShotPlanRuntimeError("SHOT_PLAN_INPUTS_MISSING")

        existing=self._existing(state,scenes)
        if existing:
            shots,layers,cues,plans=existing
            gate=eng.gates.evaluate_gate(state,"SHOT_PLAN",eng.now()).result
            return ShotPlanResult(self.workspace,eng.project_state,len(shots),len(layers),len(cues),tuple(_aref(x) for x in plans),gate,False,True)
        if eng.project_state!="SCENE_PLAN_READY":raise ShotPlanRuntimeError("SHOT_PLAN_REPLAY_INCOMPLETE")

        plans=_heads(state,"SCENE_PLAN")
        if len(plans)!=len(scenes):raise ShotPlanRuntimeError("SHOT_PLAN_SCENE_PLAN_COVERAGE_INVALID")
        plan_by_scene={(p.get("scene_ref") or {}).get("id"):p for p in plans}

        voice_locks=_heads(state,"VOICE_LOCK_MANIFEST")
        if len(voice_locks)!=1:raise ShotPlanRuntimeError("SHOT_PLAN_VOICE_LOCK_CARDINALITY_INVALID")
        voice_lock=voice_locks[0]
        tm_ref=voice_lock.get("timing_map") or {}
        timing_map=state.artifacts.get((tm_ref.get("artifact_id"),int(tm_ref.get("version",0))))
        if not timing_map or timing_map.get("artifact_type")!="VOICE_TIMING_MAP":raise ShotPlanRuntimeError("SHOT_PLAN_TIMING_MAP_MISSING")
        mv_ref=timing_map.get("master_voice")
        if not mv_ref:raise ShotPlanRuntimeError("SHOT_PLAN_MASTER_VOICE_MISSING")

        # Exact Beat -> Voice Block/range mapping.
        voice_blocks={o["id"]:o for o in _active(state,"VOICE_BLOCK")}
        timing_by_beat={}
        for item in timing_map.get("blocks") or []:
            vr=item.get("voice_block_ref") or {}
            vb=voice_blocks.get(vr.get("id"))
            if not vb or int(vb.get("version",0))!=int(vr.get("version",0)):continue
            for br in vb.get("source_beat_refs") or []:
                timing_by_beat[(br.get("id"),int(br.get("version",0)))]={
                    "voice_block":vb,"start":float(item["start_seconds"]),"end":float(item["end_seconds"])
                }

        # Beat -> production-ready verified Segment mapping through Asset beat key.
        segs_by_key={}
        for seg in _active(state,"SEGMENT"):
            if seg.get("production_state")!="VERIFIED":continue
            if not (((seg.get("extensions") or {}).get("asset_acquisition") or {}).get("production_ready")):continue
            ar=seg.get("asset_ref") or {}; asset=state.objects.get((ar.get("id"),int(ar.get("version",0))))
            if not asset:continue
            key=_asset_beat_key(asset)
            if key:segs_by_key.setdefault(str(key),[]).append(seg)

        beats_by_scene={s["id"]:[] for s in scenes}
        for b in beats:
            sid=(b.get("scene_ref") or {}).get("id")
            if sid in beats_by_scene:beats_by_scene[sid].append(b)
        for sid in beats_by_scene:beats_by_scene[sid].sort(key=lambda x:(int(x.get("order",0)),x["id"]))

        tx=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        shot_refs=[]; layer_refs=[]; cue_refs=[]; plan_refs=[]
        try:
            scene_order=0
            for scene in scenes:
                scene_order+=1; scene_shots=[]
                plan=plan_by_scene.get(scene["id"])
                if not plan:raise ShotPlanRuntimeError(f"SHOT_PLAN_SCENE_PLAN_MISSING: {scene['id']}")
                for idx,beat in enumerate(beats_by_scene.get(scene["id"],[]),start=1):
                    key=_beat_key(beat); segs=segs_by_key.get(key) or []
                    if not segs:raise ShotPlanRuntimeError(f"SHOT_PLAN_VERIFIED_SEGMENT_MISSING: {key}")
                    timing=timing_by_beat.get((beat["id"],int(beat["version"])))
                    if not timing:raise ShotPlanRuntimeError(f"SHOT_PLAN_BEAT_TIMING_MISSING: {key}")
                    if timing["end"]<=timing["start"]:raise ShotPlanRuntimeError(f"SHOT_PLAN_TIMING_INVALID: {key}")
                    seg=sorted(segs,key=lambda x:x["id"])[0]
                    layer=tx.create_object("LAYER",{
                        "stack_role":"BASE","z_index":0,
                        "content":{"type":"MEDIA_SEGMENT","segment_ref":_oref(seg)},
                        "comprehension_purpose":{"type":"FOCUS_ATTENTION","description":beat.get("viewer_takeaway") or "Support the narration beat with direct visual evidence."},
                        "presentation":{"fit":"COVER","source_policy":"VERIFIED_SEGMENT_ONLY"},
                        "treatment":{"design_tokens_ref":plan.get("design_tokens")},
                        "motion":{"decision":"NO_MOTION","purpose":"Preserve source legibility and evidentiary clarity."},
                        "extensions":{"shot_plan_runtime":{"scene_id":scene["id"],"beat_key":key}}
                    })
                    layer_obj=tx.staged.objects[(layer["id"],layer["version"])]
                    cue=tx.create_object("CUE",{
                        "timing_source":{"master_voice":deepcopy(mv_ref),"timing_map":_aref(timing_map)},
                        "semantic_trigger":{"type":"PHRASE_ANCHOR","anchor_id":timing["voice_block"]["id"],"offset_seconds":0.0},
                        "action":{"type":"SHOW"},"target_layer_refs":[_oref(layer_obj)],
                        "animation":{"start_offset_seconds":0.0,"key_offset_seconds":0.0,"end_offset_seconds":0.0},
                        "extensions":{"shot_plan_runtime":{"beat_key":key}}
                    })
                    cue_obj=tx.staged.objects[(cue["id"],cue["version"])]
                    vr=beat.get("visual_requirement") or {}
                    strategy="DIRECT_EVIDENCE"
                    shot=tx.create_object("SHOT",{
                        "scene_ref":_oref(scene),"order":idx,
                        "beat_bindings":[{"beat_ref":_oref(beat),"role":"PRIMARY"}],
                        "visual_job":vr.get("visual_job") or beat.get("viewer_takeaway") or "Visually support this narration beat.",
                        "viewer_takeaway":beat.get("viewer_takeaway") or beat.get("idea",{}).get("summary") or "Understand this beat.",
                        "visual_strategy":strategy,
                        "timing":{"voice_lock_manifest":_aref(voice_lock),"timing_map":_aref(timing_map),
                                  "start":{"type":"ABSOLUTE_MASTER_TIME","seconds":timing["start"]},
                                  "end":{"type":"ABSOLUTE_MASTER_TIME","seconds":timing["end"]}},
                        "layer_refs":[_oref(layer_obj)],"cue_refs":[_oref(cue_obj)],
                        "transition_out":{"type":"CUT"},
                        "review_class":{"value":"CRITICAL" if str(vr.get("priority",""))=="CRITICAL" else "STANDARD","derivation":"Derived from the Beat visual requirement priority."},
                        "extensions":{"shot_plan_runtime":{"beat_key":key,"segment_ref":_oref(seg),"scene_plan_source":_aref(plan)}}
                    })
                    shot_obj=tx.staged.objects[(shot["id"],shot["version"])]
                    scene_shots.append({"shot_ref":_oref(shot_obj)})
                    shot_refs.append(shot);layer_refs.append(layer);cue_refs.append(cue)
                pref=tx.create_artifact_version(plan["artifact_id"],base_version=plan["version"],payload_patch={
                    "shots":scene_shots,
                    "extensions":{"scene_plan_runtime":{**((plan.get("extensions") or {}).get("scene_plan_runtime") or {}),"shot_plan_compiled":True,"shot_count":len(scene_shots)}}
                },origin_refs=[_oref(scene),_aref(voice_lock),*[_oref(b) for b in beats_by_scene.get(scene["id"],[])]])
                plan_refs.append(pref)
            tx.commit()
        except Exception:
            tx.discard();raise

        state2=eng.snapshot(); gate=eng.gates.evaluate_gate(state2,"SHOT_PLAN",eng.now()).result
        if gate not in {"PASS","WARN"}:raise ShotPlanRuntimeError(f"SHOT_PLAN_GATE_FAILED: {gate}")
        tx2=eng.begin(expected_manifest_version=eng.manifest_version,expected_registry_versions=eng.registry_versions())
        try:
            tx2.transition_project_state("SHOT_PLAN_READY",actor_type="AI",human_confirmed=False);tx2.commit()
        except Exception:
            tx2.discard();raise
        RuntimeStore(self.root,self.workspace).persist(eng)
        final=eng.snapshot(); final_plans=_heads(final,"SCENE_PLAN")
        return ShotPlanResult(self.workspace,eng.project_state,len(_active(final,"SHOT")),len(_active(final,"LAYER")),len(_active(final,"CUE")),tuple(_aref(x) for x in final_plans),gate,True,False)
