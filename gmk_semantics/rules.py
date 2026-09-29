from __future__ import annotations
from collections import Counter, defaultdict
from typing import Any

from .model import ValidationIssue, decision_hash, sha256_json
from .state import StateView
from .catalog import SchemaCatalog


def I(code: str, msg: str, obj: dict[str, Any] | None = None, *, severity: str = "ERROR", path: str | None = None, related=()) -> ValidationIssue:
    target = None
    if obj:
        target = f"{obj.get('id','?')}@{obj.get('version','?')}"
    return ValidationIssue(code, msg, severity, target, path, tuple(related))


def _is_obj_ref(v: Any) -> bool:
    return isinstance(v, dict) and set(("id", "version")).issubset(v)


def _is_art_ref(v: Any) -> bool:
    return isinstance(v, dict) and set(("artifact_id", "version", "sha256")).issubset(v)


def _iter_refs(value: Any, path: str = ""):
    if _is_obj_ref(value):
        yield path or "/", "object", value
        return
    if _is_art_ref(value):
        yield path or "/", "artifact", value
        return
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _iter_refs(v, f"{path}/{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _iter_refs(v, f"{path}/{i}")


def generic_refs_resolve(obj, state, catalog):
    issues=[]
    # Dependencies and supersedes are also intentionally checked.
    for path, kind, ref in _iter_refs(obj):
        # Ignore self identity-like embedded structures only if they are not refs.
        resolved = state.resolve_object(ref) if kind == "object" else state.resolve_artifact(ref)
        if resolved is None:
            code = "OBJECT_REF_UNRESOLVED" if kind == "object" else "ARTIFACT_REF_UNRESOLVED"
            ident = ref.get("id") or ref.get("artifact_id")
            issues.append(I(code, f"Exact {kind} reference {ident}@{ref.get('version')} does not resolve.", obj, path=path))
            continue
        if kind == "artifact" and ref.get("sha256") != resolved.get("sha256"):
            issues.append(I("ARTIFACT_REF_HASH_MISMATCH", "ArtifactRef sha256 does not match the resolved artifact record.", obj, path=path))
    return issues


def base_lineage(obj, state, catalog):
    issues=[]
    v=int(obj.get("version",1))
    sup=obj.get("supersedes")
    if v == 1 and sup is not None:
        issues.append(I("V1_SUPERSEDES_FORBIDDEN", "Version 1 must not supersede an earlier version.", obj, path="/supersedes"))
    if v > 1:
        if not sup:
            issues.append(I("SUPERSEDES_REQUIRED", "Object version >1 requires an exact supersedes reference.", obj, path="/supersedes"))
        else:
            prev=state.resolve_object(sup)
            if prev:
                if prev.get("id") != obj.get("id"):
                    issues.append(I("SUPERSEDES_ID_MISMATCH", "Supersedes must remain in the same stable-ID lineage.", obj, path="/supersedes"))
                if prev.get("object_type") != obj.get("object_type"):
                    issues.append(I("SUPERSEDES_TYPE_MISMATCH", "Superseded object type must match.", obj, path="/supersedes"))
                if int(sup.get("version",0)) != v-1:
                    issues.append(I("OBJECT_VERSION_GAP", "Object versions must be contiguous with no gaps.", obj, path="/supersedes"))
    return issues


def base_status_stale(obj, state, catalog):
    issues=[]
    stale=obj.get("stale",{})
    is_stale=bool(stale.get("is_stale"))
    status=obj.get("status")
    if is_stale and status not in {"STALE","BLOCKED","SUPERSEDED","ARCHIVED","REJECTED"}:
        issues.append(I("STALE_STATUS_MISMATCH", "An object with stale.is_stale=true cannot remain CURRENT.", obj, path="/status"))
    if not is_stale and status == "STALE":
        issues.append(I("STALE_STATUS_MISMATCH", "status=STALE requires stale.is_stale=true.", obj, path="/stale"))
    cids=[c.get("constraint_id") for c in obj.get("human_constraints",[]) if isinstance(c,dict)]
    if len(cids)!=len(set(cids)):
        issues.append(I("HUMAN_CONSTRAINT_DUPLICATE", "Human constraint IDs must be unique within an object version.", obj, path="/human_constraints"))
    return issues


def project_rules(obj,state,catalog):
    r=obj.get("target",{}).get("runtime_minutes",{})
    if r and r.get("min",0)>r.get("max",0):
        return [I("PROJECT_RUNTIME_RANGE_INVALID","Runtime minimum exceeds maximum.",obj,path="/target/runtime_minutes")]
    return []


def source_rules(obj,state,catalog):
    issues=[]
    if obj.get("derived_from"):
        for ref in obj["derived_from"]:
            if state.object_type(ref) not in {None,"SOURCE"}:
                issues.append(I("SOURCE_DERIVATION_TYPE_INVALID","SOURCE.derived_from may reference SOURCE objects only.",obj,path="/derived_from"))
    return issues


def evidence_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("source_ref",{})) not in {None,"SOURCE"}:
        issues.append(I("EVIDENCE_SOURCE_TYPE_INVALID","EVIDENCE.source_ref must resolve to SOURCE.",obj,path="/source_ref"))
    loc=obj.get("locator",{})
    if loc.get("type")=="VIDEO_TIME_RANGE" and loc.get("end_seconds",0)<=loc.get("start_seconds",0):
        issues.append(I("EVIDENCE_LOCATOR_INVALID","Video evidence end_seconds must be greater than start_seconds.",obj,path="/locator"))
    if obj.get("evidence_kind")=="QUOTE":
        q=obj.get("quote")
        if not q or not q.get("original") or not q.get("context"):
            issues.append(I("QUOTE_CONTEXT_REQUIRED","Quote evidence requires original text and context.",obj,path="/quote"))
    if obj.get("evidence_kind")=="TECHNICAL":
        t=obj.get("technical")
        if not t or not t.get("method") or "limitations" not in t:
            issues.append(I("TECHNICAL_METHOD_LIMITATIONS_REQUIRED","Technical evidence requires method and limitations.",obj,path="/technical"))
    return issues


def claim_rules(obj,state,catalog):
    issues=[]
    seen=set()
    links=obj.get("evidence_links",[])
    for idx,link in enumerate(links):
        ref=link.get("evidence_ref",{})
        key=(ref.get("id"),ref.get("version"))
        if key in seen:
            issues.append(I("CLAIM_EVIDENCE_LINK_DUPLICATE","One exact Evidence version may appear only once in a Claim.",obj,path=f"/evidence_links/{idx}"))
        seen.add(key)
        typ=state.object_type(ref)
        if typ not in {None,"EVIDENCE"}:
            issues.append(I("CLAIM_EVIDENCE_TYPE_INVALID","Claim evidence links must reference EVIDENCE.",obj,path=f"/evidence_links/{idx}/evidence_ref"))
    if obj.get("verification_state")=="DISPROVEN" and not any(x.get("relation")=="CONTRADICTS" for x in links):
        issues.append(I("DISPROVEN_WITHOUT_COUNTER_EVIDENCE","DISPROVEN requires at least one contradictory EvidenceLink.",obj,path="/verification_state"))
    pu=obj.get("production_use",{})
    if pu.get("narration_allowed") is False and pu.get("language_mode")!="PROHIBITED":
        issues.append(I("CLAIM_PRODUCTION_USE_INCONSISTENT","narration_allowed=false requires language_mode=PROHIBITED.",obj,path="/production_use"))
    return issues


def contradiction_rules(obj,state,catalog):
    issues=[]
    for ref in obj.get("claim_refs",[]):
        if state.object_type(ref) not in {None,"CLAIM"}:
            issues.append(I("CONTRADICTION_CLAIM_TYPE_INVALID","Contradiction claim_refs must reference CLAIM.",obj,path="/claim_refs"))
    for ref in obj.get("evidence_refs",[]):
        if state.object_type(ref) not in {None,"EVIDENCE"}:
            issues.append(I("CONTRADICTION_EVIDENCE_TYPE_INVALID","Contradiction evidence_refs must reference EVIDENCE.",obj,path="/evidence_refs"))
    r=obj.get("resolution",{})
    if r.get("state")=="RESOLVED" and not r.get("resolution_note"):
        issues.append(I("CONTRADICTION_RESOLUTION_NOTE_REQUIRED","Resolved contradictions require a resolution note.",obj,path="/resolution"))
    if r.get("state")=="RESOLVED" and not r.get("resolved_at"):
        issues.append(I("CONTRADICTION_RESOLVED_AT_REQUIRED","Resolved contradictions require resolved_at.",obj,path="/resolution"))
    return issues


def research_gap_rules(obj,state,catalog):
    issues=[]
    st=obj.get("state")
    if st=="RESOLVED" and not obj.get("resolution"):
        issues.append(I("RESEARCH_GAP_RESOLUTION_REQUIRED","RESOLVED research gaps require resolution evidence/summary.",obj,path="/resolution"))
    for ref in obj.get("research_attempt_refs",[]):
        art=state.resolve_artifact(ref)
        if art and art.get("artifact_type")!="RESEARCH_ATTEMPT_LOG":
            issues.append(I("RESEARCH_ATTEMPT_ARTIFACT_TYPE_INVALID","research_attempt_refs must point to RESEARCH_ATTEMPT_LOG artifacts.",obj,path="/research_attempt_refs"))
    return issues


def search_rules(obj,state,catalog):
    if state.object_type(obj.get("target_beat_ref",{})) not in {None,"NARRATION_BEAT"}:
        return [I("SEARCH_TARGET_TYPE_INVALID","SEARCH target must be an exact NARRATION_BEAT.",obj,path="/target_beat_ref")]
    return []


def search_result_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("search_ref",{})) not in {None,"SEARCH"}:
        issues.append(I("SEARCH_RESULT_SEARCH_TYPE_INVALID","SEARCH_RESULT.search_ref must reference SEARCH.",obj,path="/search_ref"))
    if obj.get("source_ref") and state.object_type(obj["source_ref"]) not in {None,"SOURCE"}:
        issues.append(I("SEARCH_RESULT_SOURCE_TYPE_INVALID","SEARCH_RESULT.source_ref must reference SOURCE.",obj,path="/source_ref"))
    state_name=obj.get("candidate_state")
    if state_name in {"VIABLE","SELECTED","PROMOTED_TO_ASSET"}:
        ins=obj.get("inspection") or {}
        if not obj.get("source_ref"):
            issues.append(I("VIABLE_CANDIDATE_SOURCE_REQUIRED","Viable/selected/promoted candidate requires verified source_ref.",obj,path="/source_ref"))
        if not ins.get("exact_moment_found") or not ins.get("candidate_locator") or not ins.get("viewer_takeaway_supported"):
            issues.append(I("VIABLE_CANDIDATE_INSPECTION_INCOMPLETE","Viable candidate requires exact verified moment, locator, and supported viewer takeaway.",obj,path="/inspection"))
        if ins.get("match_type")=="MISMATCH":
            issues.append(I("VIABLE_CANDIDATE_MATCH_INVALID","A viable candidate cannot have match_type=MISMATCH.",obj,path="/inspection/match_type"))
    if state_name=="REJECTED" and not obj.get("rejection"):
        issues.append(I("REJECTED_CANDIDATE_REASON_REQUIRED","Rejected candidate requires rejection reason.",obj,path="/rejection"))
    if state_name=="PROMOTED_TO_ASSET" and not obj.get("promoted_asset_ref"):
        issues.append(I("PROMOTED_ASSET_REF_REQUIRED","PROMOTED_TO_ASSET candidate requires promoted_asset_ref.",obj,path="/promoted_asset_ref"))
    return issues


