from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json

from gmk_operations import OperationRuntime
from gmk_qa import QARuntime
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.persistence import RuntimeStore
from gmk_state.errors import StateEngineError


class AssetSelectionError(RuntimeError):
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


def _object_ref(obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": obj["id"], "version": int(obj["version"])}


def _asset_recon_ext(obj: dict[str, Any]) -> dict[str, Any]:
    return (obj.get("extensions") or {}).get("asset_recon") or {}


@dataclass(frozen=True)
class AssetSelectionResult:
    workspace: Path
    batch_id: str
    project_state: str
    manifest_version: int
    search_again_refs: tuple[dict[str, Any], ...]
    new_result_refs: tuple[dict[str, Any], ...]
    selected_candidate_refs: tuple[dict[str, Any], ...]
    asset_refs: tuple[dict[str, Any], ...]
    acquisition_operation_refs: tuple[dict[str, Any], ...]
    search_completion_report_ref: dict[str, Any]
    search_completion_result: str
    segment_count: int
    acquisition_pending_count: int
    gate_result: str
    transition_deferred: bool
    next_legal_action: dict[str, Any]
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "batch_id": self.batch_id,
            "project_state": self.project_state,
            "manifest_version": self.manifest_version,
            "search_again_refs": list(self.search_again_refs),
            "new_result_refs": list(self.new_result_refs),
            "selected_candidate_refs": list(self.selected_candidate_refs),
            "asset_refs": list(self.asset_refs),
            "acquisition_operation_refs": list(self.acquisition_operation_refs),
            "search_completion_report_ref": deepcopy(self.search_completion_report_ref),
            "search_completion_result": self.search_completion_result,
            "segment_count": self.segment_count,
            "acquisition_pending_count": self.acquisition_pending_count,
            "gate_result": self.gate_result,
            "transition_deferred": self.transition_deferred,
            "next_legal_action": deepcopy(self.next_legal_action),
            "idempotent_replay": self.idempotent_replay,
        }


