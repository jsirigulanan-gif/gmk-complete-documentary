# GMK Schema v1 — Release / Delivery + Orchestrator Report

## Scope
Build 009 implements the frozen 2I release boundary and adds a thin end-to-end orchestration harness without introducing a new Core Object or changing the authority model.

## Release / Delivery Runtime
Implemented `gmk_release.ReleaseRuntime` with the following enforced sequence:

```text
PROJECT Production Lock
        ↓
exact Production Lock approval
        ↓
Master Render Output from that exact lock
        ↓
FULL_FILM_QA PASS/WARN
        ↓
Final Asset Manifest
        ↓
Provenance Manifest
        ↓
Delivery Profile validation
        ↓
DELIVERY_QA PASS/WARN
        ↓
Delivery Package
        ↓
PRE_RELEASE Checkpoint
        ↓
PUBLISH Operation (idempotent + Human confirmation)
        ↓
RELEASE = RELEASED
        ↓
FINAL_PROJECT Checkpoint
        ↓
PROJECT_COMPLETED
```

A rendered file alone cannot become a Release.

## Project Production Lock
Build 008 implemented Scene locks. Build 009 completes the frozen 2G contract by adding PROJECT-scope Production Lock aggregation.

A Project Lock:
- accepts exact SCENE Production Lock references only;
- copies the exact Shot / Layer / Cue closure from child locks;
- never re-resolves current ACTIVE production objects;
- pins the exact Schema + Policy Bundle;
- remains immutable historical truth when live project state changes;
- is required by Release Runtime.

The physical `PRODUCTION_LOCK_MANIFEST` schema was corrected so SCENE and PROJECT lock shapes are both representable.

## Final Asset Manifest
`FINAL_ASSET_MANIFEST` is derived from the frozen Project Lock, not the entire project library.

For media layers, the runtime traces:

```text
SHOT → LAYER → SEGMENT → ASSET → SOURCE
```

and records exact Asset/Segment use. Release is blocked if a used Asset has a rights status outside the configured allowed set.

## Provenance Manifest
The release compiler records exact lineage for source-backed media and also records non-evidence disclosures for explanatory production elements such as procedural graphics and 3D reconstruction.

Voice lineage is traced through the exact child Scene Lock → Voice Lock → Master Voice chain.

## Delivery Profile + Delivery QA
Build 009 adds a pinned `GMK_YOUTUBE_4K` Delivery Profile config. The runtime currently validates:
- width / height;
- allowed codec;
- minimum duration;
- required delivery metadata.

Delivery QA is persisted as a normal `QA_REPORT` with `report_type = DELIVERY_QA`; no parallel QA system was introduced.

## Release execution
Publishing is an external `OPERATION` and therefore uses the Build 007 safeguards:
- explicit Human confirmation;
- verified PRE_RELEASE Checkpoint;
- idempotency key;
- exact Delivery Package subject;
- no blind retry from unknown external state.

A `RELEASE` Core Object is created only after the publish Operation reaches an allowed successful terminal state.

## Release immutability
A RELEASED Release can no longer be revised in place. `StateTransaction.create_version()` now fails with:

```text
RELEASED_OBJECT_MUTATION_FORBIDDEN
```

A corrected public release must be represented by a new RELEASE object and lineage through `supersedes_release_ref`.

## Full Film QA helper
`QARuntime.evaluate_full_film()` now runs and records three passes:
- Viewer Experience;
- Production Integrity;
- Delivery Integrity;

and creates both an aggregate `FULL_FILM_QA` report and a `FULL_FILM_QA_PACKAGE` artifact.

## End-to-End Orchestrator Harness
Added `gmk_orchestrator.GMKOrchestrator` as a thin integration harness. It does not fabricate missing evidence or bypass gates. It:
- exposes current Project State, Safety Mode and Next Legal Action;
- advances only through Gate Engine-authorized adjacent transitions;
- composes Production Lock, Render, QA, Operation, Checkpoint and Release runtimes.

The synthetic integration test walks the full state machine:

```text
BOOTSTRAPPED
→ RESEARCH_INTAKE
→ RESEARCH_AUDITED
→ ROUGH_NARRATIVE_READY
→ VISUAL_REQUIREMENTS_READY
→ ASSET_RECON
→ ASSET_CATALOG_READY
→ VISUAL_COVERAGE_READY
→ SCRIPT_READY
→ TTS_READY
→ VOICE_LOCKED
→ DESIGN_DNA_APPROVED
→ SCENE_PLAN_READY
→ SHOT_PLAN_READY
→ HTML_REVIEW
→ HTML_APPROVED
→ PRODUCTION_RENDER
→ SHOT_QA_PASSED
→ SCENE_QA_PASSED
→ FULL_FILM_QA_PASSED
→ DELIVERY_READY
→ PROJECT_COMPLETED
```

After completion, the workspace is persisted and reconstructed through Cold Start. `PROJECT_COMPLETED` and `current_release` survive restart.

## Compatibility fixes discovered by Build 009
The end-to-end run exposed three physical implementation gaps in previously frozen contracts:

1. `RESEARCH_PACK` was referenced by the Bootstrap Gate and Project Manifest but had no physical artifact schema. Build 009 adds that missing contract.
2. The Production Lock schema represented Scene locks but not the already-locked Project aggregate form. Build 009 adds the PROJECT shape without adding a new Core Object.
3. RELEASED Release immutability existed in the contract but was not enforced by the State Engine. Build 009 adds the hard mutation guard.

These are implementation-alignment fixes, not architecture changes.

## Validation
```text
JSON Schema / artifact contracts       75 PASS
Local $ref resolution                  PASS
Semantic validation                    PASS
State Engine smoke                     PASS
Dependency Engine smoke                PASS
Gate Engine smoke                      PASS
Cold Start smoke                       PASS
Operation / Incident / Recovery smoke  PASS
Production / Render / QA smoke         PASS
Release / Orchestrator E2E smoke       PASS
Full pytest                            91 passed
```