def asset_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("origin_search_result_ref",{})) not in {None,"SEARCH_RESULT"}:
        issues.append(I("ASSET_ORIGIN_TYPE_INVALID","Asset origin must reference SEARCH_RESULT.",obj,path="/origin_search_result_ref"))
    if state.object_type(obj.get("source_ref",{})) not in {None,"SOURCE"}:
        issues.append(I("ASSET_SOURCE_TYPE_INVALID","Asset source_ref must reference SOURCE.",obj,path="/source_ref"))
    if obj.get("workflow_state") in {"ACQUIRED","FILE_VERIFIED","CATALOGED","APPROVED"} and not obj.get("original_file"):
        issues.append(I("ACQUIRED_ASSET_FILE_REQUIRED","Acquired-or-later asset state requires immutable original_file metadata.",obj,path="/original_file"))
    if obj.get("rights",{}).get("status")=="DO_NOT_USE" and obj.get("workflow_state")=="APPROVED":
        issues.append(I("ASSET_RIGHTS_BLOCK","DO_NOT_USE asset cannot be APPROVED for production.",obj,path="/rights/status"))
    return issues


def segment_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("asset_ref",{})) not in {None,"ASSET"}:
        issues.append(I("SEGMENT_ASSET_TYPE_INVALID","Segment must reference ASSET.",obj,path="/asset_ref"))
    sel=obj.get("selector",{})
    if sel.get("type")=="VIDEO_TIME_RANGE" and sel.get("end_seconds",0)<=sel.get("start_seconds",0):
        issues.append(I("SEGMENT_SELECTOR_INVALID","Video segment end_seconds must be greater than start_seconds.",obj,path="/selector"))
    if obj.get("production_state") in {"READY","APPROVED","PRODUCTION_READY"}:
        asset=state.resolve_object(obj.get("asset_ref"))
        if asset and asset.get("rights",{}).get("status") in {"DO_NOT_USE","UNKNOWN"}:
            issues.append(I("SEGMENT_RIGHTS_NOT_READY","Production-ready segment cannot derive from blocked/unknown-rights asset.",obj,path="/asset_ref"))
    return issues


def act_rules(obj,state,catalog):
    if state.object_type(obj.get("project_ref",{})) not in {None,"PROJECT"}:
        return [I("ACT_PROJECT_TYPE_INVALID","ACT.project_ref must reference PROJECT.",obj,path="/project_ref")]
    return []


def scene_rules(obj,state,catalog):
    if state.object_type(obj.get("act_ref",{})) not in {None,"ACT"}:
        return [I("SCENE_ACT_TYPE_INVALID","SCENE.act_ref must reference ACT.",obj,path="/act_ref")]
    return []


def beat_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("scene_ref",{})) not in {None,"SCENE"}:
        issues.append(I("BEAT_SCENE_TYPE_INVALID","NARRATION_BEAT.scene_ref must reference SCENE.",obj,path="/scene_ref"))
    for i,b in enumerate(obj.get("claim_bindings",[])):
        if state.object_type(b.get("claim_ref",{})) not in {None,"CLAIM"}:
            issues.append(I("BEAT_CLAIM_TYPE_INVALID","Beat claim bindings must reference CLAIM.",obj,path=f"/claim_bindings/{i}/claim_ref"))
    for i,ref in enumerate(obj.get("evidence_anchor_refs",[])):
        if state.object_type(ref) not in {None,"EVIDENCE"}:
            issues.append(I("BEAT_EVIDENCE_ANCHOR_TYPE_INVALID","Beat evidence anchors must reference EVIDENCE only.",obj,path=f"/evidence_anchor_refs/{i}"))
    # Narration may never be stronger than the strictest bound claim production mode.
    mode_rank={"PROHIBITED":0,"UNRESOLVED":1,"THEORY":2,"INTERPRETIVE":2,"QUALIFIED":3,"ATTRIBUTED":4,"DIRECT":5}
    nar=(obj.get("narration") or {}).get("language_mode")
    if nar and obj.get("claim_bindings"):
        allowed=[]
        for b in obj["claim_bindings"]:
            cl=state.resolve_object(b.get("claim_ref"))
            if cl:
                allowed.append((cl.get("production_use") or {}).get("language_mode","PROHIBITED"))
        if allowed:
            ceiling=min(mode_rank.get(x,0) for x in allowed)
            if mode_rank.get(nar,0)>ceiling:
                issues.append(I("NARRATION_CERTAINTY_EXCEEDS_RESEARCH","Beat narration language is stronger than the bound research allows.",obj,path="/narration/language_mode"))
    pp=obj.get("promise_payoff") or {}
    if pp.get("role") in {"PROMISE","PAYOFF"} and not pp.get("paired_beat_ref"):
        issues.append(I("PROMISE_PAYOFF_PAIR_REQUIRED","PROMISE/PAYOFF beat requires paired_beat_ref.",obj,path="/promise_payoff"))
    return issues


def voice_block_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("voice_profile_ref",{})) not in {None,"VOICE_PROFILE"}:
        issues.append(I("VOICE_BLOCK_PROFILE_TYPE_INVALID","Voice block profile must reference VOICE_PROFILE.",obj,path="/voice_profile_ref"))
    for ref in obj.get("source_beat_refs",[]):
        if state.object_type(ref) not in {None,"NARRATION_BEAT"}:
            issues.append(I("VOICE_BLOCK_BEAT_TYPE_INVALID","Voice block source_beat_refs must reference NARRATION_BEAT.",obj,path="/source_beat_refs"))
    art=state.resolve_artifact(obj.get("tts_script_ref"))
    if art and art.get("artifact_type")!="TTS_READY_SCRIPT":
        issues.append(I("VOICE_BLOCK_TTS_ARTIFACT_INVALID","tts_script_ref must resolve to TTS_READY_SCRIPT.",obj,path="/tts_script_ref"))
    return issues


def design_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("project_ref",{})) not in {None,"PROJECT"}:
        issues.append(I("DESIGN_PROJECT_TYPE_INVALID","DESIGN_DNA.project_ref must reference PROJECT.",obj,path="/project_ref"))
    for idx,r in enumerate(obj.get("rules",[])):
        # Frozen contract: every rule traces to reference or explicit human decision.
        if isinstance(r,dict) and not (r.get("reference_refs") or r.get("human_decision_ref") or r.get("basis")):
            issues.append(I("DESIGN_RULE_BASIS_REQUIRED","Every design rule needs traceable reference/human basis.",obj,path=f"/rules/{idx}",severity="WARNING"))
    return issues


def layer_rules(obj,state,catalog):
    issues=[]
    role=obj.get("stack_role")
    if role!="BASE" and not obj.get("comprehension_purpose"):
        issues.append(I("LAYER_WITHOUT_COMPREHENSION_PURPOSE","Every non-base layer requires a comprehension purpose.",obj,path="/comprehension_purpose"))
    motion=obj.get("motion",{})
    if motion.get("decision")=="MOTION_REQUIRED" and not motion.get("purpose"):
        issues.append(I("MOTION_WITHOUT_PURPOSE","MOTION_REQUIRED requires an explicit comprehension/pacing purpose.",obj,path="/motion/purpose"))
    c=obj.get("content",{})
    typ=c.get("type")
    if typ=="MEDIA_SEGMENT":
        if not c.get("segment_ref"):
            issues.append(I("MEDIA_LAYER_SEGMENT_REQUIRED","MEDIA_SEGMENT layer requires segment_ref.",obj,path="/content/segment_ref"))
        elif state.object_type(c["segment_ref"]) not in {None,"SEGMENT"}:
            issues.append(I("LAYER_SEGMENT_TYPE_INVALID","Media layer segment_ref must reference SEGMENT.",obj,path="/content/segment_ref"))
    if typ=="SOURCE_LABEL":
        if not c.get("source_ref"):
            issues.append(I("SOURCE_LABEL_SOURCE_REQUIRED","SOURCE_LABEL requires source_ref.",obj,path="/content/source_ref"))
        elif state.object_type(c["source_ref"]) not in {None,"SOURCE"}:
            issues.append(I("SOURCE_LABEL_SOURCE_INVALID","SOURCE_LABEL source_ref must reference SOURCE.",obj,path="/content/source_ref"))
    if typ=="THREE_D":
        if not c.get("evidence_basis"):
            issues.append(I("THREE_D_WITHOUT_EVIDENCE","3D layer requires evidence_basis.",obj,path="/content/evidence_basis"))
        for ref in c.get("evidence_basis",[]):
            if state.object_type(ref) not in {None,"EVIDENCE"}:
                issues.append(I("THREE_D_EVIDENCE_TYPE_INVALID","3D evidence_basis must reference EVIDENCE.",obj,path="/content/evidence_basis"))
        if set(c.get("known",[])) & set(c.get("unknown",[])):
            issues.append(I("THREE_D_KNOWN_UNKNOWN_CONFLICT","A 3D fact cannot be both known and unknown.",obj,path="/content"))
    return issues


def cue_rules(obj,state,catalog):
    issues=[]
    mv=state.resolve_artifact((obj.get("timing_source") or {}).get("master_voice"))
    tm=state.resolve_artifact((obj.get("timing_source") or {}).get("timing_map"))
    if mv and mv.get("artifact_type")!="MASTER_VOICE":
        issues.append(I("CUE_MASTER_VOICE_TYPE_INVALID","Cue master_voice must resolve to MASTER_VOICE.",obj,path="/timing_source/master_voice"))
    if tm and tm.get("artifact_type")!="VOICE_TIMING_MAP":
        issues.append(I("CUE_TIMING_MAP_TYPE_INVALID","Cue timing_map must resolve to VOICE_TIMING_MAP.",obj,path="/timing_source/timing_map"))
    a=obj.get("animation") or {}
    if {"start_offset_seconds","key_offset_seconds","end_offset_seconds"}.issubset(a):
        if not (a["start_offset_seconds"] <= a["key_offset_seconds"] <= a["end_offset_seconds"]):
            issues.append(I("CUE_ANIMATION_ORDER_INVALID","Cue animation offsets must satisfy start <= key <= end.",obj,path="/animation"))
    return issues


def shot_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("scene_ref",{})) not in {None,"SCENE"}:
        issues.append(I("SHOT_SCENE_INVALID","Shot scene_ref must reference SCENE.",obj,path="/scene_ref"))
    roles=[b.get("role") for b in obj.get("beat_bindings",[])]
    if roles.count("PRIMARY")!=1:
        issues.append(I("SHOT_PRIMARY_BEAT_INVALID","Each Shot must have exactly one PRIMARY beat binding.",obj,path="/beat_bindings"))
    for b in obj.get("beat_bindings",[]):
        if state.object_type(b.get("beat_ref",{})) not in {None,"NARRATION_BEAT"}:
            issues.append(I("SHOT_BEAT_BINDING_INVALID","Shot beat bindings must reference NARRATION_BEAT.",obj,path="/beat_bindings"))
    layers=[state.resolve_object(r) for r in obj.get("layer_refs",[])]
    layers=[x for x in layers if x]
    base=[x for x in layers if x.get("object_type")=="LAYER" and x.get("stack_role")=="BASE"]
    if len(base)==0:
        issues.append(I("SHOT_BASE_LAYER_MISSING","Shot requires exactly one BASE layer.",obj,path="/layer_refs"))
    elif len(base)>1:
        issues.append(I("SHOT_MULTIPLE_BASE_LAYERS","Shot may not contain multiple BASE layers.",obj,path="/layer_refs"))
    lkeys={(r.get("id"),r.get("version")) for r in obj.get("layer_refs",[])}
    for cref in obj.get("cue_refs",[]):
        cue=state.resolve_object(cref)
        if cue and cue.get("object_type")!="CUE":
            issues.append(I("SHOT_CUE_TYPE_INVALID","shot.cue_refs must reference CUE.",obj,path="/cue_refs"))
        if cue:
            for t in cue.get("target_layer_refs",[]):
                if (t.get("id"),t.get("version")) not in lkeys:
                    issues.append(I("CUE_TARGET_NOT_IN_SHOT","Cue target layer is not part of this Shot.",obj,path="/cue_refs",related=(f"{cue['id']}@{cue['version']}",)))
    tr=obj.get("transition_out",{})
    if tr.get("type")!="CUT" and not tr.get("reason"):
        issues.append(I("SPECIAL_TRANSITION_WITHOUT_REASON","Non-CUT transition requires a narrative reason.",obj,path="/transition_out/reason"))
    # Absolute timing can be locally checked. Anchor timing is resolved by timing-map engine later.
    s=(obj.get("timing") or {}).get("start",{})
    e=(obj.get("timing") or {}).get("end",{})
    if s.get("type")==e.get("type")=="ABSOLUTE_MASTER_TIME" and e.get("seconds",0)<=s.get("seconds",0):
        issues.append(I("SHOT_TIMING_RANGE_INVALID","Shot end time must be after start time.",obj,path="/timing"))
    return issues