class AssetSelectionRuntime:
    """Search-again closure, selection, and acquisition planning for GMK Asset Recon.

    This runtime deliberately stops before media acquisition succeeds. It may create
    ASSET objects in ACQUISITION_PENDING and plan DOWNLOAD operations, but it never
    fabricates original_file checksums and never creates SEGMENT objects before an
    immutable original file has actually been acquired and verified.
    """

    def __init__(self, schema_root: Path, workspace: Path):
        self.root = Path(schema_root)
        self.workspace = Path(workspace)

    @staticmethod
    def _beat_key(beat: dict[str, Any]) -> str:
        key = ((beat.get("extensions") or {}).get("rough_narrative") or {}).get("key")
        if not key:
            raise AssetSelectionError(f"ASSET_SELECTION_BEAT_KEY_MISSING: {beat.get('id')}@{beat.get('version')}")
        return str(key)

    @staticmethod
    def _source_key(source: dict[str, Any]) -> str | None:
        for ns in ("research_audit", "asset_recon"):
            ext = (source.get("extensions") or {}).get(ns) or {}
            if ext.get("source_key"):
                return str(ext["source_key"])
        return None

    @staticmethod
    def _candidate_key(result: dict[str, Any]) -> str | None:
        value = _asset_recon_ext(result).get("candidate_key")
        return str(value) if value else None

    @staticmethod
    def _batch_id(obj: dict[str, Any]) -> str | None:
        value = _asset_recon_ext(obj).get("batch_id")
        return str(value) if value else None

    def _maps(self, state):
        beats = {self._beat_key(b): b for b in _active_objects(state, "NARRATION_BEAT")}
        sources = {}
        for source in _active_objects(state, "SOURCE"):
            key = self._source_key(source)
            if key:
                sources[key] = source
        results = {}
        for result in _active_objects(state, "SEARCH_RESULT"):
            key = self._candidate_key(result)
            if key:
                results[key] = result
        searches = {}
        for search in _active_objects(state, "SEARCH"):
            key = _asset_recon_ext(search).get("search_key")
            if key:
                searches[str(key)] = search
        return beats, sources, results, searches

    def _existing_batch_assets(self, state, batch_id: str) -> list[dict[str, Any]]:
        out = []
        for asset in _active_objects(state, "ASSET"):
            if _asset_recon_ext(asset).get("selection_batch_id") == batch_id:
                out.append(asset)
        return out

    def _existing_certificate(self, state, batch_id: str) -> dict[str, Any] | None:
        for report in _active_objects(state, "QA_REPORT"):
            if report.get("report_type") != "SEARCH_COMPLETION_CERTIFICATE":
                continue
            if ((report.get("extensions") or {}).get("asset_recon") or {}).get("selection_batch_id") == batch_id:
                return report
        return None

    @staticmethod
    def _validate_plan(plan: dict[str, Any]) -> None:
        if not str(plan.get("batch_id") or "").strip():
            raise AssetSelectionError("ASSET_SELECTION_BATCH_ID_REQUIRED")
        if not str(plan.get("source_recon_batch_id") or "").strip():
            raise AssetSelectionError("ASSET_SELECTION_SOURCE_BATCH_REQUIRED")
        selections = plan.get("selections") or []
        if not selections:
            raise AssetSelectionError("ASSET_SELECTIONS_REQUIRED")
        beat_keys = [str(x.get("beat_key") or "") for x in selections]
        if any(not x for x in beat_keys) or len(beat_keys) != len(set(beat_keys)):
            raise AssetSelectionError("ASSET_SELECTION_BEAT_KEYS_INVALID")
        candidate_keys = [str(x.get("candidate_key") or "") for x in selections]
        if any(not x for x in candidate_keys):
            raise AssetSelectionError("ASSET_SELECTION_CANDIDATE_KEY_REQUIRED")
        for spec in plan.get("search_again") or []:
            if not spec.get("beat_key") or not spec.get("search_key") or not spec.get("query"):
                raise AssetSelectionError("SEARCH_AGAIN_SPEC_INVALID")
            for result in spec.get("results") or []:
                if not result.get("key") or not result.get("source_key") or not result.get("discovery_url"):
                    raise AssetSelectionError("SEARCH_AGAIN_RESULT_INVALID")
                if result.get("candidate_state") != "VIABLE":
                    raise AssetSelectionError("SEARCH_AGAIN_RESULT_MUST_BE_VIABLE")

    def _summarize_replay(self, engine, state, batch_id: str) -> AssetSelectionResult:
        assets = self._existing_batch_assets(state, batch_id)
        cert = self._existing_certificate(state, batch_id)
        if cert is None:
            raise AssetSelectionError("ASSET_SELECTION_REPLAY_CERTIFICATE_MISSING")
        ops = []
        selected = []
        new_results = []
        searches = []
        seen_ops=set()
        for asset in assets:
            op=asset.get("acquisition_operation_ref")
            if op:
                key=(op.get("id"),int(op.get("version",0)))
                if key not in seen_ops:
                    ops.append(deepcopy(op));seen_ops.add(key)
        for obj in _active_objects(state, "SEARCH_RESULT"):
            ext = _asset_recon_ext(obj)
            if ext.get("selection_batch_id") == batch_id:
                if ext.get("search_again"):
                    new_results.append(_object_ref(obj))
                if obj.get("candidate_state") == "PROMOTED_TO_ASSET":
                    selected.append(_object_ref(obj))
        for obj in _active_objects(state, "SEARCH"):
            ext = _asset_recon_ext(obj)
            if ext.get("selection_batch_id") == batch_id:
                searches.append(_object_ref(obj))
        gate = engine.gates.evaluate_gate(state, "ASSET_RECON", engine.now()).result
        segs = len(_active_objects(state, "SEGMENT"))
        return AssetSelectionResult(
            self.workspace, batch_id, engine.project_state, engine.manifest_version,
            tuple(searches), tuple(new_results), tuple(selected), tuple(_object_ref(a) for a in assets),
            tuple(ops), _object_ref(cert), cert.get("result", "PASS"), segs,
            sum(1 for a in assets if a.get("workflow_state") == "ACQUISITION_PENDING"),
            gate, True, engine.gates.next_legal_action(state, engine.now()).to_dict(), True,
        )

    def run(self, plan: dict[str, Any]) -> AssetSelectionResult:
        plan = deepcopy(plan)
        self._validate_plan(plan)
        batch_id = str(plan["batch_id"])
        source_batch_id = str(plan["source_recon_batch_id"])
        plan_sha256 = _sha256_json(plan)

        loaded = ColdStartLoader(self.root, self.workspace).load()
        engine = loaded.engine
        state = engine.snapshot()
        if engine.project_state != "ASSET_RECON":
            raise AssetSelectionError(f"ASSET_SELECTION_STATE_INVALID: expected ASSET_RECON, found {engine.project_state}")
        if self._existing_batch_assets(state, batch_id) or self._existing_certificate(state, batch_id):
            return self._summarize_replay(engine, state, batch_id)

        beats, sources, results, searches = self._maps(state)
        source_batch_results = [r for r in results.values() if self._batch_id(r) == source_batch_id]
        if not source_batch_results:
            raise AssetSelectionError(f"ASSET_SELECTION_SOURCE_BATCH_NOT_FOUND: {source_batch_id}")

        search_again_refs = []
        new_result_refs = []
        # Search Again records are committed first so comparison/selection can use exact refs.
        if plan.get("search_again"):
            tx = engine.begin(expected_manifest_version=engine.manifest_version, expected_registry_versions=engine.registry_versions())
            staged_source_by_key = dict(sources)
            staged_search_by_key = dict(searches)
            for search_spec in plan.get("search_again") or []:
                beat_key = str(search_spec["beat_key"])
                beat = beats.get(beat_key)
                if beat is None:
                    raise AssetSelectionError(f"SEARCH_AGAIN_BEAT_UNKNOWN: {beat_key}")
                for src in search_spec.get("new_sources") or []:
                    key = str(src["key"])
                    if key in staged_source_by_key:
                        continue
                    payload = {
                        "source_type": src.get("source_type", "SOCIAL_POST"),
                        "title": src["title"],
                        "publisher": src.get("publisher", ""),
                        "author": src.get("author", ""),
                        "platform": src.get("platform", "Web"),
                        "published_at": src.get("published_at", ""),
                        "accessed_at": engine.now(),
                        "authority_class": src.get("authority_class", "PRIMARY"),
                        "independence": {"group_id": src["independence_group"], "relationship": src.get("independence_relationship", "INDEPENDENT")},
                        "language": src.get("language", "en"),
                        "availability": {"state": src.get("availability", "AVAILABLE")},
                        "notes": src.get("notes", ""),
                        "url": src["url"],
                        "extensions": {"asset_recon": {"source_key": key, "selection_batch_id": batch_id, "source_verified": True}},
                    }
                    ref = tx.create_object("SOURCE", payload)
                    staged_source_by_key[key] = tx.staged.objects[(ref["id"], int(ref["version"]))]
                previous = []
                for key in search_spec.get("previous_search_keys") or []:
                    if key in staged_search_by_key:
                        previous.append(_object_ref(staged_search_by_key[key]))
                spayload = {
                    "target_beat_ref": _object_ref(beat),
                    "priority": search_spec.get("priority") or (beat.get("visual_requirement") or {}).get("priority", "CRITICAL"),
                    "search_round": int(search_spec.get("search_round", 2)),
                    "search_pass": search_spec.get("search_pass", "TECHNICAL_RESEARCH"),
                    "query_family": search_spec.get("query_family", "EXACT_ENTITY"),
                    "query": search_spec["query"],
                    "language": search_spec.get("language", "en"),
                    "provider": {"type": search_spec.get("provider", "WEB_SEARCH")},
                    "requested_source_families": list(search_spec.get("requested_source_families") or ["ORIGINAL_CREATOR"]),
                    "trigger": {
                        "type": "SEARCH_AGAIN",
                        "previous_search_refs": previous,
                        "failure_reason": search_spec.get("failure_reason", "Critical Beat was below candidate target."),
                        "strategy_change": search_spec.get("strategy_change", "Prioritize original-creator/direct-media evidence."),
                    },
                    "workflow_state": "COMPLETED",
                    "extensions": {"asset_recon": {"selection_batch_id": batch_id, "source_recon_batch_id": source_batch_id, "plan_sha256": plan_sha256, "search_key": search_spec["search_key"], "beat_key": beat_key, "search_again": True}},
                }
                sref = tx.create_object("SEARCH", spayload)
                search_again_refs.append(sref)
                staged_search_by_key[str(search_spec["search_key"])] = tx.staged.objects[(sref["id"], int(sref["version"]))]
                for rspec in search_spec.get("results") or []:
                    src = staged_source_by_key.get(str(rspec["source_key"]))
                    if src is None:
                        raise AssetSelectionError(f"SEARCH_AGAIN_SOURCE_UNKNOWN: {rspec['source_key']}")
                    rpayload = {
                        "search_ref": sref,
                        "discovery_method": rspec.get("discovery_method", "AUTOMATED_SEARCH"),
                        "discovery_locator": {"type": "WEB_URI", "value": rspec["discovery_url"]},
                        "title": rspec["title"],
                        "source_family": rspec.get("source_family", "ORIGINAL_CREATOR"),
                        "source_ref": _object_ref(src),
                        "candidate_state": "VIABLE",
                        "inspection": deepcopy(rspec["inspection"]),
                        "evaluation": deepcopy(rspec.get("evaluation") or {"visual_clarity":"HIGH","technical_quality":"UNKNOWN","cleanliness":"CLEAN","duplicate_state":"UNIQUE"}),
                        "extensions": {"asset_recon": {"selection_batch_id": batch_id, "source_recon_batch_id": source_batch_id, "plan_sha256": plan_sha256, "candidate_key": rspec["key"], "beat_key": beat_key, "search_again": True}},
                    }
                    rref = tx.create_object("SEARCH_RESULT", rpayload)
                    new_result_refs.append(rref)
            tx.commit()
            state = engine.snapshot()
            beats, sources, results, searches = self._maps(state)

        # Recompute candidate-target closure from all current candidates by Beat.
        comparison_by_beat = {}
        for art in state.artifacts.values():
            if art.get("artifact_type") != "CANDIDATE_COMPARISON":
                continue
            beat_key = _asset_recon_ext(art).get("beat_key")
            if not beat_key:
                continue
            cur = comparison_by_beat.get(str(beat_key))
            if cur is None or int(art["version"]) > int(cur["version"]):
                comparison_by_beat[str(beat_key)] = art

        candidate_by_beat: dict[str, list[dict[str, Any]]] = {k: [] for k in beats}
        for result in _active_objects(state, "SEARCH_RESULT"):
            ext = _asset_recon_ext(result)
            beat_key = ext.get("beat_key")
            if beat_key in candidate_by_beat:
                candidate_by_beat[str(beat_key)].append(result)

        incomplete = []
        for beat_key, beat in beats.items():
            viable = [r for r in candidate_by_beat[beat_key] if r.get("candidate_state") in {"VIABLE","SELECTED","PROMOTED_TO_ASSET"}]
            fams = {str(r.get("source_family")) for r in viable}
            priority = (beat.get("visual_requirement") or {}).get("priority", "STANDARD")
            vt = 3 if priority == "CRITICAL" else (2 if priority == "MAJOR" else 1)
            ft = 2 if priority == "CRITICAL" else 1
            if len(viable) < vt or len(fams) < ft:
                incomplete.append({"beat_key": beat_key, "viable": len(viable), "families": sorted(fams), "required_viable": vt, "required_families": ft})
        if incomplete:
            raise AssetSelectionError(f"SEARCH_COMPLETION_TARGETS_NOT_MET: {incomplete}")

        # Search Again closes with a new Candidate Comparison version; old comparisons remain immutable history.
        refreshed_comparison_refs=[]
        for search_spec in plan.get("search_again") or []:
            beat_key=str(search_spec["beat_key"])
            beat=beats[beat_key]
            prior=comparison_by_beat.get(beat_key)
            if prior is None:
                raise AssetSelectionError(f"SEARCH_AGAIN_COMPARISON_MISSING: {beat_key}")
            beat_searches=[]
            for search in _active_objects(engine.snapshot(), "SEARCH"):
                if _asset_recon_ext(search).get("beat_key")==beat_key:
                    beat_searches.append(search)
            beat_candidates=candidate_by_beat[beat_key]
            viable=[r for r in beat_candidates if r.get("candidate_state") in {"VIABLE","SELECTED","PROMOTED_TO_ASSET"}]
            families=sorted({str(r.get("source_family")) for r in viable})
            priority=(beat.get("visual_requirement") or {}).get("priority","STANDARD")
            vt=3 if priority=="CRITICAL" else (2 if priority=="MAJOR" else 1)
            ft=2 if priority=="CRITICAL" else 1
            txc=engine.begin()
            ref=txc.create_artifact_version(prior["artifact_id"],base_version=prior["version"],payload_patch={
                "search_refs":[_object_ref(x) for x in beat_searches],
                "candidate_refs":[_object_ref(x) for x in beat_candidates],
                "viable_candidate_refs":[_object_ref(x) for x in viable],
                "source_families":families,
                "policy_target":{"viable_candidates":vt,"source_families":ft},
                "assessment":"MEETS_TARGET",
                "next_search_reason":None,
                "extensions":{"asset_recon":{**_asset_recon_ext(prior),"selection_batch_id":batch_id,"phase":"SEARCH_AGAIN_CLOSED","search_again_closed":True}},
            },origin_refs=[_object_ref(beat),*[_object_ref(x) for x in beat_searches],*[_object_ref(x) for x in beat_candidates]])
            txc.commit();refreshed_comparison_refs.append(ref)
        if refreshed_comparison_refs:
            state=engine.snapshot();beats,sources,results,searches=self._maps(state)

        # Explicit selection and ASSET promotion. No original_file is invented here.
        selected_candidate_refs = []
        asset_refs = []
        acquisition_ops = []
        for spec in plan["selections"]:
            beat_key = str(spec["beat_key"])
            candidate_key = str(spec["candidate_key"])
            result = results.get(candidate_key)
            if result is None:
                raise AssetSelectionError(f"ASSET_SELECTION_CANDIDATE_UNKNOWN: {candidate_key}")
            if _asset_recon_ext(result).get("beat_key") != beat_key:
                raise AssetSelectionError(f"ASSET_SELECTION_BEAT_CANDIDATE_MISMATCH: {beat_key} <- {candidate_key}")
            if result.get("candidate_state") not in {"VIABLE", "SELECTED", "PROMOTED_TO_ASSET"}:
                raise AssetSelectionError(f"ASSET_SELECTION_CANDIDATE_NOT_VIABLE: {candidate_key}")
            source = state.objects.get((result["source_ref"]["id"], int(result["source_ref"]["version"])))
            if source is None:
                raise AssetSelectionError(f"ASSET_SELECTION_SOURCE_MISSING: {candidate_key}")

            tx = engine.begin()
            current = tx.staged.objects[(result["id"], int(result["version"]))]
            if current.get("candidate_state") == "VIABLE":
                sref = tx.create_version(current["id"], base_version=current["version"], patch={
                    "candidate_state": "SELECTED",
                    "extensions": {"asset_recon": {**_asset_recon_ext(current), "selection_batch_id": batch_id, "selection_reason": spec.get("selection_reason", "Best current fit for Beat and traceability.")}},
                })
                tx.promote_active_version(current["id"], sref["version"], confirm_locked_impact=True)
                selected = tx.staged.objects[(sref["id"], int(sref["version"]))]
            else:
                selected = current
                sref = _object_ref(selected)
            apayload = {
                "origin_search_result_ref": _object_ref(selected),
                "source_ref": deepcopy(selected["source_ref"]),
                "media_type": spec["media_type"],
                "asset_class": spec["asset_class"],
                "workflow_state": "SELECTED",
                "rights": {
                    "status": spec.get("rights_status", "UNKNOWN"),
                    "basis": spec.get("rights_basis", "Rights review required before production use."),
                    "attribution_required": bool(spec.get("attribution_required", False)),
                    "notes": spec.get("rights_notes", "Selection is not rights clearance."),
                },
                "extensions": {"asset_recon": {"selection_batch_id": batch_id, "source_recon_batch_id": source_batch_id, "beat_key": beat_key, "candidate_key": candidate_key, "production_ready": False}},
            }
            aref = tx.create_object("ASSET", apayload)
            tx.commit()

            # Plan exactly-once acquisition. This is intentionally left PLANNED.
            op = OperationRuntime(engine).plan(
                operation_type="DOWNLOAD",
                subject=aref,
                provider=spec.get("acquisition_provider", "GMK_ACQUISITION_ADAPTER"),
                action="ACQUIRE_ORIGINAL_MEDIA",
                input_fingerprint=_sha256_json({"asset_ref": aref, "source": selected.get("discovery_locator"), "source_ref": selected.get("source_ref")}),
                idempotency_key=f"ACQUIRE_{aref['id']}_{candidate_key}_{batch_id}",
                destination=spec.get("destination", f"gmk://incoming/assets/{aref['id']}"),
            )
            op_ref = op["operation_ref"]
            acquisition_ops.append(op_ref)

            # Asset enters ACQUISITION_PENDING and points to the planned Operation.
            active_asset = engine.resolver().resolve(aref["id"], mode="ACTIVE")
            tx2 = engine.begin()
            av2 = tx2.create_version(active_asset["id"], base_version=active_asset["version"], patch={"workflow_state":"ACQUISITION_PENDING", "acquisition_operation_ref": op_ref})
            tx2.promote_active_version(active_asset["id"], av2["version"], confirm_locked_impact=True)
            tx2.commit()
            asset_current = engine.resolver().resolve(aref["id"], mode="ACTIVE")

            # Candidate becomes PROMOTED_TO_ASSET only after Asset identity exists.
            active_candidate = engine.resolver().resolve(selected["id"], mode="ACTIVE")
            tx3 = engine.begin()
            cv = tx3.create_version(active_candidate["id"], base_version=active_candidate["version"], patch={
                "candidate_state":"PROMOTED_TO_ASSET",
                "promoted_asset_ref": _object_ref(asset_current),
                "extensions": {"asset_recon": {**_asset_recon_ext(active_candidate), "selection_batch_id": batch_id, "promoted": True}},
            })
            tx3.promote_active_version(active_candidate["id"], cv["version"], confirm_locked_impact=True)
            tx3.commit()

            selected_candidate_refs.append(cv)
            asset_refs.append(_object_ref(asset_current))
            state = engine.snapshot()
            beats, sources, results, searches = self._maps(state)

        # Search Completion Certificate is a QA_REPORT Core Object, as frozen in 2B/2H.
        project = _active_objects(engine.snapshot(), "PROJECT")
        if not project:
            raise AssetSelectionError("SEARCH_COMPLETION_PROJECT_MISSING")
        cert = QARuntime(engine).evaluate(report_type="SEARCH_COMPLETION_CERTIFICATE", scope=_object_ref(project[0]), findings=())
        cert_ref = cert["report_ref"]
        # annotate the report with batch provenance without changing result semantics
        cert_obj = engine.resolver().resolve(cert_ref["id"], mode="ACTIVE")
        tx4 = engine.begin()
        cv2 = tx4.create_version(cert_obj["id"], base_version=cert_obj["version"], patch={
            "extensions": {"asset_recon": {"selection_batch_id": batch_id, "source_recon_batch_id": source_batch_id, "plan_sha256": plan_sha256, "all_beat_targets_met": True, "asset_count": len(asset_refs), "acquisition_complete": False}}
        })
        tx4.promote_active_version(cert_obj["id"], cv2["version"], confirm_locked_impact=True)
        tx4.commit()
        cert_ref = cv2

        # Persist but do NOT transition to ASSET_CATALOG_READY while originals are pending.
        manifest = RuntimeStore(self.root, self.workspace).persist(engine)
        loaded2 = ColdStartLoader(self.root, self.workspace).load()
        state2 = loaded2.engine.snapshot()
        gate = loaded2.engine.gates.evaluate_gate(state2, "ASSET_RECON", loaded2.engine.now()).result
        segments = len(_active_objects(state2, "SEGMENT"))
        assets = self._existing_batch_assets(state2, batch_id)
        pending = sum(1 for a in assets if a.get("workflow_state") == "ACQUISITION_PENDING")
        if segments:
            raise AssetSelectionError("ASSET_SELECTION_SEGMENT_BOUNDARY_VIOLATION")
        return AssetSelectionResult(
            self.workspace, batch_id, loaded2.engine.project_state, manifest["manifest_version"],
            tuple(search_again_refs), tuple(new_result_refs), tuple(selected_candidate_refs), tuple(_object_ref(a) for a in assets),
            tuple(acquisition_ops), cert_ref, cert["result"], segments, pending, gate, True,
            loaded2.next_legal_action, False,
        )
