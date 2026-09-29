# GMK Schema v1 — Build 025 Changelog

## Purpose
Implement the frozen `VOICE_LOCKED → DESIGN_DNA_APPROVED` stage and repair the same pre-Scene review-context deadlock that previously affected Voice approval.

## Schema v1 erratum
Added one narrowly scoped Artifact contract:

- `DESIGN_DNA_REVIEW_PACKAGE`

It allows a human to review the exact active `DESIGN_DNA` before any Scene Plan exists. The package pins:

- exact `DESIGN_DNA` version
- `VOICE_LOCK_MANIFEST`
- `NARRATIVE_SPINE`
- `EFFECTIVE_DESIGN_TOKENS`
- review summary (rule count, reference count, visual thesis)

The existing visual `REVIEW_PACKAGE` remains unchanged and still requires `SCENE_PLAN + SCENE_PREVIEW + shots`.

## Runtime added
- `gmk_design.DesignRuntime`
- `DesignRuntime.prepare()`
- `DesignRuntime.review_package()`
- `DesignRuntime.decide()`
- CLI `gmk design-prepare`
- CLI `gmk design-review-package`
- CLI `gmk design-decide`

## Authority
`design-prepare` creates the active `DESIGN_DNA` and `EFFECTIVE_DESIGN_TOKENS` but deliberately leaves the `DESIGN_DNA` Gate at FAIL until a human decision exists.

`design-decide` requires explicit human `actor_id` and an explicit `APPROVED` or `REJECTED` decision. Only APPROVED may transition the project to `DESIGN_DNA_APPROVED`.

## Architecture impact
- Core Objects: unchanged.
- Project States: unchanged.
- Gate IDs / transition order: unchanged.
- Existing `REVIEW_PACKAGE`: unchanged.
- Artifact contracts: **77 → 78**.
- Schema status: **FROZEN WITH ERRATA 024 + 025**.
