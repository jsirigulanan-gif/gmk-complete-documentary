# GMK Schema v1 — Build 009 Changelog

## Added
- `gmk_release/`
  - Final Asset Manifest compiler
  - Provenance Manifest compiler
  - Delivery Profile loader/validator
  - Delivery QA runtime
  - Delivery Package compiler
  - PRE_RELEASE Checkpoint integration
  - idempotent PUBLISH Operation integration
  - immutable RELEASE creation
  - FINAL_PROJECT Checkpoint + Project completion flow
- `gmk_orchestrator/`
  - Gate-respecting orchestration harness
  - Next Legal Action / state status surface
  - adjacent state transition driver
- `QARuntime.evaluate_full_film()`
  - Viewer Experience pass
  - Production Integrity pass
  - Delivery Integrity pass
  - aggregate FULL_FILM_QA + package
- `config/delivery_profiles/GMK_YOUTUBE_4K.yaml`
- `tools/release_orchestrator_smoke.py`
- Build 009 end-to-end integration tests

## Contract implementation fixes
- Added missing physical `RESEARCH_PACK` Artifact contract already referenced by the frozen Bootstrap/Manifest design.
- Completed `PRODUCTION_LOCK_MANIFEST` physical schema support for both SCENE and PROJECT scopes.
- Added PROJECT Production Lock aggregation runtime.
- Enforced `RELEASED_OBJECT_MUTATION_FORBIDDEN` in State Engine.
- Strengthened Release semantic validation for Project Lock, master output, manifests, required QA types and successful PUBLISH Operation.
- Added semantic checks for Research Pack, Final Asset Manifest, Provenance Manifest and Delivery Package.

## Validation
```text
Schema / artifact contracts            75 PASS
Semantic validation                    PASS
Release / Orchestrator E2E             PASS
Completed-project Cold Start           PASS
Full pytest                            91 passed
```

## Contract status
`GMK_SCHEMA_V1_CONTRACT = FROZEN`

No Core Object was added and no 2K architecture round was introduced.