def approval_rules(obj,state,catalog):
    issues=[]
    target=state.resolve_target(obj.get("target"))
    if target is None:
        return issues
    if "id" in obj.get("target",{}):
        if not obj.get("target_decision_sha256"):
            issues.append(I("APPROVAL_DECISION_HASH_REQUIRED","Core-object approval requires target_decision_sha256.",obj,path="/target_decision_sha256"))
        else:
            dh=decision_hash(target,catalog.derived_root_fields(target.get("object_type","")))
            if dh!=obj.get("target_decision_sha256"):
                issues.append(I("APPROVAL_TARGET_HASH_MISMATCH","Approval decision hash does not match exact target decision content.",obj,path="/target_decision_sha256"))
    if not obj.get("review_context"):
        issues.append(I("APPROVAL_REVIEW_CONTEXT_REQUIRED","Approval requires exact Review Context artifact.",obj,path="/review_context"))
    else:
        rc=state.resolve_artifact(obj["review_context"])
        if rc:
            allowed={"REVIEW_PACKAGE"}
            # Contract repair Build 024: VOICE approvals may use a pre-scene
            # VOICE_REVIEW_PACKAGE. Historical visual REVIEW_PACKAGE contexts
            # remain valid for backwards compatibility. Other approval classes
            # keep the original REVIEW_PACKAGE-only rule.
            if obj.get("approval_class")=="VOICE": allowed.add("VOICE_REVIEW_PACKAGE")
            if obj.get("approval_class")=="DESIGN_DNA": allowed.add("DESIGN_DNA_REVIEW_PACKAGE")
            # Erratum Build 029: the project Production Lock is reviewed before
            # lock artifacts exist. The exact closure package may therefore be
            # used for both per-Shot visual approvals and the final lock approval.
            if obj.get("approval_class") in {"SHOT_VISUAL","PRODUCTION_LOCK"}: allowed.add("PRODUCTION_LOCK_REVIEW_PACKAGE")
            # Erratum Build 033: delivery/release approval reviews the exact pre-publish candidate package.
            if obj.get("approval_class")=="RELEASE": allowed.add("DELIVERY_REVIEW_PACKAGE")
            if rc.get("artifact_type") not in allowed:
                issues.append(I("APPROVAL_REVIEW_CONTEXT_INVALID",f"review_context must resolve to one of {sorted(allowed)} for {obj.get('approval_class')} approval.",obj,path="/review_context"))
    return issues


def edit_request_rules(obj,state,catalog):
    issues=[]
    d=obj.get("directive",{})
    if d.get("type")=="RELEASE_CONSTRAINT" and not d.get("constraint_id"):
        issues.append(I("HUMAN_CONSTRAINT_RELEASE_ID_REQUIRED","RELEASE_CONSTRAINT requires constraint_id.",obj,path="/directive"))
    if d.get("type")=="PRESERVE" and not d.get("instruction"):
        issues.append(I("PRESERVE_DIRECTIVE_INSTRUCTION_REQUIRED","PRESERVE directive requires explicit instruction.",obj,path="/directive"))
    return issues


def revision_rules(obj,state,catalog):
    issues=[]
    for idx,ch in enumerate(obj.get("changes",[])):
        before=ch.get("from") or ch.get("from_ref")
        after=ch.get("to") or ch.get("to_ref")
        if before and after:
            if before.get("id")!=after.get("id"):
                issues.append(I("REVISION_LINEAGE_MISMATCH","Revision before/after must share stable object ID.",obj,path=f"/changes/{idx}"))
            if int(after.get("version",0))<=int(before.get("version",0)):
                issues.append(I("REVISION_VERSION_NOT_FORWARD","Revision target version must move forward.",obj,path=f"/changes/{idx}"))
            b=state.resolve_object(before); a=state.resolve_object(after)
            if b and a:
                active={c.get("constraint_id"):c for c in b.get("human_constraints",[])}
                after_ids={c.get("constraint_id") for c in a.get("human_constraints",[])}
                preserved=set(obj.get("preserved_constraints",[]))
                for cid in active:
                    if cid not in after_ids and cid in preserved:
                        issues.append(I("HUMAN_CONSTRAINT_NOT_PRESERVED",f"Preserved constraint {cid} is missing from revision target.",obj,path=f"/changes/{idx}"))
    return issues


def render_job_rules(obj,state,catalog):
    issues=[]
    if obj.get("render_level")=="FINAL" and not obj.get("production_lock"):
        issues.append(I("FINAL_RENDER_PRODUCTION_LOCK_REQUIRED","FINAL render requires exact Production Lock.",obj,path="/production_lock"))
    lock=state.resolve_artifact(obj.get("production_lock")) if obj.get("production_lock") else None
    if lock and lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST":
        issues.append(I("RENDER_PRODUCTION_LOCK_TYPE_INVALID","production_lock must resolve to PRODUCTION_LOCK_MANIFEST.",obj,path="/production_lock"))
    if lock and obj.get("render_level")=="FINAL":
        allowed=set()
        for field in ("shots","layers","cues"):
            for r in lock.get(field,[]):
                allowed.add(("object",r.get("id"),r.get("version")))
        # lock itself and pinned artifacts are valid render inputs.
        for r in (obj.get("input_snapshot") or {}).get("inputs",[]):
            if "id" in r and ("object",r.get("id"),r.get("version")) not in allowed:
                issues.append(I("RENDER_INPUT_NOT_IN_PRODUCTION_LOCK","FINAL Render input object is not frozen by the Production Lock.",obj,path="/input_snapshot/inputs"))
    limit=(obj.get("execution_policy") or {}).get("transient_retry_limit")
    if limit is not None and limit>2:
        issues.append(I("RENDER_RETRY_LIMIT_EXCEEDED","Transient render retry limit may not exceed 2.",obj,path="/execution_policy/transient_retry_limit"))
    return issues


def render_manifest_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("render_job_ref",{})) not in {None,"RENDER_JOB"}:
        issues.append(I("RENDER_MANIFEST_JOB_TYPE_INVALID","Render manifest must reference RENDER_JOB.",obj,path="/render_job_ref"))
    if obj.get("outcome")=="SUCCESS" and (obj.get("technical_validation") or {}).get("state")!="PASS":
        issues.append(I("RENDER_SUCCESS_WITHOUT_TECHNICAL_PASS","Successful render manifest requires technical validation PASS.",obj,path="/technical_validation"))
    return issues


def qa_issue_rules(obj,state,catalog):
    issues=[]
    st=obj.get("workflow_state")
    rc=obj.get("root_cause",{})
    if st in {"REPAIR_PLANNED","REPAIR_IN_PROGRESS","RETEST_REQUIRED","RESOLVED"} and rc.get("state") not in {"IDENTIFIED","BOUNDED_UNKNOWN"}:
        issues.append(I("REPAIR_WITHOUT_ROOT_CAUSE","Repair lifecycle cannot proceed without identified/bounded root cause.",obj,path="/root_cause"))
    if st=="RESOLVED" and not obj.get("verification_report_ref"):
        issues.append(I("QA_ISSUE_RESOLVED_WITHOUT_RETEST","Resolved QA issue requires verification QA report reference.",obj,path="/verification_report_ref"))
    return issues


def qa_report_rules(obj,state,catalog):
    issues=[]
    sev=Counter()
    blocking=False
    for ref in obj.get("issue_refs",[]):
        issue=state.resolve_object(ref)
        if not issue: continue
        if issue.get("object_type")!="QA_ISSUE":
            issues.append(I("QA_REPORT_ISSUE_TYPE_INVALID","QA report issue_refs must reference QA_ISSUE.",obj,path="/issue_refs"))
            continue
        sev[issue.get("severity")]+=1
        if issue.get("severity") in {"MAJOR","CRITICAL"} and issue.get("workflow_state") not in {"RESOLVED","ACCEPTED_EXCEPTION"}:
            blocking=True
    summary=obj.get("summary",{})
    for key in ("critical","major","minor"):
        if key in summary and summary[key] != sev[key.upper()]:
            issues.append(I("QA_REPORT_SUMMARY_MISMATCH",f"QA report summary.{key} does not match referenced issues.",obj,path=f"/summary/{key}"))
    if blocking and obj.get("result")=="PASS":
        issues.append(I("QA_REPORT_PASS_WITH_BLOCKING_ISSUE","QA report cannot PASS with unresolved MAJOR/CRITICAL issue.",obj,path="/result"))
    return issues


def checkpoint_rules(obj,state,catalog):
    issues=[]
    integ=obj.get("integrity_summary")
    if integ=="PASS":
        # Every important artifact ref has already gone through generic exact-ref/hash checks.
        if any(state.resolve_artifact(r) is None for r in obj.get("important_artifact_refs",[])):
            issues.append(I("CHECKPOINT_INTEGRITY_FALSE_PASS","Checkpoint cannot report PASS with missing important artifacts.",obj,path="/integrity_summary"))
    return issues


def operation_rules(obj,state,catalog):
    issues=[]
    attempts=obj.get("attempts",[])
    nums=[a.get("attempt") for a in attempts]
    if nums and nums != list(range(1,len(nums)+1)):
        issues.append(I("OPERATION_ATTEMPT_SEQUENCE_INVALID","Operation attempts must be contiguous starting at 1.",obj,path="/attempts"))
    if obj.get("workflow_state")=="SUCCEEDED" and attempts and not attempts[-1].get("finished_at"):
        issues.append(I("OPERATION_SUCCESS_WITH_OPEN_ATTEMPT","Succeeded operation requires its final attempt to be finished.",obj,path="/attempts"))
    auth=obj.get("authorization") or {}
    cpref=auth.get("checkpoint_ref")
    if cpref and state.object_type(cpref) not in {None,"CHECKPOINT"}:
        issues.append(I("OPERATION_CHECKPOINT_TYPE_INVALID","Operation authorization checkpoint_ref must reference CHECKPOINT.",obj,path="/authorization/checkpoint_ref"))
    if obj.get("operation_type") in {"PUBLISH","DELETE_EXTERNAL"}:
        if auth.get("human_confirmed") is not True:
            issues.append(I("DESTRUCTIVE_OPERATION_NOT_AUTHORIZED","Destructive/public operation requires explicit Human confirmation.",obj,path="/authorization/human_confirmed"))
        cp=state.resolve_object(cpref) if cpref else None
        if not cp or cp.get("object_type")!="CHECKPOINT" or cp.get("integrity_summary")!="PASS":
            issues.append(I("OPERATION_CHECKPOINT_REQUIRED","Destructive/public operation requires a verified Checkpoint.",obj,path="/authorization/checkpoint_ref"))
    return issues


