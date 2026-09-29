from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

import yaml

from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state.errors import StateEngineError


class AssetReconError(RuntimeError):
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


def _object_ref(o: dict[str, Any]) -> dict[str, Any]:
    return {"id": o["id"], "version": int(o["version"])}


def _artifact_ref(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": a["artifact_id"],
        "artifact_type": a["artifact_type"],
        "version": int(a["version"]),
        "sha256": a["sha256"],
    }


@dataclass(frozen=True)
class AssetReconResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    search_refs: tuple[dict[str, Any], ...]
    result_refs: tuple[dict[str, Any], ...]
    new_source_refs: tuple[dict[str, Any], ...]
    comparison_refs: tuple[dict[str, Any], ...]
    search_count: int
    candidate_count: int
    viable_count: int
    inspection_required_count: int
    meet_target_beats: tuple[str, ...]
    search_again_beats: tuple[str, ...]
    gate_result: str
    next_legal_action: dict[str, Any]
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "batch_id": self.batch_id,
            "project_state": self.project_state,
            "manifest_version": self.manifest_version,
            "search_refs": list(self.search_refs),
            "result_refs": list(self.result_refs),
            "new_source_refs": list(self.new_source_refs),
            "comparison_refs": list(self.comparison_refs),
            "search_count": self.search_count,
            "candidate_count": self.candidate_count,
            "viable_count": self.viable_count,
            "inspection_required_count": self.inspection_required_count,
            "meet_target_beats": list(self.meet_target_beats),
            "search_again_beats": list(self.search_again_beats),
            "gate_result": self.gate_result,
            "next_legal_action": deepcopy(self.next_legal_action),
            "idempotent_replay": self.idempotent_replay,
        }


