# GMK Schema v1 — Build 027 Changelog

## Added
- `gmk_planning.ShotPlanRuntime`.
- CLI command `gmk shot-plan`.
- Deterministic baseline compiler: one active `SHOT` per active `NARRATION_BEAT`.
- One BASE `LAYER` per Shot sourced from a production-ready VERIFIED `SEGMENT`.
- One `SHOW` `CUE` per Shot anchored to the exact `VOICE_BLOCK` represented in `VOICE_TIMING_MAP`.
- Exact absolute Shot timing from the locked voice timing map.
- `SCENE_PLAN` head revisions that pin the exact ordered Shot refs.
- Build 027 regression coverage for creation, state transition, and idempotent replay.

## Runtime behavior
- Runs only from `SCENE_PLAN_READY` (or replays from `SHOT_PLAN_READY`).
- Requires current Scene Plan coverage for every active Scene.
- Requires a current `VOICE_LOCK_MANIFEST`, `VOICE_TIMING_MAP`, and `MASTER_VOICE` reference.
- Requires a production-ready VERIFIED Segment for every active narration Beat.
- Requires exact Beat timing from the locked Voice Block mapping.
- Creates no HTML preview and does not advance beyond `SHOT_PLAN_READY`.
- Replays idempotently when the exact compiled Shot/Layers/Cues and Scene Plan heads already exist.

## Schema status
No schema contract was added or changed in Build 027.

`GMK_SCHEMA_V1_CONTRACT = FROZEN_WITH_ERRATA_024_025`