def incident_rules(obj,state,catalog):
    issues=[]
    if obj.get("severity")=="CRITICAL" and not (obj.get("containment") or {}).get("actions"):
        issues.append(I("CRITICAL_INCIDENT_UNCONTAINED","Critical incident requires explicit containment actions.",obj,path="/containment"))
    if obj.get("workflow_state") in {"RESOLVED","CLOSED"} and not obj.get("verification_refs"):
        issues.append(I("INCIDENT_RESOLVED_WITHOUT_VERIFICATION","Resolved/closed incident requires verification evidence.",obj,path="/verification_refs"))
    return issues


def release_rules(obj,state,catalog):
    issues=[]
    if state.object_type(obj.get("project_ref",{})) not in {None,"PROJECT"}:
        issues.append(I("RELEASE_PROJECT_TYPE_INVALID","Release project_ref must reference PROJECT.",obj,path="/project_ref"))
    lock=state.resolve_artifact(obj.get("production_lock"))
    if lock:
        if lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST":
            issues.append(I("RELEASE_PRODUCTION_LOCK_INVALID","Release production_lock must be PRODUCTION_LOCK_MANIFEST.",obj,path="/production_lock"))
        elif (lock.get("scope") or {}).get("type")!="PROJECT":
            issues.append(I("RELEASE_PROJECT_LOCK_REQUIRED","Release requires PROJECT-scope Production Lock.",obj,path="/production_lock"))
    out=state.resolve_artifact(obj.get("master_output"))
    if out and out.get("artifact_type")!="RENDER_OUTPUT":
        issues.append(I("RELEASE_MASTER_OUTPUT_INVALID","Release master_output must reference RENDER_OUTPUT.",obj,path="/master_output"))
    fam=state.resolve_artifact(obj.get("final_asset_manifest"))
    if fam and fam.get("artifact_type")!="FINAL_ASSET_MANIFEST":
        issues.append(I("RELEASE_FINAL_ASSET_MANIFEST_INVALID","Release final_asset_manifest must reference FINAL_ASSET_MANIFEST.",obj,path="/final_asset_manifest"))
    prov=state.resolve_artifact(obj.get("provenance_manifest"))
    if prov and prov.get("artifact_type")!="PROVENANCE_MANIFEST":
        issues.append(I("RELEASE_PROVENANCE_INVALID","Release provenance_manifest must reference PROVENANCE_MANIFEST.",obj,path="/provenance_manifest"))
    if obj.get("state")=="RELEASED":
        if not obj.get("released_at"):
            issues.append(I("RELEASED_AT_REQUIRED","RELEASED release requires released_at.",obj,path="/released_at"))
        types=set()
        for ref in obj.get("qa_reports",[]):
            q=state.resolve_object(ref)
            if q and q.get("object_type")!="QA_REPORT":
                issues.append(I("RELEASE_QA_REF_INVALID","Release qa_reports must reference QA_REPORT.",obj,path="/qa_reports"))
            if q:
                types.add(q.get("report_type"))
                if q.get("result") not in {"PASS","WARN"}:
                    issues.append(I("RELEASE_QA_INVALID","Release requires acceptable QA reports.",obj,path="/qa_reports"))
        for required in ("FULL_FILM_QA","DELIVERY_QA"):
            if required not in types: issues.append(I("RELEASE_REQUIRED_QA_MISSING",f"Release requires {required} report.",obj,path="/qa_reports"))
        op=state.resolve_object(obj.get("release_operation_ref")) if obj.get("release_operation_ref") else None
        if not op or op.get("object_type")!="OPERATION" or op.get("operation_type")!="PUBLISH" or op.get("workflow_state") not in {"SUCCEEDED","PARTIALLY_SUCCEEDED"}:
            issues.append(I("RELEASE_OPERATION_INCOMPLETE","Released Release requires a successful PUBLISH operation.",obj,path="/release_operation_ref"))
    if obj.get("supersedes_release_ref"):
        prev=state.resolve_object(obj["supersedes_release_ref"])
        if prev and (prev.get("object_type")!="RELEASE" or prev.get("state")!="RELEASED"):
            issues.append(I("RELEASE_LINEAGE_INVALID","supersedes_release_ref must reference an immutable RELEASED Release.",obj,path="/supersedes_release_ref"))
    return issues


def global_order_uniqueness(state: StateView,catalog: SchemaCatalog):
    issues=[]
    # A stable Core Object may have many immutable versions in StateView.  Order
    # uniqueness is about object identities, not historical versions of the same
    # identity.  Evaluate the latest candidate per stable ID so v1 + v2 never
    # self-collide merely because history is retained.
    latest={}
    for (oid,_),o in state.objects.items():
        prev=latest.get(oid)
        if prev is None or int(o.get("version",0))>int(prev.get("version",0)):
            latest[oid]=o
    groups=defaultdict(list)
    for o in latest.values():
        typ=o.get("object_type")
        if typ=="ACT": parent=("PROJECT",tuple(sorted((o.get("project_ref") or {}).items())))
        elif typ=="SCENE": parent=("ACT",tuple(sorted((o.get("act_ref") or {}).items())))
        elif typ=="NARRATION_BEAT": parent=("SCENE",tuple(sorted((o.get("scene_ref") or {}).items())))
        elif typ=="SHOT": parent=("SHOT_SCENE",tuple(sorted((o.get("scene_ref") or {}).items())))
        else: continue
        groups[(typ,parent)].append(o)
    for (typ,parent), items in groups.items():
        ctr=Counter(x.get("order") for x in items)
        for order,count in ctr.items():
            if count>1:
                for o in items:
                    if o.get("order")==order:
                        issues.append(I("ORDER_NOT_UNIQUE_WITHIN_PARENT",f"{typ} order {order} is duplicated within the same parent.",o,path="/order"))
    return issues


def global_id_type_consistency(state: StateView,catalog: SchemaCatalog):
    issues=[]
    types=defaultdict(set)
    for (oid,_),o in state.objects.items():
        types[oid].add(o.get("object_type"))
    for oid,ts in types.items():
        if len(ts)>1:
            for (x,_),o in state.objects.items():
                if x==oid:
                    issues.append(I("GLOBAL_ID_TYPE_COLLISION",f"Stable ID {oid} is used by multiple Core Object types: {sorted(ts)}.",o))
    return issues


def global_human_lock_carry_forward(state: StateView,catalog: SchemaCatalog):
    issues=[]
    byid=defaultdict(list)
    for (oid,_),o in state.objects.items(): byid[oid].append(o)
    for oid,items in byid.items():
        items.sort(key=lambda x:x["version"])
        for prev,cur in zip(items,items[1:]):
            if cur.get("version") != prev.get("version")+1: continue
            prevc={x.get("constraint_id") for x in prev.get("human_constraints",[])}
            curc={x.get("constraint_id") for x in cur.get("human_constraints",[])}
            released=set((cur.get("extensions") or {}).get("released_human_constraints",[]))
            missing=prevc-curc-released
            for cid in missing:
                issues.append(I("HUMAN_CONSTRAINT_NOT_CARRIED_FORWARD",f"Human-locked constraint {cid} disappeared without explicit release.",cur,path="/human_constraints"))
    return issues


OBJECT_RULES={
    "*": [generic_refs_resolve, base_lineage, base_status_stale],
    "PROJECT": [project_rules],
    "SOURCE": [source_rules],
    "EVIDENCE": [evidence_rules],
    "CLAIM": [claim_rules],
    "CONTRADICTION": [contradiction_rules],
    "RESEARCH_GAP": [research_gap_rules],
    "SEARCH": [search_rules],
    "SEARCH_RESULT": [search_result_rules],
    "ASSET": [asset_rules],
    "SEGMENT": [segment_rules],
    "ACT": [act_rules],
    "SCENE": [scene_rules],
    "NARRATION_BEAT": [beat_rules],
    "VOICE_BLOCK": [voice_block_rules],
    "DESIGN_DNA": [design_rules],
    "LAYER": [layer_rules],
    "CUE": [cue_rules],
    "SHOT": [shot_rules],
    "APPROVAL": [approval_rules],
    "EDIT_REQUEST": [edit_request_rules],
    "REVISION": [revision_rules],
    "RENDER_JOB": [render_job_rules],
    "RENDER_MANIFEST": [render_manifest_rules],
    "QA_ISSUE": [qa_issue_rules],
    "QA_REPORT": [qa_report_rules],
    "CHECKPOINT": [checkpoint_rules],
    "OPERATION": [operation_rules],
    "INCIDENT": [incident_rules],
    "RELEASE": [release_rules],
}

GLOBAL_RULES=[global_order_uniqueness, global_id_type_consistency, global_human_lock_carry_forward]

# ---------------- Artifact semantics ----------------

def AI(code: str, msg: str, art: dict[str, Any] | None = None, *, severity: str = "ERROR", path: str | None = None, related=()) -> ValidationIssue:
    target = None
    if art:
        target = f"{art.get('artifact_id','?')}@{art.get('version','?')}"
    return ValidationIssue(code, msg, severity, target, path, tuple(related))


def artifact_refs_resolve(art,state,catalog):
    issues=[]
    for path,kind,ref in _iter_refs(art):
        resolved=state.resolve_object(ref) if kind=="object" else state.resolve_artifact(ref)
        if resolved is None:
            ident=ref.get("id") or ref.get("artifact_id")
            code="OBJECT_REF_UNRESOLVED" if kind=="object" else "ARTIFACT_REF_UNRESOLVED"
            issues.append(AI(code,f"Exact {kind} reference {ident}@{ref.get('version')} does not resolve.",art,path=path))
        elif kind=="artifact" and ref.get("sha256")!=resolved.get("sha256"):
            issues.append(AI("ARTIFACT_REF_HASH_MISMATCH","ArtifactRef sha256 does not match resolved artifact.",art,path=path))
    return issues


def artifact_lineage(art,state,catalog):
    issues=[]
    v=int(art.get("version",1))
    sv=art.get("supersedes_version")
    if v==1 and sv is not None:
        issues.append(AI("ARTIFACT_V1_SUPERSEDES_FORBIDDEN","Artifact version 1 must not supersede an earlier version.",art,path="/supersedes_version"))
    if v>1:
        if sv is None:
            issues.append(AI("ARTIFACT_SUPERSEDES_REQUIRED","Artifact version >1 requires supersedes_version.",art,path="/supersedes_version"))
        elif int(sv)!=v-1:
            issues.append(AI("ARTIFACT_VERSION_GAP","Artifact versions must be contiguous.",art,path="/supersedes_version"))
        prev=state.artifacts.get((art.get("artifact_id"),v-1))
        if prev and prev.get("artifact_type")!=art.get("artifact_type"):
            issues.append(AI("ARTIFACT_TYPE_LINEAGE_MISMATCH","Artifact type may not change within a stable artifact ID lineage.",art,path="/artifact_type"))
    return issues


