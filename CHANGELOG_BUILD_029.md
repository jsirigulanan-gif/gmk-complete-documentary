# GMK Schema v1 — Build 029 Changelog

## Added
- `PRODUCTION_LOCK_REVIEW_PACKAGE` artifact contract.
- Semantic closure validation for exact Project / Scene Preview / Scene Plan / Voice / Design / Shot / Layer / Cue refs.
- Approval-context support for `SHOT_VISUAL` and `PRODUCTION_LOCK` against the exact Production Lock review closure.
- `gmk_production.ProductionLockStageRuntime`.
- CLI command `gmk production-lock-prepare`.
- CLI command `gmk production-lock-decide`.
- Human APPROVED/REJECTED Production Lock review flow.
- Idempotent Scene Lock / Project Lock creation and replay behavior.
- Build 029 regression coverage.

## Runtime behavior
- Prepare runs from `HTML_APPROVED` and creates no Production Lock yet.
- The review package pins the exact current Scene Preview, Scene Plan, Voice Lock, Design DNA, Shot, Layer, and Cue closure and hashes the complete closure.
- Human `APPROVED` creates exact `SHOT_VISUAL` approvals only for Shots inside the reviewed closure.
- Scene Production Locks are then compiled with the existing Production Lock Runtime.
- One Project Production Lock aggregates the exact Scene Locks.
- The same human-reviewed closure is the context for exact `PRODUCTION_LOCK` approvals on every current Scene/Project Lock created from that closure.
- Transition to `PRODUCTION_RENDER` occurs only after the existing `PRODUCTION_LOCK` Gate returns PASS/WARN.
- Human `REJECTED` is durable and creates no lock.
- Closure drift requires a new review package / human decision; no prior approval is silently carried forward.

## Erratum 029
The original `REVIEW_PACKAGE` contract is Scene-specific and could not faithfully represent a Project Production Lock before the lock artifacts existed. Build 029 adds a narrow review-context artifact rather than weakening the existing Scene review package or bypassing exact Shot approval requirements.

No Core Object, Project State, Gate ID, or transition was added or changed.

`GMK_SCHEMA_V1_CONTRACT = FROZEN_WITH_ERRATA_024_025_029`