class AssetReconRuntime:
    """First-pass Asset Recon runtime for frozen GMK Schema v1.

    It creates exact Beat-targeted SEARCH objects and SEARCH_RESULT candidate records,
    performs structured inspection bookkeeping, and compiles explainable candidate
    comparisons. It deliberately does not create ASSET or SEGMENT objects and does not
    issue the Search Completion Certificate until every Beat satisfies the current
    recon policy or has a documented stop condition.
    """

    ALLOWED_PRIORITIES = {"CRITICAL", "MAJOR", "STANDARD", "SUPPORTING"}
    ALLOWED_CANDIDATE_STATES = {
        "DISCOVERED", "INSPECTION_REQUIRED", "INSPECTED", "VIABLE",
        "NON_VIABLE", "SELECTED", "REJECTED", "PROMOTED_TO_ASSET",
    }
    PLACEHOLDER_TOKENS = {"TBD", "TODO", "PLACEHOLDER", "FILLER", "TEMP_ASSET"}

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)
        self.policy = yaml.safe_load((self.root / "config/asset_recon_policies.yaml").read_text(encoding="utf-8")) or {}

    @staticmethod
    def _beat_key(beat: dict[str, Any]) -> str:
        ext = (beat.get("extensions") or {}).get("rough_narrative") or {}
        key = ext.get("key")
        if not key:
            raise AssetReconError(f"ASSET_RECON_BEAT_KEY_MISSING: {beat.get('id')}@{beat.get('version')}")
        return str(key)

    @classmethod
    def _validate_text(cls, value: Any, code: str) -> str:
        out = str(value or "").strip()
        if not out:
            raise AssetReconError(code)
        upper = out.upper()
        if any(tok in upper for tok in cls.PLACEHOLDER_TOKENS):
            raise AssetReconError(f"{code}_PLACEHOLDER")
        return out

    @classmethod
    def _validate_plan(cls, plan: dict[str, Any]) -> None:
        if not plan.get("batch_id"):
            raise AssetReconError("ASSET_RECON_BATCH_ID_REQUIRED")
        searches = plan.get("searches") or []
        results = plan.get("results") or []
        if not searches:
            raise AssetReconError("ASSET_RECON_SEARCHES_REQUIRED")
        if not results:
            raise AssetReconError("ASSET_RECON_RESULTS_REQUIRED")
        search_keys = [str(x.get("key") or "") for x in searches]
        if any(not x for x in search_keys) or len(search_keys) != len(set(search_keys)):
            raise AssetReconError("ASSET_RECON_SEARCH_KEY_INVALID")
        result_keys = [str(x.get("key") or "") for x in results]
        if any(not x for x in result_keys) or len(result_keys) != len(set(result_keys)):
            raise AssetReconError("ASSET_RECON_RESULT_KEY_INVALID")
        known = set(search_keys)
        for s in searches:
            cls._validate_text(s.get("beat_key"), "ASSET_RECON_SEARCH_BEAT_REQUIRED")
            cls._validate_text(s.get("query"), "ASSET_RECON_QUERY_REQUIRED")
            if s.get("priority") not in cls.ALLOWED_PRIORITIES:
                raise AssetReconError(f"ASSET_RECON_PRIORITY_INVALID: {s.get('key')}")
        for r in results:
            if str(r.get("search_key") or "") not in known:
                raise AssetReconError(f"ASSET_RECON_RESULT_SEARCH_UNKNOWN: {r.get('key')}")
            if r.get("candidate_state") not in cls.ALLOWED_CANDIDATE_STATES:
                raise AssetReconError(f"ASSET_RECON_CANDIDATE_STATE_INVALID: {r.get('key')}")
            cls._validate_text(r.get("title"), "ASSET_RECON_RESULT_TITLE_REQUIRED")
            if r.get("candidate_state") == "VIABLE":
                ins = r.get("inspection") or {}
                if not ins.get("exact_moment_found") or not ins.get("candidate_locator") or not ins.get("viewer_takeaway_supported"):
                    raise AssetReconError(f"ASSET_RECON_VIABLE_INSPECTION_INCOMPLETE: {r.get('key')}")
                if not r.get("source_key"):
                    raise AssetReconError(f"ASSET_RECON_VIABLE_SOURCE_REQUIRED: {r.get('key')}")

    @staticmethod
    def _source_key(source: dict[str, Any]) -> str | None:
        for ns in ("research_audit", "asset_recon"):
            ext = (source.get("extensions") or {}).get(ns) or {}
            if ext.get("source_key"):
                return str(ext["source_key"])
        return None

    def _targets(self, priority: str) -> tuple[int, int]:
        if priority == "CRITICAL":
            return int((self.policy.get("critical_targets") or {}).get("viable_candidates", 3)), int((self.policy.get("critical_targets") or {}).get("source_families", 2))
        if priority == "MAJOR":
            return int((self.policy.get("major_targets") or {}).get("viable_candidates", 2)), 1
        return 1, 1

    def _active_beat_map(self, state) -> dict[str, dict[str, Any]]:
        beats = _active_objects(state, "NARRATION_BEAT")
        if not beats:
            raise AssetReconError("ASSET_RECON_ACTIVE_BEATS_MISSING")
        out: dict[str, dict[str, Any]] = {}
        for b in beats:
            key = self._beat_key(b)
            if key in out:
                raise AssetReconError(f"ASSET_RECON_BEAT_KEY_COLLISION: {key}")
            vr = b.get("visual_requirement") or {}
            if b.get("workflow_state") != "VISUAL_REQUIREMENT_READY" or not vr:
                raise AssetReconError(f"ASSET_RECON_BEAT_VISUAL_REQUIREMENT_NOT_READY: {b['id']}@{b['version']}")
            out[key] = b
        return out

    def _source_map(self, state) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for s in _active_objects(state, "SOURCE"):
            key = self._source_key(s)
            if key:
                out[key] = s
        return out

    def _batch_objects(self, state, batch_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        searches=[]; results=[]
        for o in _active_objects(state, "SEARCH"):
            ext=(o.get("extensions") or {}).get("asset_recon") or {}
            if ext.get("batch_id")==batch_id: searches.append(o)
        for o in _active_objects(state, "SEARCH_RESULT"):
            ext=(o.get("extensions") or {}).get("asset_recon") or {}
            if ext.get("batch_id")==batch_id: results.append(o)
        return searches,results

    def _comparison_artifacts(self, state, batch_id: str) -> list[dict[str, Any]]:
        out=[]
        for a in state.artifacts.values():
            if a.get("artifact_type")!="CANDIDATE_COMPARISON": continue
            ext=(a.get("extensions") or {}).get("asset_recon") or {}
            if ext.get("batch_id")==batch_id: out.append(a)
        # one current head per id; replay batches create each comparison once
        return sorted(out,key=lambda a:(a["artifact_id"],int(a["version"])))

    def _summarize(self, state, batch_id: str, plan_sha256: str) -> tuple[tuple[dict[str,Any],...],tuple[dict[str,Any],...],tuple[dict[str,Any],...],tuple[str,...],tuple[str,...],int,int]:
        searches, results = self._batch_objects(state,batch_id)
        hashes={((o.get("extensions") or {}).get("asset_recon") or {}).get("plan_sha256") for o in searches+results}
        hashes.discard(None)
        if hashes and hashes != {plan_sha256}:
            raise AssetReconError("ASSET_RECON_BATCH_ID_COLLISION")
        comps=self._comparison_artifacts(state,batch_id)
        meet=[]; again=[]
        for a in comps:
            key=((a.get("extensions") or {}).get("asset_recon") or {}).get("beat_key")
            if a.get("assessment")=="MEETS_TARGET": meet.append(str(key))
            elif a.get("assessment")=="NEEDS_SEARCH_AGAIN": again.append(str(key))
        viable=sum(1 for r in results if r.get("candidate_state")=="VIABLE")
        inspect=sum(1 for r in results if r.get("candidate_state")=="INSPECTION_REQUIRED")
        return (
            tuple(_object_ref(o) for o in searches), tuple(_object_ref(o) for o in results),
            tuple(_artifact_ref(a) for a in comps), tuple(sorted(meet)), tuple(sorted(again)), viable, inspect
        )

    def run(self, recon_plan: dict[str, Any]) -> AssetReconResult:
        plan=deepcopy(recon_plan); self._validate_plan(plan)
        batch_id=str(plan["batch_id"]); plan_sha256=_sha256_json(plan)
        loaded=ColdStartLoader(self.root,self.workspace).load(); engine=loaded.engine; state=engine.snapshot()

        existing_searches, existing_results = self._batch_objects(state,batch_id)
        if existing_searches or existing_results:
            srefs,rrefs,crefs,meet,again,viable,inspect=self._summarize(state,batch_id,plan_sha256)
            gate=engine.gates.evaluate_gate(state,"ASSET_RECON",engine.now()).result
            return AssetReconResult(self.workspace,batch_id,engine.project_state,engine.manifest_version,srefs,rrefs,tuple(),crefs,len(srefs),len(rrefs),viable,inspect,meet,again,gate,loaded.next_legal_action,True)

        if engine.project_state not in {"VISUAL_REQUIREMENTS_READY","ASSET_RECON"}:
            raise AssetReconError(f"ASSET_RECON_STATE_INVALID: expected VISUAL_REQUIREMENTS_READY/ASSET_RECON, found {engine.project_state}")
        beats=self._active_beat_map(state)
        source_map=self._source_map(state)

        search_specs={str(x["key"]):x for x in plan["searches"]}
        used_beats={str(x["beat_key"]) for x in plan["searches"]}
        unknown=sorted(used_beats-set(beats))
        if unknown: raise AssetReconError(f"ASSET_RECON_UNKNOWN_BEAT_KEYS: {unknown}")
        missing=sorted(set(beats)-used_beats)
        if missing: raise AssetReconError(f"ASSET_RECON_SEARCH_COVERAGE_INCOMPLETE: {missing}")
        for s in plan["searches"]:
            beat=beats[str(s["beat_key"])]
            priority=(beat.get("visual_requirement") or {}).get("priority")
            if s.get("priority")!=priority:
                raise AssetReconError(f"ASSET_RECON_SEARCH_PRIORITY_MISMATCH: {s['key']} expected {priority}, found {s.get('priority')}")

        # Create all data in one staged transaction so exact refs are internally coherent.
        tx=engine.begin(expected_manifest_version=engine.manifest_version, expected_registry_versions=engine.registry_versions())
        if engine.project_state=="VISUAL_REQUIREMENTS_READY":
            tx.transition_project_state("ASSET_RECON",actor_type="SYSTEM",human_confirmed=False)

        new_source_refs=[]
        for spec in plan.get("new_sources") or []:
            key=str(spec["key"])
            if key in source_map:
                raise AssetReconError(f"ASSET_RECON_SOURCE_KEY_COLLISION: {key}")
            payload={
                "source_type":spec.get("source_type","WEB_PAGE"),
                "title":spec["title"],
                "publisher":spec.get("publisher",""),
                "author":spec.get("author",""),
                "platform":spec.get("platform","Web"),
                "published_at":spec.get("published_at",""),
                "accessed_at":engine.now(),
                "authority_class":spec.get("authority_class","REPUTABLE_SECONDARY"),
                "independence":{
                    "group_id":spec["independence_group"],
                    "relationship":spec.get("independence_relationship","INDEPENDENT"),
                },
                "language":spec.get("language","en"),
                "availability":{"state":spec.get("availability","AVAILABLE")},
                "notes":spec.get("notes",""),
                "extensions":{"asset_recon":{"batch_id":batch_id,"plan_sha256":plan_sha256,"source_key":key,"source_verified":True}},
            }
            if spec.get("url"): payload["url"]=spec["url"]
            ref=tx.create_object("SOURCE",payload); new_source_refs.append(ref)
            source_map[key]=tx.staged.objects[(ref["id"],int(ref["version"]))]

        search_ref_by_key={}; search_refs=[]
        for spec in plan["searches"]:
            beat=beats[str(spec["beat_key"])]
            payload={
                "target_beat_ref":_object_ref(beat),
                "priority":spec["priority"],
                "search_round":int(spec.get("search_round",1)),
                "search_pass":spec["search_pass"],
                "query_family":spec["query_family"],
                "query":spec["query"],
                "language":spec.get("language","en"),
                "provider":{"type":spec.get("provider","WEB_SEARCH")},
                "requested_source_families":list(spec.get("requested_source_families") or []),
                "trigger":deepcopy(spec.get("trigger") or {"type":"INITIAL"}),
                "workflow_state":"COMPLETED",
                "extensions":{"asset_recon":{"batch_id":batch_id,"plan_sha256":plan_sha256,"search_key":spec["key"],"beat_key":spec["beat_key"]}},
            }
            ref=tx.create_object("SEARCH",payload); search_refs.append(ref); search_ref_by_key[str(spec["key"])]=ref

        result_ref_by_key={}; result_refs=[]; result_spec_by_key={str(r["key"]):r for r in plan["results"]}
        for spec in plan["results"]:
            source=None; source_ref=None
            if spec.get("source_key"):
                source=source_map.get(str(spec["source_key"]))
                if source is None: raise AssetReconError(f"ASSET_RECON_SOURCE_KEY_UNKNOWN: {spec['key']} -> {spec['source_key']}")
                if source.get("status") in {"STALE","BLOCKED","ARCHIVED","REJECTED"} or (source.get("stale") or {}).get("is_stale"):
                    raise AssetReconError(f"ASSET_RECON_SOURCE_NOT_CURRENT: {spec['source_key']}")
                source_ref=_object_ref(source)
            payload={
                "search_ref":search_ref_by_key[str(spec["search_key"])],
                "discovery_method":spec.get("discovery_method","AUTOMATED_SEARCH"),
                "discovery_locator":{"type":"WEB_URI","value":spec["discovery_url"]},
                "title":spec["title"],
                "source_family":spec["source_family"],
                "candidate_state":spec["candidate_state"],
                "extensions":{"asset_recon":{"batch_id":batch_id,"plan_sha256":plan_sha256,"candidate_key":spec["key"],"beat_key":search_specs[str(spec["search_key"])]["beat_key"]}},
            }
            if source_ref: payload["source_ref"]=source_ref
            if spec.get("inspection") is not None: payload["inspection"]=deepcopy(spec["inspection"])
            if spec.get("evaluation") is not None: payload["evaluation"]=deepcopy(spec["evaluation"])
            if spec.get("rejection") is not None: payload["rejection"]=deepcopy(spec["rejection"])
            ref=tx.create_object("SEARCH_RESULT",payload); result_refs.append(ref); result_ref_by_key[str(spec["key"])]=ref

        comparison_refs=[]; meet=[]; again=[]
        for beat_key, beat in beats.items():
            beat_search_keys=[k for k,s in search_specs.items() if str(s["beat_key"])==beat_key]
            beat_result_specs=[r for r in plan["results"] if str(r["search_key"]) in beat_search_keys]
            candidate_refs=[result_ref_by_key[str(r["key"])] for r in beat_result_specs]
            viable_specs=[r for r in beat_result_specs if r.get("candidate_state")=="VIABLE"]
            viable_refs=[result_ref_by_key[str(r["key"])] for r in viable_specs]
            families=sorted(set(str(r["source_family"]) for r in viable_specs))
            priority=(beat.get("visual_requirement") or {}).get("priority","STANDARD")
            viable_target,family_target=self._targets(priority)
            meets=len(viable_refs)>=viable_target and len(families)>=family_target
            assessment="MEETS_TARGET" if meets else "NEEDS_SEARCH_AGAIN"
            if meets: meet.append(beat_key)
            else: again.append(beat_key)
            dimensions=[]
            for r in beat_result_specs:
                dimensions.append({
                    "candidate_ref":result_ref_by_key[str(r["key"])],
                    "strengths":list(r.get("strengths") or []),
                    "weaknesses":list(r.get("weaknesses") or []),
                    "note":str(r.get("comparison_note") or ""),
                })
            payload={
                "target_beat_ref":_object_ref(beat),
                "priority":priority,
                "search_refs":[search_ref_by_key[k] for k in beat_search_keys],
                "candidate_refs":candidate_refs,
                "viable_candidate_refs":viable_refs,
                "source_families":families,
                "policy_target":{"viable_candidates":viable_target,"source_families":family_target},
                "assessment":assessment,
                "dimensions":dimensions,
                "extensions":{"asset_recon":{"batch_id":batch_id,"plan_sha256":plan_sha256,"beat_key":beat_key,"phase":"FIRST_PASS"}},
            }
            if not meets:
                payload["next_search_reason"]=f"Need {max(0,viable_target-len(viable_refs))} more viable candidate(s) and/or {max(0,family_target-len(families))} more viable source family/families."
            comparison_refs.append(tx.create_artifact("CANDIDATE_COMPARISON",payload,origin_refs=[_object_ref(beat),*[search_ref_by_key[k] for k in beat_search_keys],*candidate_refs]))

        # First-pass recon must not silently promote discovery into production assets.
        before_asset_ids={o["id"] for o in _active_objects(state,"ASSET")}
        after_asset_ids={o["id"] for o in _active_objects(tx.staged,"ASSET")}
        if after_asset_ids != before_asset_ids:
            raise AssetReconError("ASSET_RECON_SEARCH_RESULT_ASSET_BOUNDARY_VIOLATION")

        tx.commit()
        manifest=RuntimeStore(self.root,self.workspace).persist(engine)
        loaded2=ColdStartLoader(self.root,self.workspace).load(); state2=loaded2.engine.snapshot()
        gate=loaded2.engine.gates.evaluate_gate(state2,"ASSET_RECON",loaded2.engine.now()).result
        return AssetReconResult(
            self.workspace,batch_id,loaded2.engine.project_state,manifest["manifest_version"],
            tuple(search_refs),tuple(result_refs),tuple(new_source_refs),tuple(comparison_refs),
            len(search_refs),len(result_refs),sum(1 for r in plan["results"] if r.get("candidate_state")=="VIABLE"),
            sum(1 for r in plan["results"] if r.get("candidate_state")=="INSPECTION_REQUIRED"),
            tuple(sorted(meet)),tuple(sorted(again)),gate,loaded2.next_legal_action,False,
        )