def voiceover_script_rules(art,state,catalog):
    issues=[]
    if state.object_type(art.get("project_ref",{})) not in {None,"PROJECT"}:
        issues.append(AI("VOICEOVER_PROJECT_TYPE_INVALID","VOICEOVER_SCRIPT_FINAL.project_ref must reference PROJECT.",art,path="/project_ref"))
    for i,b in enumerate(art.get("blocks",[])):
        beat=state.resolve_object(b.get("beat_ref"))
        if beat:
            if beat.get("object_type")!="NARRATION_BEAT":
                issues.append(AI("VOICEOVER_BEAT_TYPE_INVALID","Voiceover script blocks must reference NARRATION_BEAT.",art,path=f"/blocks/{i}/beat_ref"))
                continue
            expected=decision_hash(beat,catalog.derived_root_fields("NARRATION_BEAT"))
            if b.get("decision_sha256")!=expected:
                issues.append(AI("VOICEOVER_BEAT_DECISION_HASH_DRIFT","Compiled voiceover block decision hash no longer matches exact Beat.",art,path=f"/blocks/{i}/decision_sha256"))
            text=(beat.get("narration") or {}).get("text")
            if text is not None and b.get("narration_text")!=text:
                issues.append(AI("VOICEOVER_TEXT_DRIFT","Compiled narration text differs from the exact Beat narration authority.",art,path=f"/blocks/{i}/narration_text"))
    return issues


def tts_script_rules(art,state,catalog):
    issues=[]
    ss=state.resolve_artifact(art.get("source_script"))
    pd=state.resolve_artifact(art.get("pronunciation_dictionary"))
    vp=state.resolve_object(art.get("voice_profile_ref"))
    if ss and ss.get("artifact_type")!="VOICEOVER_SCRIPT_FINAL": issues.append(AI("TTS_SOURCE_SCRIPT_INVALID","TTS source_script must be VOICEOVER_SCRIPT_FINAL.",art,path="/source_script"))
    if pd and pd.get("artifact_type")!="PRONUNCIATION_DICTIONARY": issues.append(AI("TTS_DICTIONARY_INVALID","TTS pronunciation_dictionary must be PRONUNCIATION_DICTIONARY.",art,path="/pronunciation_dictionary"))
    if vp and vp.get("object_type")!="VOICE_PROFILE": issues.append(AI("TTS_VOICE_PROFILE_INVALID","TTS voice_profile_ref must reference VOICE_PROFILE.",art,path="/voice_profile_ref"))
    return issues


def master_voice_rules(art,state,catalog):
    issues=[]
    if state.object_type(art.get("project_ref",{})) not in {None,"PROJECT"}:
        issues.append(AI("MASTER_VOICE_PROJECT_INVALID","MASTER_VOICE.project_ref must reference PROJECT.",art,path="/project_ref"))
    for i,r in enumerate(art.get("source_voice_blocks",[])):
        if state.object_type(r) not in {None,"VOICE_BLOCK"}:
            issues.append(AI("MASTER_VOICE_BLOCK_TYPE_INVALID","MASTER_VOICE source_voice_blocks must reference VOICE_BLOCK.",art,path=f"/source_voice_blocks/{i}"))
    if (art.get("audio") or {}).get("duration_seconds",0)<=0:
        issues.append(AI("MASTER_VOICE_DURATION_INVALID","Master Voice duration must be greater than zero.",art,path="/audio/duration_seconds"))
    return issues


def voice_timing_map_rules(art,state,catalog):
    issues=[]
    mv=state.resolve_artifact(art.get("master_voice"))
    if mv and mv.get("artifact_type")!="MASTER_VOICE":
        issues.append(AI("TIMING_MAP_MASTER_VOICE_INVALID","Voice Timing Map must reference MASTER_VOICE.",art,path="/master_voice"))
    if mv:
        expected=(mv.get("audio") or {}).get("duration_seconds")
        actual=art.get("duration_seconds")
        if expected is not None and actual is not None and abs(float(expected)-float(actual))>0.005:
            issues.append(AI("VOICE_TIMING_DURATION_MISMATCH","Voice Timing Map duration must match Master Voice duration.",art,path="/duration_seconds"))
    return issues


def voice_lock_rules(art,state,catalog):
    issues=[]
    obj_types=[("voice_profile_ref","VOICE_PROFILE")]
    for f,t in obj_types:
        o=state.resolve_object(art.get(f))
        if o and o.get("object_type")!=t: issues.append(AI("VOICE_LOCK_OBJECT_TYPE_INVALID",f"{f} must reference {t}.",art,path=f"/{f}"))
    atypes={"voiceover_script":"VOICEOVER_SCRIPT_FINAL","tts_script":"TTS_READY_SCRIPT","pronunciation_dictionary":"PRONUNCIATION_DICTIONARY","master_voice":"MASTER_VOICE","timing_map":"VOICE_TIMING_MAP"}
    for f,t in atypes.items():
        a=state.resolve_artifact(art.get(f))
        if a and a.get("artifact_type")!=t: issues.append(AI("VOICE_LOCK_ARTIFACT_TYPE_INVALID",f"{f} must reference {t}.",art,path=f"/{f}"))
    for i,r in enumerate(art.get("voice_blocks",[])):
        if state.object_type(r) not in {None,"VOICE_BLOCK"}: issues.append(AI("VOICE_LOCK_BLOCK_TYPE_INVALID","Voice Lock voice_blocks must reference VOICE_BLOCK.",art,path=f"/voice_blocks/{i}"))
    tm=state.resolve_artifact(art.get("timing_map")); mv=state.resolve_artifact(art.get("master_voice"))
    if tm and mv:
        ref=tm.get("master_voice") or {}
        if (ref.get("artifact_id"),ref.get("version"))!=(mv.get("artifact_id"),mv.get("version")):
            issues.append(AI("VOICE_LOCK_TIMING_MAP_MASTER_MISMATCH","Voice Lock timing map must be built from the exact locked Master Voice.",art,path="/timing_map"))
    return issues


def motion_previs_rules(art,state,catalog):
    shot=state.resolve_object(art.get("shot_ref"))
    if shot and shot.get("object_type")!="SHOT": return [AI("MOTION_PREVIS_SHOT_INVALID","Motion previs shot_ref must reference SHOT.",art,path="/shot_ref")]
    ks=art.get("key_states") or {}
    if not all(k in ks for k in ("start","key","end")):
        return [AI("MOTION_PREVIS_TEMPORAL_STATES_REQUIRED","Critical motion previs must contain START/KEY/END states.",art,path="/key_states")]
    return []


def three_d_previs_rules(art,state,catalog):
    issues=[]
    if state.object_type(art.get("shot_ref",{})) not in {None,"SHOT"}: issues.append(AI("THREE_D_PREVIS_SHOT_INVALID","3D previs shot_ref must reference SHOT.",art,path="/shot_ref"))
    for r in art.get("evidence_basis",[]):
        if state.object_type(r) not in {None,"EVIDENCE"}: issues.append(AI("THREE_D_PREVIS_EVIDENCE_INVALID","3D previs evidence_basis must reference EVIDENCE.",art,path="/evidence_basis"))
    if set(art.get("known",[])) & set(art.get("unknown",[])):
        issues.append(AI("THREE_D_PREVIS_KNOWN_UNKNOWN_CONFLICT","3D previs known and unknown sets must be disjoint.",art,path="/known"))
    return issues


def scene_plan_rules(art,state,catalog):
    issues=[]
    if state.object_type(art.get("scene_ref",{})) not in {None,"SCENE"}: issues.append(AI("SCENE_PLAN_SCENE_INVALID","Scene Plan scene_ref must reference SCENE.",art,path="/scene_ref"))
    if state.object_type(art.get("design_dna_ref",{})) not in {None,"DESIGN_DNA"}: issues.append(AI("SCENE_PLAN_DNA_INVALID","Scene Plan design_dna_ref must reference DESIGN_DNA.",art,path="/design_dna_ref"))
    vl=state.resolve_artifact(art.get("voice_lock")); dt=state.resolve_artifact(art.get("design_tokens")); pool=state.resolve_artifact(art.get("scene_asset_pool"))
    if vl and vl.get("artifact_type")!="VOICE_LOCK_MANIFEST": issues.append(AI("SCENE_PLAN_VOICE_LOCK_INVALID","Scene Plan voice_lock must reference VOICE_LOCK_MANIFEST.",art,path="/voice_lock"))
    if dt and dt.get("artifact_type")!="EFFECTIVE_DESIGN_TOKENS": issues.append(AI("SCENE_PLAN_DESIGN_TOKENS_INVALID","Scene Plan design_tokens must reference EFFECTIVE_DESIGN_TOKENS.",art,path="/design_tokens"))
    if pool and pool.get("artifact_type")!="SCENE_ASSET_POOL": issues.append(AI("SCENE_PLAN_ASSET_POOL_INVALID","Scene Plan scene_asset_pool must reference SCENE_ASSET_POOL.",art,path="/scene_asset_pool"))
    for i,item in enumerate(art.get("shots",[])):
        ref=item.get("shot_ref") if isinstance(item,dict) and "shot_ref" in item else item if _is_obj_ref(item) else None
        if ref and state.object_type(ref) not in {None,"SHOT"}: issues.append(AI("SCENE_PLAN_SHOT_INVALID","Scene Plan shot entries must reference SHOT.",art,path=f"/shots/{i}"))
    return issues


def scene_preview_rules(art,state,catalog):
    issues=[]
    if state.object_type(art.get("scene_ref",{})) not in {None,"SCENE"}: issues.append(AI("SCENE_PREVIEW_SCENE_INVALID","Scene Preview scene_ref must reference SCENE.",art,path="/scene_ref"))
    sp=state.resolve_artifact(art.get("scene_plan"))
    if sp and sp.get("artifact_type")!="SCENE_PLAN": issues.append(AI("SCENE_PREVIEW_PLAN_INVALID","Scene Preview scene_plan must reference SCENE_PLAN.",art,path="/scene_plan"))
    if sp:
        plan_refs=[]
        for item in sp.get("shots",[]):
            ref=item.get("shot_ref") if isinstance(item,dict) and "shot_ref" in item else item if _is_obj_ref(item) else None
            if ref: plan_refs.append((ref.get("id"),ref.get("version")))
        prev_refs=[(r.get("id"),r.get("version")) for r in art.get("shots",[])]
        if plan_refs and prev_refs!=plan_refs:
            issues.append(AI("SCENE_PREVIEW_SHOT_SET_MISMATCH","Scene Preview must reflect exact ordered Shot versions from its Scene Plan.",art,path="/shots"))
    return issues


def review_package_rules(art,state,catalog):
    issues=[]
    pv=state.resolve_artifact(art.get("scene_preview")); pl=state.resolve_artifact(art.get("scene_plan"))
    if pv and pv.get("artifact_type")!="SCENE_PREVIEW": issues.append(AI("REVIEW_PACKAGE_PREVIEW_INVALID","Review Package scene_preview must reference SCENE_PREVIEW.",art,path="/scene_preview"))
    if pl and pl.get("artifact_type")!="SCENE_PLAN": issues.append(AI("REVIEW_PACKAGE_PLAN_INVALID","Review Package scene_plan must reference SCENE_PLAN.",art,path="/scene_plan"))
    if pv and pl:
        pvp=pv.get("scene_plan") or {}
        if (pvp.get("artifact_id"),pvp.get("version"))!=(pl.get("artifact_id"),pl.get("version")):
            issues.append(AI("REVIEW_PACKAGE_CONTEXT_MISMATCH","Review Package preview and plan must belong to the same exact Scene Plan.",art,path="/scene_plan"))
    return issues



