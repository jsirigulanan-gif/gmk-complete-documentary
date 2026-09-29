# GMK Schema v1 — Build 026 Changelog

## Purpose
Implement the frozen `DESIGN_DNA_APPROVED → SCENE_PLAN_READY` stage without creating Shot objects early.

## Runtime added
- `gmk_planning.ScenePlanRuntime`
- CLI `gmk scene-plan`

## Scene planning behavior
For every active `SCENE`, Build 026 creates exactly one:

- `SCENE_ASSET_POOL`
- `SCENE_PLAN`

Each Scene Plan pins the exact current:

- `VOICE_LOCK_MANIFEST`
- approved `DESIGN_DNA`
- `EFFECTIVE_DESIGN_TOKENS`
- scene-specific `SCENE_ASSET_POOL`

The Scene Asset Pool records the active Narration Beats in that Scene, their visual requirements, production-ready VERIFIED Segment refs, and exact voice ranges derived from `VOICE_TIMING_MAP`.

## Fail-closed rules
Build 026 rejects a Scene Beat when:

- no stable Beat identity can be resolved;
- no production-ready VERIFIED Segment exists for the Beat;
- no exact voice timing can be resolved from the locked Timing Map;
- the active Design DNA does not match the Effective Design Tokens;
- the Voice Lock / Timing Map dependency is missing.

## Shot boundary
`SCENE_PLAN.shots` is deliberately created as an empty array. Build 026 does **not** create any `SHOT` object. The frozen pipeline reserves Shot creation for the following `SHOT_PLAN` stage.

## Architecture impact
- Core Objects: unchanged.
- Project States: unchanged.
- Gate IDs / transition order: unchanged.
- Artifact contracts: unchanged at **78**.
- Schema status remains **FROZEN_WITH_ERRATA_024_025**.
