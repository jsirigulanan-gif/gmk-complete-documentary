# GMK Schema v1 — Build 008 Changelog

## Added
- `gmk_production/`
  - Production Lock Runtime
  - exact Shot/Layer/Cue closure compiler
  - exact approval eligibility checks
  - lock dependency snapshot hashing
  - stale/invalidation rejection for Final Render
- `gmk_render/`
  - provider-independent Render Runtime
  - FINAL job queueing from Production Lock
  - renderer prompt compilation
  - bounded transient retry
  - deterministic render-key cache reuse
  - `RENDER_OUTPUT` creation
  - `RENDER_MANIFEST` execution records
- `gmk_qa/`
  - QA execution runtime
  - QA Issue / QA Report creation
  - derived PASS/WARN/FAIL
  - Repair Plan compiler
  - two-cycle auto-repair cap
  - QA Baseline and Regression Compare creation
- `production_render_qa_smoke.py`
- Build 008 runtime test suite

## Physical artifact contracts completed
The following were already part of the frozen 2H architecture but had not yet been represented as physical schema files:
- `RENDER_OUTPUT`
- `QA_BASELINE`
- `REGRESSION_COMPARE`
- `FULL_FILM_QA_PACKAGE`

Local schema registry count increased from **70 → 74** without adding any Core Object.

## Runtime guarantees added
- Final Render cannot start from an unresolved/invalidation-marked Production Lock.
- Renderer execution cannot silently switch to a newer ACTIVE Shot/Layer/Cue.
- Transient retry does not change creative decisions.
- Cache reuse is auditable through a new Render Manifest.
- QA success is distinct from renderer execution success.
- Root cause is mandatory before Repair Plan creation.
- QA does not directly repair authoritative production objects.
- Auto Repair planning stops after two cycles.
- Regression records unexpected changed scope rather than silently accepting it.

## Validation
```text
JSON Schema / artifact contracts   74 PASS
Local $ref resolution              PASS
Semantic validation                PASS
Production/Render/QA smoke         PASS
Full pytest                        88 passed
```

## Contract status
`GMK_SCHEMA_V1_CONTRACT = FROZEN`

No 2K, no new Core Object, and no architecture redesign were introduced.