def voice_review_package_rules(art,state,catalog):
    issues=[]
    scope=art.get("scope") or {}
    if scope.get("type")!="VOICE_LOCK":
        issues.append(AI("VOICE_REVIEW_SCOPE_INVALID","Voice Review Package scope.type must be VOICE_LOCK.",art,path="/scope/type"))
    lock=state.resolve_artifact(art.get("voice_lock")); mv=state.resolve_artifact(art.get("master_voice")); tm=state.resolve_artifact(art.get("timing_map")); tts=state.resolve_artifact(art.get("tts_script"))
    if lock and lock.get("artifact_type")!="VOICE_LOCK_MANIFEST": issues.append(AI("VOICE_REVIEW_LOCK_INVALID","voice_lock must reference VOICE_LOCK_MANIFEST.",art,path="/voice_lock"))
    if mv and mv.get("artifact_type")!="MASTER_VOICE": issues.append(AI("VOICE_REVIEW_MASTER_INVALID","master_voice must reference MASTER_VOICE.",art,path="/master_voice"))
    if tm and tm.get("artifact_type")!="VOICE_TIMING_MAP": issues.append(AI("VOICE_REVIEW_TIMING_INVALID","timing_map must reference VOICE_TIMING_MAP.",art,path="/timing_map"))
    if tts and tts.get("artifact_type")!="TTS_READY_SCRIPT": issues.append(AI("VOICE_REVIEW_TTS_INVALID","tts_script must reference TTS_READY_SCRIPT.",art,path="/tts_script"))
    if lock:
        pairs=(("master_voice",mv),("timing_map",tm),("tts_script",tts))
        for field,resolved in pairs:
            lr=lock.get(field) or {}
            ar=art.get(field) or {}
            if (lr.get("artifact_id"),lr.get("version"))!=(ar.get("artifact_id"),ar.get("version")):
                issues.append(AI("VOICE_REVIEW_CONTEXT_MISMATCH",f"{field} must match the exact dependency pinned by VOICE_LOCK_MANIFEST.",art,path=f"/{field}"))
    summary=art.get("review_summary") or {}
    if mv:
        audio=mv.get("audio") or {}
        if summary.get("audio_sha256")!=audio.get("sha256"): issues.append(AI("VOICE_REVIEW_AUDIO_HASH_MISMATCH","Review summary audio hash must match MASTER_VOICE.",art,path="/review_summary/audio_sha256"))
        if abs(float(summary.get("duration_seconds") or 0)-float(audio.get("duration_seconds") or 0))>0.01: issues.append(AI("VOICE_REVIEW_DURATION_MISMATCH","Review summary duration must match MASTER_VOICE.",art,path="/review_summary/duration_seconds"))
    if lock and int(summary.get("block_count") or 0)!=len(lock.get("voice_blocks") or []): issues.append(AI("VOICE_REVIEW_BLOCK_COUNT_MISMATCH","Review summary block count must match VOICE_LOCK_MANIFEST.",art,path="/review_summary/block_count"))
    return issues



def design_dna_review_package_rules(art,state,catalog):
    issues=[]
    scope=art.get("scope") or {}
    if scope.get("type")!="DESIGN_DNA":
        issues.append(AI("DESIGN_REVIEW_SCOPE_INVALID","Design DNA Review Package scope.type must be DESIGN_DNA.",art,path="/scope/type"))
    dna=state.resolve_object(art.get("design_dna_ref")); voice=state.resolve_artifact(art.get("voice_lock")); spine=state.resolve_artifact(art.get("narrative_spine")); tokens=state.resolve_artifact(art.get("effective_tokens"))
    if dna and dna.get("object_type")!="DESIGN_DNA": issues.append(AI("DESIGN_REVIEW_DNA_INVALID","design_dna_ref must reference DESIGN_DNA.",art,path="/design_dna_ref"))
    if voice and voice.get("artifact_type")!="VOICE_LOCK_MANIFEST": issues.append(AI("DESIGN_REVIEW_VOICE_INVALID","voice_lock must reference VOICE_LOCK_MANIFEST.",art,path="/voice_lock"))
    if spine and spine.get("artifact_type")!="NARRATIVE_SPINE": issues.append(AI("DESIGN_REVIEW_SPINE_INVALID","narrative_spine must reference NARRATIVE_SPINE.",art,path="/narrative_spine"))
    if tokens and tokens.get("artifact_type")!="EFFECTIVE_DESIGN_TOKENS": issues.append(AI("DESIGN_REVIEW_TOKENS_INVALID","effective_tokens must reference EFFECTIVE_DESIGN_TOKENS.",art,path="/effective_tokens"))
    if dna and tokens:
        dr=tokens.get("design_dna_ref") or {}; ar=art.get("design_dna_ref") or {}
        if (dr.get("id"),dr.get("version"))!=(ar.get("id"),ar.get("version")):
            issues.append(AI("DESIGN_REVIEW_TOKEN_DNA_MISMATCH","Effective design tokens must derive from the exact reviewed DESIGN_DNA version.",art,path="/effective_tokens"))
    summary=art.get("review_summary") or {}
    if dna:
        if int(summary.get("rule_count") or 0)!=len(dna.get("rules") or []): issues.append(AI("DESIGN_REVIEW_RULE_COUNT_MISMATCH","Review summary rule_count must match DESIGN_DNA.",art,path="/review_summary/rule_count"))
        if int(summary.get("reference_count") or 0)!=len(dna.get("references") or []): issues.append(AI("DESIGN_REVIEW_REFERENCE_COUNT_MISMATCH","Review summary reference_count must match DESIGN_DNA.",art,path="/review_summary/reference_count"))
        if summary.get("visual_thesis")!=(dna.get("design_intent") or {}).get("visual_thesis"): issues.append(AI("DESIGN_REVIEW_THESIS_MISMATCH","Review summary visual_thesis must match DESIGN_DNA.",art,path="/review_summary/visual_thesis"))
    return issues

def production_lock_review_package_rules(art,state,catalog):
    issues=[]
    scope=art.get("scope") or {}
    if scope.get("type")!="PROJECT_PRODUCTION_LOCK":
        issues.append(AI("PRODUCTION_LOCK_REVIEW_SCOPE_INVALID","Production Lock Review Package scope.type must be PROJECT_PRODUCTION_LOCK.",art,path="/scope/type"))
    project=state.resolve_object(scope.get("project_ref"))
    if project and project.get("object_type")!="PROJECT":
        issues.append(AI("PRODUCTION_LOCK_REVIEW_PROJECT_INVALID","scope.project_ref must reference PROJECT.",art,path="/scope/project_ref"))

    previews=[]; plans=[]; shots=[]; layers=[]; cues=[]; voices=[]; dnas=[]
    for i,r in enumerate(art.get("scene_previews",[])):
        x=state.resolve_artifact(r)
        if x:
            previews.append(x)
            if x.get("artifact_type")!="SCENE_PREVIEW": issues.append(AI("PRODUCTION_LOCK_REVIEW_PREVIEW_INVALID","scene_previews must reference SCENE_PREVIEW.",art,path=f"/scene_previews/{i}"))
    for i,r in enumerate(art.get("scene_plans",[])):
        x=state.resolve_artifact(r)
        if x:
            plans.append(x)
            if x.get("artifact_type")!="SCENE_PLAN": issues.append(AI("PRODUCTION_LOCK_REVIEW_PLAN_INVALID","scene_plans must reference SCENE_PLAN.",art,path=f"/scene_plans/{i}"))
    for i,r in enumerate(art.get("shots",[])):
        x=state.resolve_object(r)
        if x:
            shots.append(x)
            if x.get("object_type")!="SHOT": issues.append(AI("PRODUCTION_LOCK_REVIEW_SHOT_INVALID","shots must reference SHOT.",art,path=f"/shots/{i}"))
    for i,r in enumerate(art.get("layers",[])):
        x=state.resolve_object(r)
        if x:
            layers.append(x)
            if x.get("object_type")!="LAYER": issues.append(AI("PRODUCTION_LOCK_REVIEW_LAYER_INVALID","layers must reference LAYER.",art,path=f"/layers/{i}"))
    for i,r in enumerate(art.get("cues",[])):
        x=state.resolve_object(r)
        if x:
            cues.append(x)
            if x.get("object_type")!="CUE": issues.append(AI("PRODUCTION_LOCK_REVIEW_CUE_INVALID","cues must reference CUE.",art,path=f"/cues/{i}"))
    for i,r in enumerate(art.get("voice_locks",[])):
        x=state.resolve_artifact(r)
        if x:
            voices.append(x)
            if x.get("artifact_type")!="VOICE_LOCK_MANIFEST": issues.append(AI("PRODUCTION_LOCK_REVIEW_VOICE_INVALID","voice_locks must reference VOICE_LOCK_MANIFEST.",art,path=f"/voice_locks/{i}"))
    for i,r in enumerate(art.get("design_dna_refs",[])):
        x=state.resolve_object(r)
        if x:
            dnas.append(x)
            if x.get("object_type")!="DESIGN_DNA": issues.append(AI("PRODUCTION_LOCK_REVIEW_DNA_INVALID","design_dna_refs must reference DESIGN_DNA.",art,path=f"/design_dna_refs/{i}"))

    plan_by_scene={(p.get("scene_ref") or {}).get("id"):p for p in plans}
    preview_by_scene={(p.get("scene_ref") or {}).get("id"):p for p in previews}
    if plan_by_scene and preview_by_scene and set(plan_by_scene)!=set(preview_by_scene):
        issues.append(AI("PRODUCTION_LOCK_REVIEW_SCENE_COVERAGE_MISMATCH","scene_previews and scene_plans must cover the same exact Scene identities.",art,path="/scene_previews"))
    for sid,pv in preview_by_scene.items():
        pl=plan_by_scene.get(sid)
        if not pl: continue
        ref=pv.get("scene_plan") or {}
        if (ref.get("artifact_id"),ref.get("version"))!=(pl.get("artifact_id"),pl.get("version")):
            issues.append(AI("PRODUCTION_LOCK_REVIEW_PREVIEW_PLAN_MISMATCH","Every Scene Preview must pin the exact reviewed Scene Plan.",art,path="/scene_previews"))

    expected_shots=[]
    for pl in plans:
        for item in pl.get("shots",[]):
            ref=item.get("shot_ref") if isinstance(item,dict) and "shot_ref" in item else item if _is_obj_ref(item) else None
            if ref: expected_shots.append((ref.get("id"),ref.get("version")))
    actual_shots=[(r.get("id"),r.get("version")) for r in art.get("shots",[])]
    if expected_shots and actual_shots!=expected_shots:
        issues.append(AI("PRODUCTION_LOCK_REVIEW_SHOT_CLOSURE_MISMATCH","Review package shots must equal the exact ordered Scene Plan shot closure.",art,path="/shots"))

    expected_layers=[]; expected_cues=[]
    for shot in shots:
        for r in shot.get("layer_refs",[]):
            k=(r.get("id"),r.get("version"))
            if k not in expected_layers: expected_layers.append(k)
        for r in shot.get("cue_refs",[]):
            k=(r.get("id"),r.get("version"))
            if k not in expected_cues: expected_cues.append(k)
    if [(r.get("id"),r.get("version")) for r in art.get("layers",[])]!=expected_layers:
        issues.append(AI("PRODUCTION_LOCK_REVIEW_LAYER_CLOSURE_MISMATCH","Review package layers must equal the exact Shot layer closure.",art,path="/layers"))
    if [(r.get("id"),r.get("version")) for r in art.get("cues",[])]!=expected_cues:
        issues.append(AI("PRODUCTION_LOCK_REVIEW_CUE_CLOSURE_MISMATCH","Review package cues must equal the exact Shot cue closure.",art,path="/cues"))

    expected_voices=[]; expected_dnas=[]
    for pl in plans:
        vr=pl.get("voice_lock") or {}; dk=pl.get("design_dna_ref") or {}
        vk=(vr.get("artifact_id"),vr.get("version")); dk2=(dk.get("id"),dk.get("version"))
        if vk not in expected_voices: expected_voices.append(vk)
        if dk2 not in expected_dnas: expected_dnas.append(dk2)
    if [(r.get("artifact_id"),r.get("version")) for r in art.get("voice_locks",[])]!=expected_voices:
        issues.append(AI("PRODUCTION_LOCK_REVIEW_VOICE_CLOSURE_MISMATCH","voice_locks must equal the exact Scene Plan voice-lock closure.",art,path="/voice_locks"))
    if [(r.get("id"),r.get("version")) for r in art.get("design_dna_refs",[])]!=expected_dnas:
        issues.append(AI("PRODUCTION_LOCK_REVIEW_DNA_CLOSURE_MISMATCH","design_dna_refs must equal the exact Scene Plan design closure.",art,path="/design_dna_refs"))

    closure={k:art.get(k,[]) for k in ("scene_previews","scene_plans","voice_locks","design_dna_refs","shots","layers","cues")}
    if art.get("closure_sha256")!=sha256_json(closure):
        issues.append(AI("PRODUCTION_LOCK_REVIEW_HASH_MISMATCH","closure_sha256 must hash the exact reviewed production closure.",art,path="/closure_sha256"))
    summary=art.get("review_summary") or {}
    expected_counts={"scene_count":len(plans),"shot_count":len(shots),"layer_count":len(layers),"cue_count":len(cues)}
    for field,value in expected_counts.items():
        if int(summary.get(field,-1))!=value:
            issues.append(AI("PRODUCTION_LOCK_REVIEW_SUMMARY_MISMATCH",f"review_summary.{field} must match the exact closure.",art,path=f"/review_summary/{field}"))
    return issues


def production_lock_rules(art,state,catalog):
    issues=[]
    scope=art.get("scope") or {}; scope_type=scope.get("type")
    if scope_type not in {"SCENE","PROJECT"}:
        issues.append(AI("PRODUCTION_LOCK_SCOPE_INVALID","Production Lock scope.type must be SCENE or PROJECT.",art,path="/scope/type"))
    if scope_type=="SCENE":
        vl=state.resolve_artifact(art.get("voice_lock")); sp=state.resolve_artifact(art.get("scene_plan")); dna=state.resolve_object(art.get("design_dna_ref")); prev=state.resolve_artifact(art.get("scene_preview"))
        if vl and vl.get("artifact_type")!="VOICE_LOCK_MANIFEST": issues.append(AI("PRODUCTION_LOCK_VOICE_INVALID","Production Lock voice_lock must be VOICE_LOCK_MANIFEST.",art,path="/voice_lock"))
        if sp and sp.get("artifact_type")!="SCENE_PLAN": issues.append(AI("PRODUCTION_LOCK_SCENE_PLAN_INVALID","Production Lock scene_plan must be SCENE_PLAN.",art,path="/scene_plan"))
        if prev and prev.get("artifact_type")!="SCENE_PREVIEW": issues.append(AI("PRODUCTION_LOCK_SCENE_PREVIEW_INVALID","Production Lock scene_preview must be SCENE_PREVIEW.",art,path="/scene_preview"))
        if dna and dna.get("object_type")!="DESIGN_DNA": issues.append(AI("PRODUCTION_LOCK_DNA_INVALID","Production Lock design_dna_ref must reference DESIGN_DNA.",art,path="/design_dna_ref"))
    elif scope_type=="PROJECT":
        child_shots=set(); child_layers=set(); child_cues=set()
        for i,r in enumerate(art.get("scene_locks",[])):
            lock=state.resolve_artifact(r)
            if lock:
                if lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST" or (lock.get("scope") or {}).get("type")!="SCENE":
                    issues.append(AI("PROJECT_PRODUCTION_LOCK_CHILD_INVALID","scene_locks must reference SCENE Production Locks.",art,path=f"/scene_locks/{i}")); continue
                child_shots.update((x.get("id"),x.get("version")) for x in lock.get("shots",[]))
                child_layers.update((x.get("id"),x.get("version")) for x in lock.get("layers",[]))
                child_cues.update((x.get("id"),x.get("version")) for x in lock.get("cues",[]))
        if not art.get("scene_locks"):
            issues.append(AI("PROJECT_PRODUCTION_LOCK_SCENES_REQUIRED","PROJECT Production Lock requires scene_locks.",art,path="/scene_locks"))
        if child_shots and child_shots!={(x.get("id"),x.get("version")) for x in art.get("shots",[])}:
            issues.append(AI("PROJECT_PRODUCTION_LOCK_SHOT_CLOSURE_FAILED","PROJECT Production Lock shots must equal the union of child Scene Lock shots.",art,path="/shots"))
        if child_layers and child_layers!={(x.get("id"),x.get("version")) for x in art.get("layers",[])}:
            issues.append(AI("PROJECT_PRODUCTION_LOCK_LAYER_CLOSURE_FAILED","PROJECT Production Lock layers must equal the union of child Scene Lock layers.",art,path="/layers"))
        if child_cues!={(x.get("id"),x.get("version")) for x in art.get("cues",[])}:
            issues.append(AI("PROJECT_PRODUCTION_LOCK_CUE_CLOSURE_FAILED","PROJECT Production Lock cues must equal the union of child Scene Lock cues.",art,path="/cues"))
    expected={"shots":"SHOT","layers":"LAYER","cues":"CUE","approvals":"APPROVAL"}
    resolved_by_field={}
    for field,typ in expected.items():
        vals=[]
        for i,r in enumerate(art.get(field,[])):
            o=state.resolve_object(r)
            if o:
                vals.append(o)
                if o.get("object_type")!=typ: issues.append(AI("PRODUCTION_LOCK_OBJECT_TYPE_INVALID",f"{field} entries must reference {typ}.",art,path=f"/{field}/{i}"))
                if o.get("status") in {"STALE","BLOCKED","REJECTED"} or (o.get("stale") or {}).get("is_stale"):
                    issues.append(AI("PRODUCTION_LOCK_CONTAINS_INELIGIBLE_OBJECT",f"Production Lock contains stale/blocked/rejected {typ}.",art,path=f"/{field}/{i}"))
        resolved_by_field[field]=vals
    locked_layers={(x["id"],x["version"]) for x in resolved_by_field["layers"]}
    locked_cues={(x["id"],x["version"]) for x in resolved_by_field["cues"]}
    for shot in resolved_by_field["shots"]:
        for r in shot.get("layer_refs",[]):
            if (r.get("id"),r.get("version")) not in locked_layers: issues.append(AI("PRODUCTION_LOCK_SHOT_LAYER_CLOSURE_FAILED","Every Shot layer must be frozen in Production Lock.layers.",art,path="/layers",related=(f"{shot['id']}@{shot['version']}",)))
        for r in shot.get("cue_refs",[]):
            if (r.get("id"),r.get("version")) not in locked_cues: issues.append(AI("PRODUCTION_LOCK_SHOT_CUE_CLOSURE_FAILED","Every Shot cue must be frozen in Production Lock.cues.",art,path="/cues",related=(f"{shot['id']}@{shot['version']}",)))
    for ap in resolved_by_field["approvals"]:
        if ap.get("decision")!="APPROVED": issues.append(AI("PRODUCTION_LOCK_APPROVAL_NOT_APPROVED","Production Lock may contain only APPROVED approvals.",art,path="/approvals"))
    sentinels={"TBD","TODO","PLACEHOLDER","FILLER","TEMP_ASSET"}
    def scan(v,path=""):
        if isinstance(v,str) and v.strip().upper() in sentinels:
            issues.append(AI("PRODUCTION_PLACEHOLDER_DETECTED","Production Lock contains unresolved placeholder sentinel.",art,path=path or "/"))
        elif isinstance(v,dict):
            for k,x in v.items(): scan(x,f"{path}/{k}")
        elif isinstance(v,list):
            for i,x in enumerate(v): scan(x,f"{path}/{i}")
    scan(art)
    return issues

def renderer_prompt_rules(art,state,catalog):
    lock=state.resolve_artifact(art.get("production_lock"))
    if lock and lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST": return [AI("RENDERER_PROMPT_LOCK_INVALID","Renderer Prompt production_lock must reference PRODUCTION_LOCK_MANIFEST.",art,path="/production_lock")]
    return []


def repair_plan_rules(art,state,catalog):
    issue=state.resolve_object(art.get("qa_issue_ref"))
    if issue and issue.get("object_type")!="QA_ISSUE": return [AI("REPAIR_PLAN_QA_ISSUE_INVALID","Repair Plan qa_issue_ref must reference QA_ISSUE.",art,path="/qa_issue_ref")]
    if issue and (issue.get("root_cause") or {}).get("state") not in {"IDENTIFIED","BOUNDED_UNKNOWN"}:
        return [AI("REPAIR_WITHOUT_ROOT_CAUSE","Repair Plan cannot be created before root cause is identified/bounded.",art,path="/qa_issue_ref")]
    return []



def render_output_rules(art,state,catalog):
    issues=[]
    job=state.resolve_object(art.get("render_job_ref"))
    if job and job.get("object_type")!="RENDER_JOB":
        issues.append(AI("RENDER_OUTPUT_JOB_INVALID","Render Output render_job_ref must reference RENDER_JOB.",art,path="/render_job_ref"))
    return issues

def qa_baseline_rules(art,state,catalog):
    issues=[]
    lock=state.resolve_artifact(art.get("production_lock"))
    if lock and lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST":
        issues.append(AI("QA_BASELINE_LOCK_INVALID","QA Baseline production_lock must reference PRODUCTION_LOCK_MANIFEST.",art,path="/production_lock"))
    rm=state.resolve_object(art.get("render_manifest_ref"))
    if rm and rm.get("object_type")!="RENDER_MANIFEST":
        issues.append(AI("QA_BASELINE_RENDER_MANIFEST_INVALID","QA Baseline render_manifest_ref must reference RENDER_MANIFEST.",art,path="/render_manifest_ref"))
    for i,r in enumerate(art.get("qa_report_refs",[])):
        q=state.resolve_object(r)
        if q and q.get("object_type")!="QA_REPORT":issues.append(AI("QA_BASELINE_REPORT_INVALID","qa_report_refs must reference QA_REPORT.",art,path=f"/qa_report_refs/{i}"))
    for i,r in enumerate(art.get("output_refs",[])):
        a=state.resolve_artifact(r)
        if a and a.get("artifact_type")!="RENDER_OUTPUT":issues.append(AI("QA_BASELINE_OUTPUT_INVALID","output_refs must reference RENDER_OUTPUT.",art,path=f"/output_refs/{i}"))
    return issues

def regression_compare_rules(art,state,catalog):
    issues=[]
    b=state.resolve_artifact(art.get("baseline")); c=state.resolve_artifact(art.get("candidate_output"))
    if b and b.get("artifact_type")!="QA_BASELINE":issues.append(AI("REGRESSION_BASELINE_INVALID","baseline must reference QA_BASELINE.",art,path="/baseline"))
    if c and c.get("artifact_type")!="RENDER_OUTPUT":issues.append(AI("REGRESSION_OUTPUT_INVALID","candidate_output must reference RENDER_OUTPUT.",art,path="/candidate_output"))
    if art.get("unexpected_changes") and art.get("result")=="PASS":issues.append(AI("REGRESSION_FALSE_PASS","Regression compare cannot PASS with unexpected changes.",art,path="/result"))
    return issues

def full_film_qa_package_rules(art,state,catalog):
    issues=[]
    lock=state.resolve_artifact(art.get("production_lock")); out=state.resolve_artifact(art.get("master_output"))
    if lock and lock.get("artifact_type")!="PRODUCTION_LOCK_MANIFEST":issues.append(AI("FULL_FILM_QA_LOCK_INVALID","production_lock must reference PRODUCTION_LOCK_MANIFEST.",art,path="/production_lock"))
    if out and out.get("artifact_type")!="RENDER_OUTPUT":issues.append(AI("FULL_FILM_QA_OUTPUT_INVALID","master_output must reference RENDER_OUTPUT.",art,path="/master_output"))
    for field in ("viewer_experience_report","production_integrity_report","delivery_integrity_report"):
        q=state.resolve_object(art.get(field))
        if q and q.get("object_type")!="QA_REPORT":issues.append(AI("FULL_FILM_QA_REPORT_INVALID",f"{field} must reference QA_REPORT.",art,path=f"/{field}"))
    return issues

def research_pack_rules(art,state,catalog):
    issues=[]
    for i,r in enumerate(art.get("source_refs",[])):
        o=state.resolve_object(r)
        if o and o.get("object_type")!="SOURCE": issues.append(AI("RESEARCH_PACK_SOURCE_INVALID","Research Pack source_refs must reference SOURCE.",art,path=f"/source_refs/{i}"))
    return issues

def final_asset_manifest_rules(art,state,catalog):
    issues=[]
    for i,e in enumerate(art.get("assets",[])):
        if not isinstance(e,dict): continue
        a=state.resolve_object(e.get("asset_ref"))
        if a and a.get("object_type")!="ASSET": issues.append(AI("FINAL_ASSET_MANIFEST_ASSET_INVALID","asset_ref must reference ASSET.",art,path=f"/assets/{i}/asset_ref"))
        for j,r in enumerate(e.get("segment_refs",[])):
            seg=state.resolve_object(r)
            if seg and seg.get("object_type")!="SEGMENT": issues.append(AI("FINAL_ASSET_MANIFEST_SEGMENT_INVALID","segment_refs must reference SEGMENT.",art,path=f"/assets/{i}/segment_refs/{j}"))
    return issues

def provenance_manifest_rules(art,state,catalog):
    issues=[]
    if not art.get("entries") and not art.get("disclosures"):
        issues.append(AI("PROVENANCE_MANIFEST_EMPTY","Provenance Manifest requires at least one lineage entry or disclosure.",art,path="/entries"))
    return issues

def delivery_package_rules(art,state,catalog):
    issues=[]
    for i,r in enumerate(art.get("items",[])):
        if state.resolve_artifact(r) is None: issues.append(AI("DELIVERY_PACKAGE_ITEM_MISSING","Delivery Package item does not resolve.",art,path=f"/items/{i}"))
    return issues

def delivery_review_package_rules(art,state,catalog):
    issues=[]
    typed_artifacts={
        "project_lock":"PRODUCTION_LOCK_MANIFEST",
        "master_output":"RENDER_OUTPUT",
        "final_asset_manifest":"FINAL_ASSET_MANIFEST",
        "provenance_manifest":"PROVENANCE_MANIFEST",
        "delivery_package":"DELIVERY_PACKAGE",
    }
    for field,typ in typed_artifacts.items():
        a=state.resolve_artifact(art.get(field))
        if a and a.get("artifact_type")!=typ:
            issues.append(AI("DELIVERY_REVIEW_ARTIFACT_INVALID",f"{field} must reference {typ}.",art,path=f"/{field}"))
    lock=state.resolve_artifact(art.get("project_lock"))
    if lock and (lock.get("scope") or {}).get("type")!="PROJECT":
        issues.append(AI("DELIVERY_REVIEW_PROJECT_LOCK_REQUIRED","Delivery review requires PROJECT Production Lock.",art,path="/project_lock"))
    for field,rtype in (("full_film_qa","FULL_FILM_QA"),("delivery_qa","DELIVERY_QA")):
        q=state.resolve_object(art.get(field))
        if q and (q.get("object_type")!="QA_REPORT" or q.get("report_type")!=rtype):
            issues.append(AI("DELIVERY_REVIEW_QA_INVALID",f"{field} must reference QA_REPORT/{rtype}.",art,path=f"/{field}"))
    dq=state.resolve_object(art.get("delivery_qa"))
    if dq and dq.get("result") not in {"PASS","WARN"}:
        issues.append(AI("DELIVERY_REVIEW_QA_NOT_ACCEPTABLE","delivery_qa must be PASS or WARN for review packaging.",art,path="/delivery_qa"))
    cp=state.resolve_object(art.get("pre_release_checkpoint"))
    if cp and (cp.get("object_type")!="CHECKPOINT" or cp.get("checkpoint_class")!="PRE_RELEASE"):
        issues.append(AI("DELIVERY_REVIEW_CHECKPOINT_INVALID","pre_release_checkpoint must reference PRE_RELEASE CHECKPOINT.",art,path="/pre_release_checkpoint"))
    pkg=state.resolve_artifact(art.get("delivery_package"))
    if pkg:
        item_keys={(x.get("artifact_id"),x.get("version")) for x in pkg.get("items",[]) if isinstance(x,dict)}
        for field in ("master_output","final_asset_manifest","provenance_manifest"):
            r=art.get(field) or {}
            if (r.get("artifact_id"),r.get("version")) not in item_keys:
                issues.append(AI("DELIVERY_REVIEW_PACKAGE_CLOSURE_INVALID",f"delivery_package does not contain {field}.",art,path="/delivery_package"))
    return issues

def restore_plan_rules(art,state,catalog):
    issues=[]
    if state.object_type(art.get("checkpoint_ref",{})) not in {None,"CHECKPOINT"}: issues.append(AI("RESTORE_CHECKPOINT_INVALID","Restore Plan checkpoint_ref must reference CHECKPOINT.",art,path="/checkpoint_ref"))
    if art.get("target_baseline_manifest_version",0)>art.get("current_manifest_version",0): issues.append(AI("RESTORE_TARGET_NOT_HISTORICAL","Restore baseline cannot be newer than current manifest version.",art,path="/target_baseline_manifest_version"))
    if art.get("human_confirmation_required") is not True: issues.append(AI("RESTORE_HUMAN_CONFIRMATION_REQUIRED","Restore Plan must require human confirmation.",art,path="/human_confirmation_required"))
    return issues



def candidate_comparison_rules(art,state,catalog):
    issues=[]
    beat=state.resolve_object(art.get("target_beat_ref"))
    if beat and beat.get("object_type")!="NARRATION_BEAT":
        issues.append(AI("CANDIDATE_COMPARISON_BEAT_INVALID","target_beat_ref must reference NARRATION_BEAT.",art,path="/target_beat_ref"))
    viable=set()
    for i,r in enumerate(art.get("search_refs",[])):
        o=state.resolve_object(r)
        if o and o.get("object_type")!="SEARCH":
            issues.append(AI("CANDIDATE_COMPARISON_SEARCH_INVALID","search_refs must reference SEARCH.",art,path=f"/search_refs/{i}"))
    candidate_keys=set()
    for i,r in enumerate(art.get("candidate_refs",[])):
        o=state.resolve_object(r)
        if o and o.get("object_type")!="SEARCH_RESULT":
            issues.append(AI("CANDIDATE_COMPARISON_RESULT_INVALID","candidate_refs must reference SEARCH_RESULT.",art,path=f"/candidate_refs/{i}"))
        if o: candidate_keys.add((o["id"],int(o["version"])))
    for i,r in enumerate(art.get("viable_candidate_refs",[])):
        o=state.resolve_object(r)
        if o and o.get("object_type")!="SEARCH_RESULT":
            issues.append(AI("CANDIDATE_COMPARISON_VIABLE_INVALID","viable_candidate_refs must reference SEARCH_RESULT.",art,path=f"/viable_candidate_refs/{i}"))
        if o and o.get("candidate_state")!="VIABLE":
            issues.append(AI("CANDIDATE_COMPARISON_NOT_VIABLE","viable_candidate_refs may include only VIABLE SEARCH_RESULT objects.",art,path=f"/viable_candidate_refs/{i}"))
        if o:
            viable.add((o["id"],int(o["version"])))
            if (o["id"],int(o["version"])) not in candidate_keys:
                issues.append(AI("CANDIDATE_COMPARISON_VIABLE_NOT_LISTED","Every viable candidate must also appear in candidate_refs.",art,path=f"/viable_candidate_refs/{i}"))
    for i,d in enumerate(art.get("dimensions",[])):
        o=state.resolve_object(d.get("candidate_ref"))
        if o and (o["id"],int(o["version"])) not in candidate_keys:
            issues.append(AI("CANDIDATE_COMPARISON_DIMENSION_NOT_LISTED","dimension candidate_ref must be listed in candidate_refs.",art,path=f"/dimensions/{i}/candidate_ref"))
    target=art.get("policy_target") or {}
    meets=len(viable)>=int(target.get("viable_candidates",0)) and len(set(art.get("source_families") or []))>=int(target.get("source_families",0))
    if art.get("assessment")=="MEETS_TARGET" and not meets:
        issues.append(AI("CANDIDATE_COMPARISON_FALSE_COMPLETE","MEETS_TARGET requires the declared viable-candidate and source-family targets to be met.",art,path="/assessment"))
    if art.get("assessment")=="NEEDS_SEARCH_AGAIN" and meets:
        issues.append(AI("CANDIDATE_COMPARISON_UNNECESSARY_SEARCH_AGAIN","NEEDS_SEARCH_AGAIN is inconsistent with the declared target counts.",art,path="/assessment"))
    return issues

def global_artifact_id_type_consistency(state: StateView,catalog: SchemaCatalog):
    issues=[]
    types=defaultdict(set)
    for (aid,_),a in state.artifacts.items(): types[aid].add(a.get("artifact_type"))
    for aid,ts in types.items():
        if len(ts)>1:
            for (x,_),a in state.artifacts.items():
                if x==aid: issues.append(AI("ARTIFACT_ID_TYPE_COLLISION",f"Artifact ID {aid} is used by multiple artifact types: {sorted(ts)}.",a))
    return issues


ARTIFACT_RULES={
    "*": [artifact_refs_resolve, artifact_lineage],
    "VOICEOVER_SCRIPT_FINAL": [voiceover_script_rules],
    "TTS_READY_SCRIPT": [tts_script_rules],
    "MASTER_VOICE": [master_voice_rules],
    "VOICE_TIMING_MAP": [voice_timing_map_rules],
    "VOICE_LOCK_MANIFEST": [voice_lock_rules],
    "MOTION_PREVIS": [motion_previs_rules],
    "THREE_D_PREVIS": [three_d_previs_rules],
    "SCENE_PLAN": [scene_plan_rules],
    "SCENE_PREVIEW": [scene_preview_rules],
    "REVIEW_PACKAGE": [review_package_rules],
    "VOICE_REVIEW_PACKAGE": [voice_review_package_rules],
    "DESIGN_DNA_REVIEW_PACKAGE": [design_dna_review_package_rules],
    "PRODUCTION_LOCK_REVIEW_PACKAGE": [production_lock_review_package_rules],
    "PRODUCTION_LOCK_MANIFEST": [production_lock_rules],
    "RENDERER_PROMPT": [renderer_prompt_rules],
    "REPAIR_PLAN": [repair_plan_rules],
    "RENDER_OUTPUT": [render_output_rules],
    "QA_BASELINE": [qa_baseline_rules],
    "REGRESSION_COMPARE": [regression_compare_rules],
    "FULL_FILM_QA_PACKAGE": [full_film_qa_package_rules],
    "RESEARCH_PACK": [research_pack_rules],
    "FINAL_ASSET_MANIFEST": [final_asset_manifest_rules],
    "PROVENANCE_MANIFEST": [provenance_manifest_rules],
    "DELIVERY_PACKAGE": [delivery_package_rules],
    "DELIVERY_REVIEW_PACKAGE": [delivery_review_package_rules],
    "RESTORE_PLAN": [restore_plan_rules],
    "CANDIDATE_COMPARISON": [candidate_comparison_rules],
}
GLOBAL_RULES.append(global_artifact_id_type_consistency)
